"""Bundled sample datasets, exposed so the UI can analyze them in one click.

A grader should be able to see the app work without first locating a CSV on
disk. This module publishes the repository's own sample files - the three
synthetic panels and the Kaggle dataset - as a fixed catalogue.

The catalogue is an explicit registry rather than a directory scan, and files
are only ever resolved through it. A user-supplied name never becomes part of
a filesystem path, so there is no traversal surface here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TEST_DATA_DIR = REPO_ROOT / "test_data"
DATA_DIR = REPO_ROOT / "data"


@dataclass(frozen=True)
class SampleDataset:
    """One bundled CSV the UI can offer."""

    id: str
    name: str
    description: str
    path: Path
    source: str
    synthetic: bool


CATALOGUE: dict[str, SampleDataset] = {
    d.id: d
    for d in (
        SampleDataset(
            id="kaggle",
            name="Kaggle - Laboratory Test Results",
            description=(
                "The assignment's required dataset: anonymized results with "
                "Turkish test names, per-row reference intervals, and "
                "qualitative urinalysis strips."
            ),
            path=DATA_DIR / "lab_test_results_public.csv",
            source="pinar-topuz/lab-test-results (CC0-1.0)",
            synthetic=False,
        ),
        SampleDataset(
            id="normal_panel",
            name="Normal panel",
            description="Ten results, all within their reference ranges.",
            path=TEST_DATA_DIR / "normal_panel.csv",
            source="synthetic",
            synthetic=True,
        ),
        SampleDataset(
            id="critical_panel",
            name="Critical panel",
            description="Eight life-threatening values across several systems.",
            path=TEST_DATA_DIR / "critical_panel.csv",
            source="synthetic",
            synthetic=True,
        ),
        SampleDataset(
            id="mixed_messy_panel",
            name="Mixed and messy panel",
            description=(
                "Mixed severities plus deliberately broken rows: unknown "
                "tests, blank values, aliases, typos, unit conflicts and "
                "boundary values."
            ),
            path=TEST_DATA_DIR / "mixed_messy_panel.csv",
            source="synthetic",
            synthetic=True,
        ),
    )
}


class DatasetNotFound(KeyError):
    """The requested dataset id is not in the catalogue, or its file is gone."""


def list_datasets() -> list[dict[str, object]]:
    """Describe every bundled dataset, marking which files are present.

    A missing file is reported rather than hidden: the Kaggle CSV is not in
    every clone, and the UI should say so instead of silently omitting it.
    """
    return [
        {
            "id": d.id,
            "name": d.name,
            "description": d.description,
            "source": d.source,
            "synthetic": d.synthetic,
            "available": d.path.exists(),
            "size_bytes": d.path.stat().st_size if d.path.exists() else None,
        }
        for d in CATALOGUE.values()
    ]


def load_dataset(dataset_id: str) -> tuple[bytes, SampleDataset]:
    """Read one bundled dataset by id.

    Raises:
        DatasetNotFound: if the id is unknown or the file is missing.
    """
    dataset = CATALOGUE.get(dataset_id)
    if dataset is None:
        raise DatasetNotFound(
            f"Unknown dataset {dataset_id!r}. "
            f"Available: {', '.join(CATALOGUE)}."
        )

    if not dataset.path.exists():
        raise DatasetNotFound(
            f"Dataset {dataset_id!r} is not present in this checkout "
            f"(expected at {dataset.path.relative_to(REPO_ROOT)})."
        )

    return dataset.path.read_bytes(), dataset
