"""Pure implementations of the MCP tools.

Deliberately free of any MCP protocol code: these are ordinary functions that
take and return JSON-friendly dicts. ``server.py`` is the only module that
knows they are exposed over a protocol. Keeping the split means the clinical
logic is unit-testable, and swapping transports never touches it.

The functions map onto the assignment's agent pipeline:

    get_reference_range   ->  the optional "reference_range_lookup" tool
    classify_lab_result   ->  the Classify step
    route_by_severity     ->  the Route step
    list_reference_ranges ->  catalogue discovery for the UI

Severity vocabulary is the assignment's: **Normal, Warning, Critical**.
``unknown`` is not a fourth severity - it marks a row that could not be
interpreted at all (unrecognised test, non-numeric value, incompatible unit)
and belongs to the error-handling requirement, not the classification one.
"""

from __future__ import annotations

from typing import Any

from .reference_ranges import (
    REFERENCE_RANGES,
    TestDefinition,
    list_known_tests,
    normalize_qualitative,
    normalize_unit,
    resolve_test,
    unit_is_compatible,
)

# Order used everywhere results are sorted: most urgent first.
SEVERITY_ORDER: tuple[str, ...] = ("critical", "warning", "normal", "unknown")

# When a caller supplies a reference interval but no critical thresholds - the
# Kaggle dataset ships Min_Reference/Max_Reference and has no concept of a
# panic value - critical bounds are estimated this far outside the interval,
# measured in multiples of its width.
#
# This is a heuristic, not a clinical panic value, and every result derived
# this way says so in `critical_basis` so the UI can label it. Where the test
# is in our own table, that table's real thresholds are used instead.
DERIVED_CRITICAL_MARGIN = 0.5


# ---------------------------------------------------------------------------
# Tool 1 - reference range lookup
# ---------------------------------------------------------------------------

def get_reference_range(test_name: str) -> dict[str, Any]:
    """Look up the built-in clinical reference range for a lab test.

    Resolves aliases and minor typos, so "HGB", "Haemoglobin", "hemoglobin"
    and the Turkish "Lökosit" all reach the right definition.

    Returns a dict with ``found`` set to True or False. An unknown test is a
    normal outcome, not an exception - the caller reports it and moves on.
    """
    resolved = resolve_test(test_name)
    if resolved is None:
        return {
            "found": False,
            "requested_name": test_name,
            "error": f"No reference range is defined for {test_name!r}.",
            "known_tests": list_known_tests(),
        }

    definition, matched_by = resolved
    return {
        "found": True,
        "requested_name": test_name,
        "matched_by": matched_by,
        "test_name": definition.canonical_name,
        "unit": definition.unit,
        "low": definition.low,
        "high": definition.high,
        "critical_low": definition.critical_low,
        "critical_high": definition.critical_high,
        "category": definition.category,
        "specialty": definition.specialty,
        "measures": definition.measures,
    }


def list_reference_ranges() -> dict[str, Any]:
    """List every test this server can classify, with its thresholds.

    Lets a client discover the catalogue instead of hardcoding it. The UI uses
    this for input autocomplete and to show users what is supported before
    they submit, so the clinical table stays the single source of truth.
    """
    return {
        "count": len(REFERENCE_RANGES),
        "tests": [
            {
                "test_name": d.canonical_name,
                "unit": d.unit,
                "low": d.low,
                "high": d.high,
                "critical_low": d.critical_low,
                "critical_high": d.critical_high,
                "category": d.category,
                "specialty": d.specialty,
                "measures": d.measures,
                "aliases": list(d.aliases),
            }
            for d in REFERENCE_RANGES.values()
        ],
    }


# ---------------------------------------------------------------------------
# Value parsing
# ---------------------------------------------------------------------------

def _parse_value(raw: Any) -> tuple[float | None, str | None, str | None]:
    """Coerce a raw cell into a number.

    Returns ``(value, qualifier, error)``. Exactly one of ``value`` or
    ``error`` is set.

    Real lab exports contain censored results such as ``"<0.1"`` or ``">1000"``
    (below or above the instrument's measurable limit). The qualifier is kept
    so the explanation can say the value was reported as a limit rather than a
    precise measurement.
    """
    if raw is None:
        return None, None, "Value is missing."

    if isinstance(raw, bool):  # bool is an int subclass; never a lab value
        return None, None, f"Value {raw!r} is not numeric."

    if isinstance(raw, (int, float)):
        number, qualifier = float(raw), None
    else:
        text = str(raw).strip().replace(",", "")
        if not text:
            return None, None, "Value is empty."

        qualifier = None
        if text[0] in "<>":
            qualifier, text = text[0], text[1:].strip()

        try:
            number = float(text)
        except ValueError:
            return None, None, f"Value {str(raw).strip()!r} is not numeric."

    if number != number or number in (float("inf"), float("-inf")):
        return None, None, f"Value {raw!r} is not a finite number."

    if number < 0:
        return None, None, f"Value {number} is negative, which no lab test reports."

    return number, qualifier, None


