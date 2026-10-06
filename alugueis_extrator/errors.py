"""Typed failures shared by the PDF and batch layers."""


class ExtractionError(ValueError):
    """A document field is absent, invalid, ambiguous, or unsupported."""


class PdfReadError(ExtractionError):
    """The source file could not be opened as a supported PDF."""


class FolderInputError(ValueError):
    """The batch input path is not an existing directory."""


class OutputAlreadyExistsError(FileExistsError):
    """Refuse to overwrite an existing workbook unless explicitly requested."""


class WorkbookWriteError(OSError):
    """The workbook or its diagnostics could not be saved."""


class ValidationError(ValueError):
    """An extracted record failed business validation."""
