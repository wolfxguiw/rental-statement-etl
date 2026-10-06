"""Tests for the GUI-facing application service without opening a window."""

from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from alugueis_extrator.application_service import (
    count_pdf_files,
    normalize_competence,
    report_filename,
    run_application_batch,
    unique_output_path,
)
from alugueis_extrator.gui_presentation import (
    friendly_issue,
    friendly_warning,
    result_summary,
)
from alugueis_extrator.models import (
    BatchReport,
    ProcessingIssue,
    ProcessingWarning,
    RentalRecord,
)


class ApplicationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_competence_is_optional_and_normalized_for_core(self) -> None:
        self.assertIsNone(normalize_competence("  "))
        self.assertEqual(normalize_competence("09/2026"), "09-2026")

    def test_invalid_competence_is_rejected(self) -> None:
        for value in ("13/2026", "2026-09", "9/2026", "09/0000", "09/20A6"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_competence(value)

    def test_report_filename_uses_period_only_when_supplied(self) -> None:
        self.assertEqual(report_filename(None), "Relatorio_Alugueis.xlsx")
        self.assertEqual(report_filename("09/2026"), "Relatorio_Alugueis_09-2026.xlsx")

    def test_existing_report_and_diagnostics_choose_a_free_alternate(self) -> None:
        base = self.root / "Relatorio_Alugueis_09-2026.xlsx"
        base.touch()
        base.with_suffix(".diagnostics.json").touch()
        candidate = unique_output_path(self.root, "09/2026")
        self.assertEqual(candidate.name, "Relatorio_Alugueis_09-2026_2.xlsx")
        self.assertFalse(candidate.exists())

    def test_pdf_count_uses_recursive_batch_discovery(self) -> None:
        (self.root / "one.PDF").write_bytes(b"1")
        nested = self.root / "sub"
        nested.mkdir()
        (nested / "two.pdf").write_bytes(b"2")
        (nested / "ignore.txt").write_text("x", encoding="utf-8")
        self.assertEqual(count_pdf_files(self.root), 2)

    def test_gui_service_calls_existing_batch_core_and_writes_support_log(self) -> None:
        output = self.root / "Relatorio_Alugueis_09-2026.xlsx"
        record = RentalRecord(
            source_file="demonstrativo.pdf",
            cpf="987.654.321-00",
            name="MARIA EXEMPLO DA SILVA",
            rent=Decimal("123.45"),
            source_path="demonstrativo.pdf",
        )
        report = BatchReport(
            input_folder=self.root,
            output_path=output,
            diagnostics_path=output.with_suffix(".diagnostics.json"),
            total_pdfs=1,
            records=[record],
            errors=[],
            warnings=[],
        )
        with patch(
            "alugueis_extrator.application_service.process_folder", return_value=report
        ) as process:
            run = run_application_batch(self.root, "09/2026")
        process.assert_called_once_with(
            self.root,
            output_path=output,
            report_period="09-2026",
            overwrite=False,
        )
        self.assertTrue(run.log_path and run.log_path.is_file())
        log = run.log_path.read_text(encoding="utf-8")
        self.assertIn("Versão:", log)
        self.assertIn("PDFs encontrados: 1", log)
        self.assertIn("Documentos processados: 1", log)
        self.assertNotIn(record.cpf, log)
        self.assertNotIn(record.name, log)

    def test_gui_result_summary_and_friendly_issue_messages(self) -> None:
        output = self.root / "report.xlsx"
        report = BatchReport(
            input_folder=self.root,
            output_path=output,
            diagnostics_path=output.with_suffix(".diagnostics.json"),
            total_pdfs=2,
            records=[],
            errors=[ProcessingIssue("falha.pdf", "parser", "valor do aluguel ambíguo")],
            warnings=[ProcessingWarning("copia.pdf", "PDF binariamente idêntico")],
        )
        summary = result_summary(report)
        self.assertIn("PDFs encontrados: 2", summary)
        self.assertIn("Documentos para revisão: 1", summary)
        self.assertIn("Falhas técnicas do lote: 0", summary)
        self.assertEqual(
            friendly_issue(report.errors[0]),
            "Valor do aluguel não identificado com segurança.",
        )
        self.assertIn("ignorada", friendly_warning(report.warnings[0]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