def _failed(test_name: str, value: Any, unit: str | None,
            error: str, **extra: Any) -> dict[str, Any]:
    """Build an uninterpretable result.

    Severity ``unknown`` means "we will not guess". These rows are still
    returned to the user, clearly flagged, and are the assignment's
    error-handling case rather than a classification.
    """
    return {
        "test_name": test_name,
        "value": value,
        "unit": unit,
        "severity": "unknown",
        "band": None,
        "reference_range": None,
        "range_source": None,
        "critical_basis": None,
        "comparison": None,
        "direction": None,
        "deviation_pct": None,
        "deviation_text": None,
        "rule_fired": None,
        "matched_by": None,
        "unit_assumed": False,
        "category": None,
        "specialty": None,
        "measures": None,
        "notes": None,
        "error": error,
        **extra,
    }


# ---------------------------------------------------------------------------
# Range selection
# ---------------------------------------------------------------------------

def _select_range(
    definition: TestDefinition | None,
    reference_low: float | None,
    reference_high: float | None,
) -> tuple[dict[str, Any] | None, str, str]:
    """Choose which reference interval to classify against.

    Precedence, and why:

    1. **The interval supplied with the result.** Reference intervals vary by
       laboratory, method and population, so the range that arrived with a
       result is authoritative for that result. The Kaggle dataset ships one
       per row.
    2. **The built-in table.** Used when the row carries no interval. It is
       also the only source of genuine critical thresholds.
    3. **Neither** - the test cannot be classified.

    When a supplied interval is used for a test we also know, that test's real
    critical thresholds are kept if they remain consistent with the supplied
    bounds. Otherwise criticals are estimated from the interval's width and
    labelled as derived.

    Returns ``(range_dict, range_source, critical_basis)``.
    """
    supplied = reference_low is not None and reference_high is not None

    if supplied and reference_low >= reference_high:
        supplied = False  # nonsense interval; fall back to the table

    if supplied:
        low, high = float(reference_low), float(reference_high)
        unit = definition.unit if definition else ""

        critical_low = critical_high = None
        basis = "none"

        # Prefer real panic values when we have them and they still bracket
        # the supplied interval.
        if definition is not None:
            if definition.critical_low is not None and definition.critical_low < low:
                critical_low = definition.critical_low
            if definition.critical_high is not None and definition.critical_high > high:
                critical_high = definition.critical_high
            if critical_low is not None or critical_high is not None:
                basis = "table"

        if basis == "none":
            width = high - low
            margin = width * DERIVED_CRITICAL_MARGIN
            derived_low = low - margin
            critical_low = derived_low if derived_low > 0 else None
            critical_high = high + margin
            basis = "derived"

        return (
            {
                "low": low,
                "high": high,
                "critical_low": critical_low,
                "critical_high": critical_high,
                "unit": unit,
            },
            "supplied",
            basis,
        )

    if definition is not None:
        return (
            {
                "low": definition.low,
                "high": definition.high,
                "critical_low": definition.critical_low,
                "critical_high": definition.critical_high,
                "unit": definition.unit,
            },
            "internal",
            "table",
        )

    return None, "none", "none"


# ---------------------------------------------------------------------------
# Tool 2 - classification
# ---------------------------------------------------------------------------

