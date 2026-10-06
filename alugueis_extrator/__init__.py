"""Deterministic, local processing of rental statement folders."""

from .app_version import APP_VERSION
from .batch import find_pdfs, process_folder
from .errors import ExtractionError, FolderInputError, OutputAlreadyExistsError
from .models import BatchReport, RentalRecord
from .parser import extract_pdf, extract_pdf_events
from .rubrics import RubricClassification, classify_history
from .validation import is_valid_cpf, validate_record

__all__ = [
    "BatchReport",
    "APP_VERSION",
    "ExtractionError",
    "FolderInputError",
    "OutputAlreadyExistsError",
    "RentalRecord",
    "RubricClassification",
    "classify_history",
    "extract_pdf",
    "extract_pdf_events",
    "find_pdfs",
    "is_valid_cpf",
    "process_folder",
    "validate_record",
]
