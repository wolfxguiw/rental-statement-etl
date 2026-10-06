"""Folder discovery and independent PDF batch processing."""

from hashlib import sha256
from pathlib import Path
import re

from .diagnostics import write_diagnostics
from .errors import (
    ExtractionError,
    FolderInputError,
    OutputAlreadyExistsError,
    PdfReadError,
    ValidationError,
)
from .excel_writer import write_rental_workbook
from .models import BatchReport, ProcessingIssue, ProcessingWarning, RentalRecord
from .parser import extract_pdf_events
from .validation import validate_record


_PERIOD_RE = re.compile(r"(?:0[1-9]|1[0-2])-\d{4}")


def _relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_pdfs(root: str | Path, recursive: bool = True) -> list[Path]:
    """Return PDF paths under an existing folder in stable path order."""

    root = Path(root)
    if not root.exists() or not root.is_dir():
        raise FolderInputError(f"pasta de entrada inexistente: {root}")
    root = root.resolve()
    candidates = root.rglob("*") if recursive else root.iterdir()
    return sorted(
        (path for path in candidates if path.is_file() and path.suffix.lower() == ".pdf"),
        key=lambda path: path.relative_to(root).as_posix().casefold(),
    )


def process_folder(
    input_folder: str | Path,
    *,
    output_path: str | Path | None = None,
    report_period: str | None = None,
    recursive: bool = True,
    overwrite: bool = False,
    diagnostics_path: str | Path | None = None,
) -> BatchReport:
    """Process each PDF independently and write a workbook plus diagnostics.

    ``report_period`` is optional ``MM-YYYY`` metadata supplied by the caller.
    It is never inferred from PDF issue dates or contract competence fields.
    """

    root = Path(input_folder)
    if not root.exists() or not root.is_dir():
        raise FolderInputError(f"pasta de entrada inexistente: {root}")
    root = root.resolve()

    if report_period is not None and not _PERIOD_RE.fullmatch(report_period):
        raise ValueError("período deve usar MM-AAAA, por exemplo 09-2026")
    if output_path is None:
        suffix = f"_{report_period}" if report_period else ""
        target = root / f"Relatorio_Alugueis{suffix}.xlsx"
    else:
        target = Path(output_path).resolve()
    if target.suffix.lower() != ".xlsx":
        raise ValueError("o caminho de saída deve terminar em .xlsx")
    if target.exists() and not overwrite:
        raise OutputAlreadyExistsError(f"arquivo de saída já existe: {target}")

    sidecar = (
        Path(diagnostics_path).resolve()
        if diagnostics_path is not None
        else target.with_suffix(".diagnostics.json")
    )
    if sidecar == target:
        raise ValueError("o arquivo de diagnósticos deve ser diferente do Excel")

    pdfs = find_pdfs(root, recursive=recursive)
    records: list[RentalRecord] = []
    errors: list[ProcessingIssue] = []
    warnings: list[ProcessingWarning] = []
    seen_hashes: dict[str, str] = {}

    for pdf_path in pdfs:
        relative = _relative_path(pdf_path, root)
        try:
            file_hash = _sha256(pdf_path)
        except OSError as exc:
            errors.append(ProcessingIssue(relative, "file_read", f"não foi possível ler arquivo: {exc}"))
            continue
        previous_file = seen_hashes.get(file_hash)
        if previous_file is not None:
            warnings.append(
                ProcessingWarning(
                    relative,
                    f"PDF binariamente idêntico a {previous_file}; esta cópia foi ignorada.",
                )
            )
            continue
        seen_hashes[file_hash] = relative

        try:
            parsed_events = extract_pdf_events(pdf_path)
        except PdfReadError as exc:
            errors.append(ProcessingIssue(relative, "pdf_read", str(exc)))
            continue
        except ExtractionError as exc:
            errors.append(ProcessingIssue(relative, "parser", str(exc)))
            continue

        validated_events: list[RentalRecord] = []
        validation_error: ValidationError | None = None
        for parsed in parsed_events:
            try:
                record = validate_record(parsed)
            except ValidationError as exc:
                validation_error = exc
                break
            validated_events.append(
                RentalRecord(
                    source_file=record.source_file,
                    cpf=record.cpf,
                    name=record.name,
                    rent=record.rent,
                    source_path=relative,
                    category=record.category,
                    original_history=record.original_history,
                )
            )
        if validation_error is not None:
            errors.append(ProcessingIssue(relative, "validation", str(validation_error)))
            continue
        records.extend(validated_events)

    report = BatchReport(
        input_folder=root,
        output_path=target,
        diagnostics_path=sidecar,
        total_pdfs=len(pdfs),
        records=records,
        errors=errors,
        warnings=warnings,
    )
    write_rental_workbook(records, target, overwrite=overwrite)
    write_diagnostics(report)
    return report
