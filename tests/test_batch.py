"""Synthetic checks for monthly batch behavior and failure isolation."""

from decimal import Decimal
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import load_workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

from alugueis_extrator import (
    ExtractionError,
    FolderInputError,
    OutputAlreadyExistsError,
    RentalRecord,
    is_valid_cpf,
    process_folder,
    validate_record,
)
from alugueis_extrator.errors import ValidationError
from alugueis_extrator.parser import extract_pdf


TEST_CPF = "987.654.321-00"
TEST_NAME = "MARIA EXEMPLO DA SILVA"


def make_pdf(
    path: Path,
    *,
    name: str = TEST_NAME,
    cpf: str | None = TEST_CPF,
    amount: str = "1.234,56",
    rent_rows: int = 1,
    include_rent: bool = True,
    include_fine: bool = False,
    fine_amount: str = "695,34",
    period_reference: str = "10/08/2026 a 09/09/2026",
    unknown_history: str | None = None,
    known_layout: bool = True,
    marker: str = "A",
    column_order: tuple[int, ...] | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not known_layout:
        data = [["Comprovante de outro formato"]]
        table = Table(data, colWidths=[350])
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    else:
        tenant_line = f"INQ.: {name} - CPF: {cpf}" if cpf else f"INQ.: {name}"
        rows = [
            [tenant_line, "", "", "", "", ""],
            [f"Repasse: sintético {marker}", "", "", "", "", ""],
            ["VENCIMENTO", "HISTÓRICO", "BRUTO", "PARTICIPAÇÃO", "DÉBITO", "CRÉDITO"],
        ]
        if include_rent:
            for index in range(rent_rows):
                rows.append(
                    [
                        "10/09/2026",
                        f"Aluguel {index + 1:02d}/12 - Ref. {period_reference}",
                        amount,
                        "100,0000%",
                        "",
                        amount,
                    ]
                )
        if include_fine:
            rows.append(
                ["10/09/2026", "Multa Contratual", fine_amount, "100,0000%", "", fine_amount]
            )
        if unknown_history:
            rows.append(
                ["10/09/2026", unknown_history, "88,88", "100,0000%", "", "88,88"]
            )
        rows.extend(
            [
                ["10/09/2026", "Taxa ADM./Aluguel", "8.888,88", "100,0000%", "8.888,88", ""],
                ["10/09/2026", "Condomínio", "777,77", "100,0000%", "", "777,77"],
                ["Subtotal", "", "", "", "8.888,88", "9.999,99"],
                ["Total", "", "", "", "", "9.999,99"],
                ["16/09/2026", "PAGAMENTO EFETUADO (TED)", "9.999,99", "100,0000%", "9.999,99", ""],
            ]
        )
        if column_order is not None:
            rows = [[row[index] for index in column_order] for row in rows]
        table = Table(rows, colWidths=[75, 250, 65, 70, 55, 57], repeatRows=2)
        table.setStyle(
            TableStyle(
                [
                    ("SPAN", (0, 0), (5, 0)),
                    ("SPAN", (0, 1), (5, 1)),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("BACKGROUND", (0, 2), (-1, 2), colors.lightblue),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]
            )
        )
    document = SimpleDocTemplate(
        str(path), pagesize=letter, leftMargin=20, rightMargin=20, topMargin=25, bottomMargin=25
    )
    document.build([table])
    return path


class BatchProcessingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_empty_folder_creates_header_only_workbook(self) -> None:
        empty = self.root / "empty"
        empty.mkdir()
        report = process_folder(empty)
        self.assertEqual((report.total_pdfs, report.processed, report.review_count), (0, 0, 0))
        workbook = load_workbook(report.output_path, data_only=True)
        self.assertEqual(list(workbook.active.values), [("CPF", "NOME", "VALOR DO ALUGUEL")])

    def test_nonexistent_folder_fails_clearly(self) -> None:
        with self.assertRaisesRegex(FolderInputError, "inexistente"):
            process_folder(self.root / "does-not-exist")

    def test_invalid_pdf_isolated_from_valid_pdf(self) -> None:
        folder = self.root / "mixed"
        folder.mkdir()
        (folder / "arquivo corrompido.pdf").write_bytes(b"not a pdf")
        make_pdf(folder / "válido São.pdf")
        report = process_folder(folder)
        self.assertEqual(report.total_pdfs, 2)
        self.assertEqual(report.processed, 1)
        self.assertEqual(report.review_count, 1)
        self.assertEqual(report.errors[0].stage, "pdf_read")
        diagnostics = json.loads(report.diagnostics_path.read_text(encoding="utf-8"))
        self.assertEqual(diagnostics["records"][0]["source_path"], "válido São.pdf")
        self.assertEqual(diagnostics["errors"][0]["file"], "arquivo corrompido.pdf")

    def test_missing_cpf_is_reported_for_that_pdf(self) -> None:
        folder = self.root / "missing-cpf"
        make_pdf(folder / "sem-cpf.pdf", cpf=None)
        report = process_folder(folder)
        self.assertEqual(report.processed, 0)
        self.assertEqual(report.errors[0].stage, "parser")
        self.assertIn("CPF ausente", report.errors[0].reason)

    def test_missing_rent_is_reported_for_that_pdf(self) -> None:
        folder = self.root / "missing-rent"
        make_pdf(folder / "sem-aluguel.pdf", include_rent=False)
        report = process_folder(folder)
        self.assertEqual(report.processed, 0)
        self.assertEqual(report.errors[0].stage, "parser")
        self.assertIn("rubrica principal suportada", report.errors[0].reason)

    def test_two_main_rows_in_one_pdf_are_both_preserved(self) -> None:
        folder = self.root / "two-rents"
        make_pdf(folder / "dois-alugueis.pdf", rent_rows=2)
        report = process_folder(folder)
        self.assertEqual(report.processed, 1)
        self.assertEqual(report.records_generated, 2)
        self.assertEqual([record.category.value for record in report.records], ["ALUGUEL", "ALUGUEL"])

    def test_only_aluguel_is_one_aluguel_event(self) -> None:
        folder = self.root / "only-aluguel"
        make_pdf(folder / "aluguel.pdf")
        report = process_folder(folder)
        self.assertEqual(report.processed, 1)
        self.assertEqual(report.records_generated, 1)
        self.assertEqual(report.records[0].category.value, "ALUGUEL")
        self.assertEqual(
            report.records[0].original_history,
            "Aluguel 01/12 - Ref. 10/08/2026 a 09/09/2026",
        )

    def test_only_multa_contratual_is_one_fine_event(self) -> None:
        folder = self.root / "only-fine"
        make_pdf(folder / "multa.pdf", include_rent=False, include_fine=True)
        report = process_folder(folder)
        self.assertEqual(report.processed, 1)
        self.assertEqual(report.records_generated, 1)
        self.assertEqual(report.records[0].category.value, "MULTA_CONTRATUAL")
        self.assertEqual(report.records[0].rent, Decimal("695.34"))

    def test_aluguel_and_multa_in_same_pdf_generate_two_categorized_records(self) -> None:
        folder = self.root / "rent-and-fine"
        make_pdf(folder / "aluguel-e-multa.pdf", include_fine=True)
        report = process_folder(folder)
        self.assertEqual(report.processed, 1)
        self.assertEqual(report.records_generated, 2)
        self.assertEqual(
            [(record.category.value, record.rent) for record in report.records],
            [("ALUGUEL", Decimal("1234.56")), ("MULTA_CONTRATUAL", Decimal("695.34"))],
        )
        self.assertEqual(report.warnings, [])
        diagnostics = json.loads(report.diagnostics_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [row["category"] for row in diagnostics["records"]],
            ["ALUGUEL", "MULTA_CONTRATUAL"],
        )
        workbook = load_workbook(report.output_path, data_only=True)
        self.assertEqual((workbook.active.max_column, workbook.active.max_row), (3, 3))

    def test_unknown_financial_rubric_is_sent_to_review(self) -> None:
        folder = self.root / "unknown-rubric"
        make_pdf(
            folder / "nova-rubrica.pdf",
            unknown_history="Cobrança Especial",
        )
        report = process_folder(folder)
        self.assertEqual(report.processed, 0)
        self.assertEqual(report.review_count, 1)
        self.assertIn("Cobrança Especial", report.errors[0].reason)
        self.assertIn("desconhecida", report.errors[0].reason)

    def test_unknown_layout_is_reviewed_without_fixture_fallback(self) -> None:
        folder = self.root / "unknown-layout"
        folder.mkdir()
        (folder / "outro-formato.pdf").write_bytes(b"synthetic PDF placeholder")
        with patch(
            "alugueis_extrator.parser.read_pdf_tables",
            return_value=[[['Comprovante de outro formato']]],
        ):
            report = process_folder(folder)
        self.assertEqual(report.processed, 0)
        self.assertEqual(report.review_count, 1)
        self.assertIn("INQ./CPF", report.errors[0].reason)

    def test_zero_leading_cpf_accented_filename_and_cents_reach_excel(self) -> None:
        folder = self.root / "dados com espaço e acento"
        source = folder / "demonstrativo São José.pdf"
        make_pdf(source, amount="1.234,56")
        report = process_folder(folder, report_period="09-2026")
        self.assertEqual(report.output_path.name, "Relatorio_Alugueis_09-2026.xlsx")
        self.assertEqual(report.processed, 1)
        self.assertEqual(report.records[0].cpf, TEST_CPF)
        self.assertEqual(report.records[0].source_path, source.name)
        workbook = load_workbook(report.output_path, data_only=True)
        sheet = workbook.active
        self.assertEqual(list(sheet.iter_rows(min_row=1, max_row=1, values_only=True))[0],
                         ("CPF", "NOME", "VALOR DO ALUGUEL"))
        self.assertEqual(sheet.max_column, 3)
        self.assertEqual(sheet["A2"].value, TEST_CPF)
        self.assertEqual(sheet["A2"].data_type, "s")
        self.assertEqual(sheet["B2"].value, TEST_NAME)
        self.assertEqual(sheet["B2"].data_type, "s")
        self.assertEqual(sheet["C2"].data_type, "n")
        self.assertEqual(Decimal(str(sheet["C2"].value)), Decimal("1234.56"))
        self.assertEqual(sheet["C2"].number_format, "#,##0.00")

    def test_gross_value_is_selected_by_bruto_header_after_column_reorder(self) -> None:
        folder = self.root / "reordered-columns"
        make_pdf(
            folder / "colunas-reordenadas.pdf",
            column_order=(0, 1, 5, 3, 2, 4),
        )
        report = process_folder(folder)
        self.assertEqual(report.processed, 1)
        self.assertEqual(report.records[0].rent, Decimal("1234.56"))

    def test_exact_duplicate_file_is_reported_and_only_written_once(self) -> None:
        folder = self.root / "file-duplicates"
        first = make_pdf(folder / "a.pdf")
        folder.joinpath("sub").mkdir()
        shutil.copy2(first, folder / "sub" / "b.pdf")
        report = process_folder(folder)
        self.assertEqual(report.total_pdfs, 2)
        self.assertEqual(report.processed, 1)
        self.assertEqual(report.review_count, 0)
        self.assertEqual(len(report.warnings), 1)
        self.assertEqual(report.warnings[0].file, "sub/b.pdf")
        self.assertIn("binariamente idêntico", report.warnings[0].reason)

    def test_distinct_pdfs_with_same_cpf_and_rent_are_both_kept(self) -> None:
        folder = self.root / "record-duplicates"
        make_pdf(folder / "a.pdf", marker="A")
        make_pdf(folder / "b.pdf", marker="B")
        report = process_folder(folder)
        self.assertEqual(report.total_pdfs, 2)
        self.assertEqual(report.processed, 2)
        self.assertEqual(report.review_count, 0)
        self.assertEqual(len(report.warnings), 0)
        self.assertEqual({record.source_file for record in report.records}, {"a.pdf", "b.pdf"})
        workbook = load_workbook(report.output_path, data_only=True)
        self.assertEqual(workbook.active.max_row, 3)
        self.assertEqual([workbook.active[f"A{row}"].value for row in (2, 3)], [TEST_CPF, TEST_CPF])

    def test_distinct_pdfs_with_same_cpf_and_different_rents_are_both_kept(self) -> None:
        folder = self.root / "same-cpf-different-rent"
        make_pdf(folder / "a.pdf", marker="A", amount="1.234,56")
        make_pdf(folder / "b.pdf", marker="B", amount="2.345,67")
        report = process_folder(folder)
        self.assertEqual(report.total_pdfs, 2)
        self.assertEqual(report.processed, 2)
        self.assertEqual(report.review_count, 0)
        self.assertEqual(len(report.warnings), 0)
        self.assertEqual({record.rent for record in report.records}, {Decimal("1234.56"), Decimal("2345.67")})
        workbook = load_workbook(report.output_path, data_only=True)
        self.assertEqual(workbook.active.max_row, 3)
        self.assertEqual(
            {Decimal(str(workbook.active[f"C{row}"].value)) for row in (2, 3)},
            {Decimal("1234.56"), Decimal("2345.67")},
        )

    def test_same_cpf_value_and_category_with_different_periods_are_not_warned(self) -> None:
        folder = self.root / "different-periods"
        make_pdf(
            folder / "first.pdf",
            marker="A",
            period_reference="10/05/2026 a 09/06/2026",
        )
        make_pdf(
            folder / "second.pdf",
            marker="B",
            period_reference="10/06/2026 a 09/07/2026",
        )
        report = process_folder(folder)
        self.assertEqual((report.processed, report.records_generated), (2, 2))
        self.assertEqual(report.warnings, [])

    def test_output_existing_is_not_overwritten(self) -> None:
        folder = self.root / "input"
        make_pdf(folder / "valid.pdf")
        output = self.root / "existing.xlsx"
        original = b"do not overwrite"
        output.write_bytes(original)
        with self.assertRaises(OutputAlreadyExistsError):
            process_folder(folder, output_path=output)
        self.assertEqual(output.read_bytes(), original)

    def test_month_is_never_inferred_when_not_supplied(self) -> None:
        folder = self.root / "period"
        make_pdf(folder / "statement.pdf")
        report = process_folder(folder)
        self.assertEqual(report.output_path.name, "Relatorio_Alugueis.xlsx")
        with self.assertRaisesRegex(ValueError, "MM-AAAA"):
            process_folder(folder, output_path=self.root / "bad.xlsx", report_period="2026-09")

    def test_invalid_cpf_check_digits_and_nonpositive_rent_fail_validation(self) -> None:
        self.assertTrue(is_valid_cpf(TEST_CPF))
        self.assertFalse(is_valid_cpf("987.654.321-01"))
        base = RentalRecord("synthetic.pdf", TEST_CPF, TEST_NAME, Decimal("0.00"))
        with self.assertRaisesRegex(ValidationError, "positivo"):
            validate_record(base)

    def test_unreadable_character_is_not_repaired_from_fixture_names(self) -> None:
        base = RentalRecord("synthetic.pdf", TEST_CPF, "NOME � DESCONHECIDO", Decimal("12.34"))
        with self.assertRaisesRegex(ValidationError, "ilegível"):
            validate_record(base)

    def test_runtime_modules_do_not_reference_regression_datasets(self) -> None:
        production_text = "\n".join(
            module.read_text(encoding="utf-8")
            for module in (Path(__file__).parents[1] / "alugueis_extrator").glob("*.py")
        )
        lower = production_text.casefold()
        self.assertNotIn("cases.json", lower)
        self.assertNotIn("relatorio_alugueis_09-2026", lower)
        self.assertNotIn("tests/fixtures", lower)

    def test_synthetic_unseen_tenant_extracts_without_oracle_lookup(self) -> None:
        folder = self.root / "unseen"
        source = make_pdf(folder / "cliente novo.pdf", name="JOAO TESTE DE SOUZA", amount="7,23")
        record = extract_pdf(source)
        self.assertEqual(record.cpf, TEST_CPF)
        self.assertEqual(record.name, "JOAO TESTE DE SOUZA")
        self.assertEqual(record.rent, Decimal("7.23"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
