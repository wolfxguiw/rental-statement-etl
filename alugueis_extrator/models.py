"""Data objects shared by parser, validation, and batch processing."""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .rubrics import RubricClassification


@dataclass(frozen=True)
class RentalRecord:
    """A validated financial event with tenant and source traceability."""

    source_file: str
    cpf: str
    name: str
    rent: Decimal
    source_path: str | None = None
    category: RubricClassification = RubricClassification.ALUGUEL
    original_history: str = "Aluguel"


@dataclass(frozen=True)
class ProcessingIssue:
    file: str
    stage: str
    reason: str


@dataclass(frozen=True)
class ProcessingWarning:
    file: str
    reason: str


@dataclass
class BatchReport:
    input_folder: Path
    output_path: Path
    diagnostics_path: Path
    total_pdfs: int
    records: list[RentalRecord]
    errors: list[ProcessingIssue]
    warnings: list[ProcessingWarning]

    @property
    def processed(self) -> int:
        """Number of distinct source PDFs that produced at least one record."""

        return len({record.source_path or record.source_file for record in self.records})

    @property
    def records_generated(self) -> int:
        return len(self.records)

    @property
    def review_count(self) -> int:
        return len(self.errors)
