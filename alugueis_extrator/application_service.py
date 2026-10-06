"""Application workflows shared by the desktop GUI and automated tests."""

from dataclasses import dataclass
from datetime import datetime
from itertools import count
from pathlib import Path
import re

from .app_version import APP_VERSION
from .batch import find_pdfs, process_folder
from .models import BatchReport


_COMPETENCE_RE = re.compile(r"(0[1-9]|1[0-2])/([0-9]{4})")


@dataclass(frozen=True)
class ApplicationRun:
    report: BatchReport
    log_path: Path | None
    log_error: str | None = None


def normalize_competence(value: str | None) -> str | None:
    """Convert the UI's optional MM/YYYY input to the core's MM-YYYY form."""

    entered = (value or "").strip()
    if not entered:
        return None
    match = _COMPETENCE_RE.fullmatch(entered)
    if match is None:
        raise ValueError("Informe a competência como MM/AAAA, por exemplo 09/2026.")
    if int(match.group(2)) < 1900:
        raise ValueError("O ano da competência deve ser igual ou posterior a 1900.")
    return f"{match.group(1)}-{match.group(2)}"


def report_filename(competence: str | None) -> str:
    """Return the standard user-facing workbook name for an optional period."""

    normalized = normalize_competence(competence)
    suffix = f"_{normalized}" if normalized else ""
    return f"Relatorio_Alugueis{suffix}.xlsx"


def unique_output_path(folder: str | Path, competence: str | None) -> Path:
    """Choose the first unused report/diagnostic/log name in the input folder."""

    root = Path(folder).resolve()
    filename = report_filename(competence)
    stem = Path(filename).stem
    for sequence in count(1):
        candidate_stem = stem if sequence == 1 else f"{stem}_{sequence}"
        candidate = root / f"{candidate_stem}.xlsx"
        companions = (
            candidate,
            candidate.with_suffix(".diagnostics.json"),
            candidate.with_suffix(".execution.log"),
        )
        if not any(path.exists() for path in companions):
            return candidate
    raise RuntimeError("não foi possível escolher um nome de saída disponível")


def count_pdf_files(folder: str | Path) -> int:
    """Count PDFs recursively using the same discovery rule as the batch core."""

    return len(find_pdfs(folder, recursive=True))


def _execution_log_text(report: BatchReport) -> str:
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        "Extrator de Demonstrativos de Aluguel",
        f"Data/hora: {timestamp}",
        f"Versão: {APP_VERSION}",
        f"Pasta escolhida: {report.input_folder}",
        f"PDFs encontrados: {report.total_pdfs}",
        f"Documentos processados: {report.processed}",
        f"Registros gerados: {report.records_generated}",
        f"Documentos para revisão/erro: {report.review_count}",
        f"Avisos: {len(report.warnings)}",
        f"Excel: {report.output_path.name}",
    ]
    if report.errors:
        lines.extend(("", "Erros/revisão:"))
        lines.extend(
            f"- {issue.file} | etapa={issue.stage} | {issue.reason}"
            for issue in report.errors
        )
    if report.warnings:
        lines.extend(("", "Avisos:"))
        lines.extend(
            f"- {warning.file} | {warning.reason}" for warning in report.warnings
        )
    return "\n".join(lines) + "\n"


def run_application_batch(
    folder: str | Path, competence_input: str | None
) -> ApplicationRun:
    """Validate UI input, choose a safe destination, and call the batch core."""

    competence = normalize_competence(competence_input)
    output_path = unique_output_path(folder, competence_input)
    report = process_folder(
        folder,
        output_path=output_path,
        report_period=competence,
        overwrite=False,
    )
    log_path = output_path.with_suffix(".execution.log")
    try:
        log_path.write_text(_execution_log_text(report), encoding="utf-8")
    except OSError as exc:
        return ApplicationRun(report=report, log_path=None, log_error=str(exc))
    return ApplicationRun(report=report, log_path=log_path)