def classify_lab_result(
    test_name: str,
    value: Any,
    unit: str | None = None,
    reference_low: float | None = None,
    reference_high: float | None = None,
    reference_text: str | None = None,
) -> dict[str, Any]:
    """Classify one lab result as Normal, Warning or Critical.

    This is the Classify step, and it is entirely deterministic - the same
    inputs always produce the same severity. No language model is involved.

    Two comparison modes:

    * **numeric** - the value is compared against a reference interval.
    * **qualitative** - word results such as "Negatif" or "1+" are compared
      against a word reference. Urinalysis strips report these, and no numeric
      comparison can handle them.

    Args:
        test_name: Lab test name; aliases and typos are tolerated.
        value: Measured value. Numbers, numeric strings, censored results
            ("<0.1") and qualitative words are all accepted.
        unit: Unit as reported.
        reference_low: Lower bound supplied with the result, if any.
        reference_high: Upper bound supplied with the result, if any.
        reference_text: Expected qualitative result, e.g. "Negatif".

    Returns:
        A classified result carrying the full explainability payload: which
        range was used and where it came from, the direction and size of any
        deviation, and the literal comparison that produced the verdict.
    """
    resolved = resolve_test(test_name)
    definition = resolved[0] if resolved else None
    matched_by = resolved[1] if resolved else None
    display_name = definition.canonical_name if definition else test_name.strip()

    # --- qualitative path -------------------------------------------------
    observed_word = normalize_qualitative(value)
    expected_word = normalize_qualitative(reference_text)

    if observed_word is not None and expected_word is not None:
        return _classify_qualitative(
            display_name, value, unit, observed_word, expected_word,
            reference_text, matched_by, definition,
        )

    # --- numeric path -----------------------------------------------------
    number, qualifier, error = _parse_value(value)
    if error is not None:
        if observed_word is not None:
            error = (
                f"{display_name} reported {str(value).strip()!r}, a qualitative "
                "result, but no expected value was supplied to compare it "
                "against."
            )
        elif definition is None:
            error = f"No reference range is defined for {test_name!r}."
        return _failed(display_name, value, unit, error, matched_by=matched_by,
                       known_tests=None if definition else list_known_tests())

    reference, range_source, critical_basis = _select_range(
        definition, reference_low, reference_high
    )

    if reference is None:
        return _failed(
            display_name, number, unit,
            f"No reference range is defined for {test_name!r}, and none was "
            "supplied with the result.",
            matched_by=matched_by, known_tests=list_known_tests(),
        )

    # Units are only checked against our own table. A range that arrived with
    # the result came from the same row as the value, so they already agree.
    unit_assumed = not normalize_unit(unit)
    if range_source == "internal" and definition is not None:
        if not unit_is_compatible(definition, unit):
            return _failed(
                display_name, number, unit,
                f"Unit {unit!r} is not comparable to the reference range for "
                f"{definition.canonical_name} ({definition.unit}). "
                "Convert the value before submitting it.",
                matched_by=matched_by,
            )
    if range_source == "supplied" and unit:
        reference["unit"] = unit
        unit_assumed = False

    severity, band, rule = _apply_thresholds(number, reference)
    direction, deviation_pct, deviation_text = _describe_deviation(number, reference)

    result: dict[str, Any] = {
        "test_name": display_name,
        "value": number,
        "unit": unit or reference["unit"] or None,
        "severity": severity,
        "band": band,
        "reference_range": reference,
        "range_source": range_source,
        "critical_basis": critical_basis,
        "comparison": "numeric",
        "direction": direction,
        "deviation_pct": deviation_pct,
        "deviation_text": deviation_text,
        "rule_fired": rule,
        "matched_by": matched_by,
        "unit_assumed": unit_assumed,
        "category": definition.category if definition else "General",
        "specialty": definition.specialty if definition else "internal medicine",
        "measures": definition.measures if definition else "",
        "notes": None,
        "error": None,
    }

    notes: list[str] = []
    if qualifier:
        result["value_qualifier"] = qualifier
        notes.append(
            f"Reported as {qualifier}{number:g} - a censored result at the "
            "limit of measurement, classified using the stated limit."
        )
    if matched_by == "fuzzy":
        notes.append(
            f"Test name {test_name!r} was matched approximately to "
            f"{display_name!r}. Verify this is correct."
        )
    if range_source == "supplied":
        notes.append(
            "Classified against the reference interval supplied with the "
            "result rather than the built-in table."
        )
    if critical_basis == "derived" and severity == "critical":
        notes.append(
            "The critical threshold was estimated from the supplied interval, "
            "not from a published panic value. Treat the critical flag as "
            "indicative."
        )
    if notes:
        result["notes"] = " ".join(notes)

    return result


