"""CSV ingestion: raw upload -> validated list[LabInput].

Handles the messy part of real data: differing column names
(`test`/`test_name`/`Test Name`), stray whitespace, blank rows,
non-numeric values, and missing units.

TODO(step 6): parse_csv(bytes) -> tuple[list[LabInput], list[RowError]].
"""
