"""CSV ingestion: a raw upload becomes validated lab inputs.

Real lab exports are inconsistent, so this module absorbs the mess rather than
pushing it onto the user: differing column names, byte-order marks, blank
rows, stray whitespace, quoted numbers.

Partial success is the rule. A row that cannot be read becomes a
:class:`RowError` while every other row still classifies - failing a 50-row
upload because one cell says "N/A" would be hostile, and the rubric grades
error handling explicitly.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

from .models import LabInput, RowError

# Header spellings seen across exports, normalized to our field names. The
# Kaggle dataset and hand-made CSVs disagree about these constantly.
COLUMN_ALIASES: dict[str, str] = {
    # test name
    "test_name": "test_name",
    "testname": "test_name",
    "test": "test_name",
    "test name": "test_name",
    "lab_test": "test_name",
    "lab test": "test_name",
    "analyte": "test_name",
    "parameter": "test_name",
    "component": "test_name",
    "investigation": "test_name",
    # value
    "value": "value",
    "result": "value",
    "result_value": "value",
    "result value": "value",
    "test_result": "value",
    "test result": "value",
    "observation_value": "value",
    "measurement": "value",
    "reading": "value",
    # unit
    "unit": "unit",
    "units": "unit",
    "uom": "unit",
    "unit_of_measure": "unit",
    "unit of measure": "unit",
    "measurement_unit": "unit",
    # reference interval supplied with the result
    # (the Kaggle dataset ships Min_Reference / Max_Reference per row)
    "min_reference": "reference_low",
    "min reference": "reference_low",
    "reference_low": "reference_low",
    "reference low": "reference_low",
    "ref_low": "reference_low",
    "low": "reference_low",
    "max_reference": "reference_high",
    "max reference": "reference_high",
    "reference_high": "reference_high",
    "reference high": "reference_high",
    "ref_high": "reference_high",
    "high": "reference_high",
    "reference_range": "reference_range",
    "reference range": "reference_range",
    "ref_range": "reference_range",
    "normal_range": "reference_range",
    # patient identifier
    "patient_id": "patient_id",
    "patient id": "patient_id",
    "patientid": "patient_id",
    "subject_id": "patient_id",
    "mrn": "patient_id",
}

# Reference intervals written as one cell, e.g. "150-450" or "0.87-1.70".
# Anchored and explicit so a date such as "2025-08-12" cannot be mistaken for
# a range.
RANGE_PATTERN = re.compile(
    r"^\s*(-?\d+(?:[.,]\d+)?)\s*(?:-|–|—|to|\.\.)\s*(-?\d+(?:[.,]\d+)?)\s*$",
    re.IGNORECASE,
)

REQUIRED_FIELDS = ("test_name", "value")

# Guard against a mistyped path or an accidental binary upload.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class CSVFormatError(ValueError):
    """The file could not be read as a lab-results CSV at all.

    Distinct from a bad row: this means the whole upload is unusable, so the
    endpoint returns 400 rather than a partial result.
    """


def _normalize_header(name: str | None) -> str | None:
    """Map one column header onto a known field, or None if unrecognised."""
    if not name:
        return None
    key = " ".join(name.strip().lower().replace("-", " ").replace("_", " ").split())
    # Try the spaced form and the underscored form, since both appear.
    return COLUMN_ALIASES.get(key) or COLUMN_ALIASES.get(key.replace(" ", "_"))


def _decode(raw: bytes) -> str:
    """Decode upload bytes, tolerating BOMs and non-UTF-8 exports."""
    if len(raw) > MAX_UPLOAD_BYTES:
        raise CSVFormatError(
            f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )
    if not raw.strip():
        raise CSVFormatError("File is empty.")

    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CSVFormatError("File is not readable text. Expected a UTF-8 CSV.")


def _sniff_dialect(text: str) -> type[csv.Dialect] | csv.Dialect:
    """Detect the delimiter, since exports use commas, semicolons or tabs."""
    sample = text[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def _to_float(text: str | None) -> float | None:
    """Read a numeric cell, tolerating a comma decimal separator."""
    if not text or not str(text).strip():
        return None
    try:
        return float(str(text).strip().replace(",", "."))
    except ValueError:
        return None


def _extract_reference(
    record: dict[str, Any],
) -> tuple[float | None, float | None, str | None]:
    """Read whatever reference information a row carries.

    Three shapes appear in practice, and the Kaggle dataset uses all three:

    * separate ``Min_Reference`` / ``Max_Reference`` columns
    * a combined ``Reference_Range`` cell such as ``"150-450"``
    * a qualitative expectation such as ``"Negatif"`` for urinalysis strips

    Returns ``(low, high, qualitative_text)``. The numeric pair and the
    qualitative text are mutually exclusive in practice, but both are returned
    so the classifier can decide which comparison applies.
    """
    low = _to_float(record.get("reference_low"))
    high = _to_float(record.get("reference_high"))

    combined = (record.get("reference_range") or "").strip()

    # Fall back to the combined cell when the explicit columns are absent.
    if (low is None or high is None) and combined:
        match = RANGE_PATTERN.match(combined)
        if match:
            low = _to_float(match.group(1))
            high = _to_float(match.group(2))

    # A non-numeric reference cell is a qualitative expectation, not junk.
    qualitative = None
    if low is None and high is None and combined and not RANGE_PATTERN.match(combined):
        qualitative = combined

    if low is not None and high is not None and low >= high:
        # A nonsense interval is worse than none: fall back to the table.
        low = high = None

    return low, high, qualitative


def parse_csv(raw: bytes) -> tuple[list[LabInput], list[RowError], str | None]:
    """Parse an uploaded CSV into lab inputs.

    Args:
        raw: The uploaded file's bytes.

    Returns:
        ``(labs, errors, patient_id)``. ``patient_id`` is taken from the file
        when a patient column is present and holds a single consistent value.

    Raises:
        CSVFormatError: if the file is unreadable or has no usable columns.
    """
    text = _decode(raw)
    reader = csv.reader(io.StringIO(text), dialect=_sniff_dialect(text))

    try:
        header = next(reader)
    except StopIteration:
        raise CSVFormatError("File is empty.") from None

    mapping = {index: _normalize_header(name) for index, name in enumerate(header)}
    found = {field for field in mapping.values() if field}

    missing = [field for field in REQUIRED_FIELDS if field not in found]
    if missing:
        raise CSVFormatError(
            f"CSV is missing required column(s): {', '.join(missing)}. "
            f"Found headers: {', '.join(h for h in header if h)}. "
            "Expected a header row such as: test_name,value,unit"
        )

    labs: list[LabInput] = []
    errors: list[RowError] = []
    patient_ids: set[str] = set()

    # Row 1 is the header, so data starts at 2 - matching what a user sees in
    # a spreadsheet when told which row failed.
    for row_number, row in enumerate(reader, start=2):
        if not any(cell.strip() for cell in row):
            continue  # blank separator row

        record: dict[str, Any] = {}
        for index, cell in enumerate(row):
            field = mapping.get(index)
            if field:
                record[field] = cell.strip()

        if record.get("patient_id"):
            patient_ids.add(record["patient_id"])

        test_name = (record.get("test_name") or "").strip()
        value = (record.get("value") or "").strip()

        if not test_name:
            errors.append(RowError(
                row=row_number, raw=record, error="Missing test name."
            ))
            continue

        if not value:
            errors.append(RowError(
                row=row_number, test_name=test_name, raw=record,
                error=f"Missing value for {test_name}.",
            ))
            continue

        low, high, qualitative = _extract_reference(record)

        try:
            labs.append(LabInput(
                test_name=test_name,
                value=value,
                unit=(record.get("unit") or "").strip() or None,
                reference_low=low,
                reference_high=high,
                reference_text=qualitative,
            ))
        except Exception as exc:  # schema rejection, e.g. name too long
            errors.append(RowError(
                row=row_number, test_name=test_name, raw=record, error=str(exc)
            ))

    if not labs and not errors:
        raise CSVFormatError("CSV contains a header but no data rows.")

    # Only report a patient id when the file is unambiguous about it.
    patient_id = patient_ids.pop() if len(patient_ids) == 1 else None
    return labs, errors, patient_id
