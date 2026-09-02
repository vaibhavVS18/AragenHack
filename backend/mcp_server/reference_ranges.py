"""Clinical reference range table - the built-in source of truth.

Every threshold defined in this application lives here and nowhere else, so
changing clinical policy is a data edit rather than a code change.

Each test defines four thresholds producing five severity bands::

        critical_low      low            high        critical_high
   ---------+--------------+--------------+--------------+---------
   CRITICAL |   WARNING    |    NORMAL    |   WARNING    | CRITICAL
     (low)  |    (low)     |              |   (high)     |  (high)

Boundaries are INCLUSIVE of normal: a value exactly equal to ``low`` or ``high``
is Normal. ``critical_low``/``critical_high`` may be ``None``, meaning that side
has no life-threatening band (a very low creatinine is not an emergency).

This table is not the only source of ranges. A caller may supply the interval
that came with the result - the Kaggle dataset ships ``Min_Reference`` and
``Max_Reference`` per row - and that takes precedence, because a laboratory's
own interval is authoritative for its own result. See ``tools.py`` for how the
two are combined.

Ranges here are adult and sex-agnostic; see docs/03-classification-logic.md for
the full list of documented assumptions.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

# Minimum similarity for a fuzzy test-name match. Deliberately strict: a wrong
# match would silently classify against the wrong range, which is far worse
# than reporting the test as unknown.
FUZZY_MATCH_CUTOFF = 0.82

# Turkish characters, folded to ASCII so dataset names match our aliases.
# An explicit map rather than unicodedata: "ı" and "İ" do not decompose the way
# the other diacritics do, and getting them wrong silently breaks matching for
# every test whose name contains them.
TURKISH_FOLD = str.maketrans({
    "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
    "ö": "o", "Ö": "o", "ü": "u", "Ü": "u", "ç": "c", "Ç": "c",
    "â": "a", "î": "i", "û": "u",
})

# Qualitative results (urinalysis strips) are compared as words, not numbers.
# Each spelling maps to a canonical token so "Negatif", "negative" and "neg"
# all compare equal.
QUALITATIVE_SYNONYMS: dict[str, str] = {
    "negatif": "negative",
    "negative": "negative",
    "neg": "negative",
    "yok": "negative",
    "pozitif": "positive",
    "positive": "positive",
    "pos": "positive",
    "var": "positive",
    "normal": "normal",
    "normalde": "normal",
    "eser": "trace",
    "trace": "trace",
    "iz": "trace",
}


@dataclass(frozen=True)
class TestDefinition:
    """Clinical definition of a single lab test."""

    canonical_name: str
    unit: str
    low: float
    high: float
    critical_low: float | None = None
    critical_high: float | None = None

    # Context, not thresholds. Passed to the LLM so explanations are grounded
    # and next-step suggestions can name the right specialty.
    category: str = "General"
    specialty: str = "internal medicine"
    measures: str = ""

    # Alternative spellings, abbreviations and dataset-specific labels,
    # including the Turkish names used by the Kaggle dataset.
    aliases: tuple[str, ...] = field(default_factory=tuple)
    # Accepted unit spellings, already normalized (lowercase, no spaces).
    unit_aliases: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------

REFERENCE_RANGES: dict[str, TestDefinition] = {
    "hemoglobin": TestDefinition(
        canonical_name="Hemoglobin",
        unit="g/dL",
        critical_low=7.0, low=12.0, high=17.5, critical_high=20.0,
        category="Hematology",
        specialty="hematology",
        measures="oxygen-carrying capacity of the blood",
        aliases=("hgb", "hb", "haemoglobin", "hemoglobin hgb", "blood hemoglobin"),
        unit_aliases=("g/dl", "gm/dl", "g/100ml", "gdl"),
    ),
    "white blood cell count": TestDefinition(
        canonical_name="White Blood Cell Count",
        unit="10^3/uL",
        critical_low=2.0, low=4.5, high=11.0, critical_high=30.0,
        category="Hematology",
        specialty="hematology",
        measures="immune cells that fight infection",
        aliases=("wbc", "wbc count", "leukocytes", "leukocyte count",
                 "white blood cells", "total leukocyte count", "tlc",
                 "lokosit", "beyaz kure"),
        unit_aliases=("10^3/ul", "10*3/ul", "x10^3/ul", "k/ul", "10e3/ul",
                      "thou/ul", "10^9/l", "cells/ul"),
    ),
    "platelet count": TestDefinition(
        canonical_name="Platelet Count",
        unit="10^3/uL",
        critical_low=50.0, low=150.0, high=450.0, critical_high=1000.0,
        category="Hematology",
        specialty="hematology",
        measures="cells responsible for blood clotting",
        aliases=("platelets", "plt", "plt count", "thrombocytes",
                 "thrombocyte count", "trombosit"),
        unit_aliases=("10^3/ul", "10*3/ul", "x10^3/ul", "k/ul", "10e3/ul",
                      "thou/ul", "10^9/l"),
    ),
    "red blood cell count": TestDefinition(
        canonical_name="Red Blood Cell Count",
        unit="10^6/uL",
        critical_low=2.5, low=4.2, high=5.9, critical_high=None,
        category="Hematology",
        specialty="hematology",
        measures="number of oxygen-carrying red cells",
        aliases=("rbc", "rbc count", "erythrocytes", "erythrocyte count",
                 "eritrosit", "red blood cells"),
        unit_aliases=("10^6/ul", "10*6/ul", "x10^6/ul", "m/ul", "10e6/ul",
                      "mil/ul", "10^12/l"),
    ),
    "hematocrit": TestDefinition(
        canonical_name="Hematocrit",
        unit="%",
        critical_low=21.0, low=36.0, high=50.0, critical_high=60.0,
        category="Hematology",
        specialty="hematology",
        measures="proportion of blood volume occupied by red cells",
        aliases=("hct", "haematocrit", "pcv", "packed cell volume",
                 "hematokrit"),
        unit_aliases=("%", "percent", "pct"),
    ),
    "glucose": TestDefinition(
        canonical_name="Glucose",
        unit="mg/dL",
        critical_low=50.0, low=70.0, high=99.0, critical_high=400.0,
        category="Chemistry",
        specialty="endocrinology",
        measures="blood sugar level (fasting)",
        aliases=("blood glucose", "fasting glucose", "glucose fasting",
                 "fbs", "fasting blood sugar", "blood sugar", "glu",
                 "glukoz", "kan sekeri"),
        unit_aliases=("mg/dl", "mgdl", "mg/100ml"),
    ),
    "hba1c": TestDefinition(
        canonical_name="HbA1c",
        unit="%",
        critical_low=None, low=4.0, high=5.7, critical_high=10.0,
        category="Chemistry",
        specialty="endocrinology",
        measures="average blood sugar over the previous 2-3 months",
        aliases=("glycated hemoglobin", "glycosylated hemoglobin",
                 "hemoglobin a1c", "a1c", "glikozile hemoglobin hba1c",
                 "glikozile hemoglobin"),
        unit_aliases=("%", "percent", "mmol/mol"),
    ),
    "potassium": TestDefinition(
        canonical_name="Potassium",
        unit="mEq/L",
        critical_low=2.5, low=3.5, high=5.1, critical_high=6.5,
        category="Chemistry",
        specialty="nephrology",
        measures="electrolyte essential for cardiac and muscle function",
        aliases=("k", "k+", "serum potassium", "potassium serum", "potasyum"),
        unit_aliases=("meq/l", "mmol/l", "mval/l"),
    ),
    "sodium": TestDefinition(
        canonical_name="Sodium",
        unit="mEq/L",
        critical_low=120.0, low=135.0, high=145.0, critical_high=160.0,
        category="Chemistry",
        specialty="nephrology",
        measures="electrolyte governing fluid balance and nerve function",
        aliases=("na", "na+", "serum sodium", "sodium serum", "sodyum"),
        unit_aliases=("meq/l", "mmol/l", "mval/l"),
    ),
    "creatinine": TestDefinition(
        canonical_name="Creatinine",
        unit="mg/dL",
        critical_low=None, low=0.6, high=1.3, critical_high=4.0,
        category="Chemistry",
        specialty="nephrology",
        measures="kidney filtration efficiency",
        aliases=("creat", "serum creatinine", "cr", "s. creatinine",
                 "kreatinin"),
        unit_aliases=("mg/dl", "mgdl", "mg/100ml"),
    ),
    "calcium": TestDefinition(
        canonical_name="Calcium",
        unit="mg/dL",
        critical_low=6.0, low=8.5, high=10.5, critical_high=13.0,
        category="Chemistry",
        specialty="endocrinology",
        measures="mineral required for bone, nerve and cardiac function",
        aliases=("ca", "ca2+", "serum calcium", "total calcium", "kalsiyum"),
        unit_aliases=("mg/dl", "mgdl", "mg/100ml"),
    ),
    "ferritin": TestDefinition(
        canonical_name="Ferritin",
        unit="ug/L",
        critical_low=None, low=15.0, high=200.0, critical_high=1000.0,
        category="Chemistry",
        specialty="hematology",
        measures="the body's stored iron",
        aliases=("serum ferritin", "ferritin serum"),
        unit_aliases=("ug/l", "mcg/l", "ng/ml"),
    ),
    "tsh": TestDefinition(
        canonical_name="TSH",
        unit="uIU/mL",
        critical_low=0.1, low=0.4, high=4.0, critical_high=20.0,
        category="Endocrine",
        specialty="endocrinology",
        measures="pituitary signal controlling thyroid hormone production",
        aliases=("thyroid stimulating hormone", "thyrotropin",
                 "thyroid-stimulating hormone"),
        unit_aliases=("uiu/ml", "miu/l", "mciu/ml"),
    ),
    "free t4": TestDefinition(
        canonical_name="Free T4",
        unit="ng/dL",
        critical_low=0.2, low=0.8, high=1.8, critical_high=5.0,
        category="Endocrine",
        specialty="endocrinology",
        measures="unbound thyroid hormone available to tissues",
        aliases=("ft4", "free thyroxine", "t4 free", "serbest t4"),
        unit_aliases=("ng/dl", "pmol/l"),
    ),
    "insulin": TestDefinition(
        canonical_name="Insulin",
        unit="mU/L",
        critical_low=None, low=2.6, high=24.9, critical_high=None,
        category="Endocrine",
        specialty="endocrinology",
        measures="the hormone that moves glucose into cells",
        aliases=("fasting insulin", "serum insulin", "insulin fasting"),
        unit_aliases=("mu/l", "uiu/ml", "miu/l", "pmol/l"),
    ),
    "alt": TestDefinition(
        canonical_name="ALT",
        unit="U/L",
        critical_low=None, low=7.0, high=56.0, critical_high=300.0,
        category="Liver",
        specialty="hepatology",
        measures="liver enzyme released when liver cells are damaged",
        aliases=("sgpt", "alanine aminotransferase", "alt sgpt",
                 "alanine transaminase"),
        unit_aliases=("u/l", "iu/l", "units/l"),
    ),
}


# ---------------------------------------------------------------------------
# Name and unit normalization
# ---------------------------------------------------------------------------

def normalize_name(raw: str) -> str:
    """Fold a user-supplied test name into a comparable form.

    Folds Turkish characters to ASCII, lowercases, strips punctuation and
    collapses whitespace, so ``"  Lökosit "``, ``"lokosit"`` and
    ``"  Hemoglobin (HGB) "`` all compare as expected.
    """
    text = raw.strip().translate(TURKISH_FOLD).lower()
    # Keep +, ^, / and . so that "K+", "10^3/uL" and "s. creatinine" survive.
    text = re.sub(r"[^a-z0-9+^/. ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_unit(raw: str | None) -> str:
    """Fold a unit string: lowercase, all whitespace removed."""
    if not raw:
        return ""
    text = re.sub(r"\s+", "", raw.strip().lower())
    # Accept the micro sign and Greek mu as plain "u" (uL, uIU/mL).
    return text.replace("µ", "u").replace("μ", "u")


def normalize_qualitative(raw: str | None) -> str | None:
    """Fold a qualitative result or reference to a canonical token.

    Urinalysis strips report words, not numbers: "Negatif", "Normal", "1+".
    Returns ``None`` when the text is not a recognised qualitative term, which
    is how callers tell a word result apart from a failed number.
    """
    if raw is None:
        return None

    text = normalize_name(str(raw))
    if not text:
        return None

    if text in QUALITATIVE_SYNONYMS:
        return QUALITATIVE_SYNONYMS[text]

    # Graded positives: "1+", "2+", "3+" all mean present, to differing degrees.
    if re.fullmatch(r"[1-4]\s*\+", text.replace(" ", "")):
        return "positive"

    return None


# Built once at import time: every alias and canonical name -> table key.
_ALIAS_INDEX: dict[str, str] = {}
for _key, _definition in REFERENCE_RANGES.items():
    _ALIAS_INDEX[normalize_name(_key)] = _key
    _ALIAS_INDEX[normalize_name(_definition.canonical_name)] = _key
    for _alias in _definition.aliases:
        _ALIAS_INDEX[normalize_name(_alias)] = _key


def resolve_test(raw_name: str) -> tuple[TestDefinition, str] | None:
    """Resolve a possibly-messy test name to its definition.

    Returns ``(definition, matched_by)`` where ``matched_by`` is one of
    ``"exact"``, ``"alias"`` or ``"fuzzy"``, or ``None`` when unrecognised.

    Tiers are tried in descending order of confidence, and the tier is reported
    back so the UI can present a fuzzy match as an assumption rather than fact.
    """
    if not raw_name or not raw_name.strip():
        return None

    normalized = normalize_name(raw_name)

    # Tier 1 - the canonical name itself.
    if normalized in REFERENCE_RANGES:
        return REFERENCE_RANGES[normalized], "exact"

    # Tier 2 - a known alias or abbreviation.
    if normalized in _ALIAS_INDEX:
        key = _ALIAS_INDEX[normalized]
        definition = REFERENCE_RANGES[key]
        is_canonical = normalized == normalize_name(definition.canonical_name)
        return definition, ("exact" if is_canonical else "alias")

    # Tier 3 - typo tolerance, strict cutoff.
    close = difflib.get_close_matches(
        normalized, list(_ALIAS_INDEX.keys()), n=1, cutoff=FUZZY_MATCH_CUTOFF
    )
    if close:
        return REFERENCE_RANGES[_ALIAS_INDEX[close[0]]], "fuzzy"

    return None


def unit_is_compatible(definition: TestDefinition, raw_unit: str | None) -> bool:
    """True when ``raw_unit`` may be compared against this range.

    A missing unit counts as compatible - the caller assumes the canonical unit
    and flags the assumption. A *conflicting* unit is never silently converted:
    comparing mmol/L against a mg/dL range produces a confidently wrong answer,
    so callers refuse to classify instead.
    """
    normalized = normalize_unit(raw_unit)
    if not normalized:
        return True
    return (normalized == normalize_unit(definition.unit)
            or normalized in definition.unit_aliases)


def list_known_tests() -> list[str]:
    """Canonical names of every test in the table, for errors and UI hints."""
    return [d.canonical_name for d in REFERENCE_RANGES.values()]