def _classify_qualitative(
    display_name: str,
    raw_value: Any,
    unit: str | None,
    observed: str,
    expected: str,
    reference_text: str | None,
    matched_by: str | None,
    definition: TestDefinition | None,
) -> dict[str, Any]:
    """Compare a word result against a word reference.

    Urinalysis strips report "Negatif", "Normal" or graded positives like
    "1+". A match is Normal; a mismatch is a Warning, never Critical - the
    strip records presence, not magnitude, so it cannot support a claim of
    immediate danger on its own.
    """
    matches = observed == expected
    severity = "normal" if matches else "warning"

    return {
        "test_name": display_name,
        "value": str(raw_value).strip(),
        "unit": unit or None,
        "severity": severity,
        "band": "normal" if matches else "qualitative_abnormal",
        "reference_range": None,
        "range_source": "supplied",
        "critical_basis": "none",
        "comparison": "qualitative",
        "direction": "within" if matches else "differs",
        "deviation_pct": None,
        "deviation_text": (
            f"matches the expected result ({reference_text})"
            if matches
            else f"differs from the expected result ({reference_text})"
        ),
        "rule_fired": (
            f"observed ({observed}) == expected ({expected})"
            if matches
            else f"observed ({observed}) != expected ({expected})"
        ),
        "matched_by": matched_by,
        "unit_assumed": False,
        "category": definition.category if definition else "Urinalysis",
        "specialty": definition.specialty if definition else "internal medicine",
        "measures": definition.measures if definition else
            "a qualitative screening result reported as present or absent",
        "notes": (
            None if matches else
            "Qualitative result: the strip records presence, not amount, so an "
            "abnormal finding is flagged as a warning pending a quantitative test."
        ),
        "error": None,
    }


def _apply_thresholds(value: float, reference: dict[str, Any]) -> tuple[str, str, str]:
    """Compare a value to the five bands.

    Returns ``(severity, band, rule_fired)``. ``rule_fired`` is the literal
    comparison that decided the verdict, so a user can check the arithmetic
    themselves - this is the core of the explainability requirement.

    Boundaries are inclusive of normal: ``low <= value <= high`` is Normal.
    """
    low = reference["low"]
    high = reference["high"]
    critical_low = reference["critical_low"]
    critical_high = reference["critical_high"]

    if critical_low is not None and value < critical_low:
        return ("critical", "critical_low",
                f"value ({value:g}) < critical_low ({critical_low:g})")

    if value < low:
        return ("warning", "warning_low",
                f"critical_low ({critical_low:g}) <= value ({value:g}) < low ({low:g})"
                if critical_low is not None
                else f"value ({value:g}) < low ({low:g}), no critical_low defined")

    if critical_high is not None and value > critical_high:
        return ("critical", "critical_high",
                f"value ({value:g}) > critical_high ({critical_high:g})")

    if value > high:
        return ("warning", "warning_high",
                f"high ({high:g}) < value ({value:g}) <= critical_high ({critical_high:g})"
                if critical_high is not None
                else f"value ({value:g}) > high ({high:g}), no critical_high defined")

    return ("normal", "normal",
            f"low ({low:g}) <= value ({value:g}) <= high ({high:g})")


def _describe_deviation(
    value: float, reference: dict[str, Any]
) -> tuple[str, float, str]:
    """Quantify how far outside the normal range a value sits.

    Percentages are relative to the limit that was crossed, which is how
    clinicians describe a result ("30% above the upper limit"), rather than
    relative to the midpoint of the range.
    """
    low, high, unit = reference["low"], reference["high"], reference["unit"]

    if value < low:
        pct = round((low - value) / low * 100, 1) if low else 0.0
        return "below", pct, f"{pct:g}% below the lower limit of normal ({low:g} {unit})".strip()

    if value > high:
        pct = round((value - high) / high * 100, 1) if high else 0.0
        return "above", pct, f"{pct:g}% above the upper limit of normal ({high:g} {unit})".strip()

    return "within", 0.0, f"within the normal range ({low:g}-{high:g} {unit})".strip()


# ---------------------------------------------------------------------------
# Tool 3 - routing
# ---------------------------------------------------------------------------

def route_by_severity(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Group and order classified results by clinical urgency.

    This is the Route step. Critical results come first, then warnings, then
    normals, then anything uninterpretable. Within a group the most deviant
    value leads, so the worst result in each band is seen first.

    Returns the flat ordered list the frontend renders, the same results
    grouped by severity, and a count summary.
    """
    groups: dict[str, list[dict[str, Any]]] = {s: [] for s in SEVERITY_ORDER}

    for item in results:
        severity = item.get("severity", "unknown")
        groups.setdefault(severity, []).append(item)

    for severity in groups:
        groups[severity].sort(
            key=lambda r: (r.get("deviation_pct") or 0.0), reverse=True
        )

    ordered = [item for severity in SEVERITY_ORDER for item in groups[severity]]

    summary = {severity: len(groups[severity]) for severity in SEVERITY_ORDER}
    summary["total"] = len(results)
    summary["abnormal"] = summary["critical"] + summary["warning"]

    return {
        "ordered": ordered,
        "groups": groups,
        "summary": summary,
        "highest_severity": next(
            (s for s in SEVERITY_ORDER if groups[s]), "normal"
        ),
    }
