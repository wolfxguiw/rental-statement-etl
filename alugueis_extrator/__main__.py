"""Command-line entry point for local monthly batches."""

import argparse
import json
import sys

from .batch import process_folder
from .errors import FolderInputError, OutputAlreadyExistsError, WorkbookWriteError


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Processa uma pasta de demonstrativos de aluguel em PDF."
    )
    parser.add_argument("pasta", help="pasta de entrada; subpastas também são pesquisadas")
    parser.add_argument("--saida", help="caminho do .xlsx; por padrão, fica na pasta de entrada")
    parser.add_argument(
        "--periodo",
        help="período explicitamente informado no formato MM-AAAA (não é inferido dos PDFs)",
    )
    parser.add_argument("--sem-recursao", action="store_true", help="não pesquisar subpastas")
    parser.add_argument("--sobrescrever", action="store_true", help="substituir a saída existente")
    args = parser.parse_args()

    try:
        report = process_folder(
            args.pasta,
            output_path=args.saida,
            report_period=args.periodo,
            recursive=not args.sem_recursao,
            overwrite=args.sobrescrever,
        )
    except (FolderInputError, OutputAlreadyExistsError, WorkbookWriteError, ValueError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "total_pdfs": report.total_pdfs,
                "processados": report.processed,
                "erro_ou_revisao": report.review_count,
                "avisos": len(report.warnings),
                "excel": str(report.output_path),
                "diagnosticos": str(report.diagnostics_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    for issue in report.errors:
        print(f"{issue.file}\nERRO [{issue.stage}]: {issue.reason}", file=sys.stderr)
    for warning in report.warnings:
        print(f"{warning.file}\nAVISO: {warning.reason}", file=sys.stderr)
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
