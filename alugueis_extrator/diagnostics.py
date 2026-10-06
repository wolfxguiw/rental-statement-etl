"""JSON diagnostics for batch outcomes and source traceability."""

import json
import os
from pathlib import Path
import tempfile

from .errors import WorkbookWriteError
from .models import BatchReport


def diagnostics_payload(report: BatchReport) -> dict:
    return {
        "input_folder": str(report.input_folder),
        "output_file": str(report.output_path),
        "summary": {
            "total_pdfs": report.total_pdfs,
            "processed": report.processed,
            "records_generated": report.records_generated,
            "errors_or_review": report.review_count,
            "warnings": len(report.warnings),
        },
        "records": [
            {
                "source_file": record.source_file,
                "source_path": record.source_path,
                "cpf": record.cpf,
                "name": record.name,
                "category": record.category.value,
                "original_history": record.original_history,
                "rent": format(record.rent, ".2f"),
            }
            for record in report.records
        ],
        "errors": [
            {"file": issue.file, "stage": issue.stage, "reason": issue.reason}
            for issue in report.errors
        ],
        "warnings": [
            {"file": warning.file, "reason": warning.reason}
            for warning in report.warnings
        ],
    }


def write_diagnostics(report: BatchReport) -> Path:
    """Save JSON diagnostics atomically alongside the workbook."""

    target = report.diagnostics_path
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=f".{target.stem}.", suffix=".tmp",
            dir=target.parent, delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(diagnostics_payload(report), temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
        os.replace(temporary_path, target)
        return target
    except Exception as exc:
        raise WorkbookWriteError(f"falha ao gravar diagnósticos: {exc}") from exc
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)
