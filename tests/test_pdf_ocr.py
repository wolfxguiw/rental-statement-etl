"""Synthetic checks for strict OCR-row and Bruto-column selection."""

from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from reportlab.pdfgen import canvas

from alugueis_extrator import ExtractionError, extract_pdf
from alugueis_extrator.parser import _extract_ocr_gross_rent, _extract_ocr_main_events
from alugueis_extrator.pdf_reader import OcrWord
from alugueis_extrator.rubrics import RubricClassification


def _word(
    text: str,
    left: int,
    top: int,
    line: int,
    *,
    width: int | None = None,
) -> OcrWord:
    return OcrWord(
        text=text,
        left=left,
        top=top,
        width=width if width is not None else max(12, len(text) * 8),
        height=14,
        confidence=96.0,
        line_id=(1, 1, line),
    )


def _header() -> list[OcrWord]:
    labels = (
        ("VENCIMENTO", 80),
        ("HISTÓRICO", 250),
        ("BRUTO", 730),
        ("PARTICIPAÇÃO", 900),
        ("DÉBITO", 1100),
        ("CRÉDITO", 1300),
    )
    return [_word(text, left, 100, 1) for text, left in labels]


def _rent_line(line: int, top: int, *, history: str = "Aluguel") -> list[OcrWord]:
    return [
        _word("06/06/2026", 80, top, line, width=90),
        _word(history, 250, top, line),
        _word("1.234,56", 720, top, line, width=90),
        _word("100,0000%", 900, top, line, width=90),
        _word("8.888,88", 1100, top, line, width=90),
        _word("1.234,56", 1300, top, line, width=90),
    ]


class OcrParserTests(unittest.TestCase):
    def test_exact_aluguel_row_uses_bruto_column_and_keeps_cents(self) -> None:
        words = _header() + _rent_line(2, 130)
        self.assertEqual(_extract_ocr_gross_rent(words), Decimal("1234.56"))

    def test_taxa_adm_aluguel_is_not_the_exact_rent_row(self) -> None:
        words = _header() + _rent_line(2, 130, history="Taxa")
        words.insert(2, _word("ADM./Aluguel", 310, 130, 2))
        with self.assertRaisesRegex(ExtractionError, "rubrica principal suportada"):
            _extract_ocr_gross_rent(words)

    def test_multa_is_kept_and_taxa_adm_aluguel_is_ignored(self) -> None:
        multa = _rent_line(2, 130, history="Multa")
        multa.insert(2, _word("Contratual", 310, 130, 2))
        multa[3] = _word("695,34", 720, 130, 2, width=70)
        taxa = _rent_line(3, 160, history="Taxa")
        taxa.insert(2, _word("ADM./Aluguel", 310, 160, 3))
        taxa[3] = _word("41,72", 720, 160, 3, width=50)
        events = _extract_ocr_main_events(_header() + multa + taxa)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], RubricClassification.MULTA_CONTRATUAL)
        self.assertEqual(events[0][2], Decimal("695.34"))

    def test_two_exact_aluguel_rows_are_ambiguous(self) -> None:
        words = _header() + _rent_line(2, 130) + _rent_line(3, 160)
        with self.assertRaisesRegex(ExtractionError, "encontrados 2"):
            _extract_ocr_gross_rent(words)

    def test_ocr_reconstructs_multitoken_multa_and_keeps_bruto_amount(self) -> None:
        aluguel = _rent_line(2, 130)
        multa = _rent_line(3, 160, history="Multa")
        multa.insert(2, _word("Contratual", 310, 160, 3))
        multa[3] = _word("695,34", 720, 160, 3, width=70)
        events = _extract_ocr_main_events(_header() + aluguel + multa)
        self.assertEqual(
            [(category, value) for category, _history, value in events],
            [
                (RubricClassification.ALUGUEL, Decimal("1234.56")),
                (RubricClassification.MULTA_CONTRATUAL, Decimal("695.34")),
            ],
        )
        self.assertEqual(events[1][1], "Multa Contratual")

    def test_missing_bruto_column_is_reviewed(self) -> None:
        words = [word for word in _header() if word.text != "BRUTO"]
        words += _rent_line(2, 130)
        with self.assertRaisesRegex(ExtractionError, "cabeçalho"):
            _extract_ocr_gross_rent(words)

    def test_unknown_scanned_layout_does_not_use_fixture_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "documento desconhecido.pdf"
            pdf = canvas.Canvas(str(path), pagesize=(595, 842))
            pdf.drawString(60, 780, "DOCUMENTO DE TESTE SEM TABELA DE ALUGUEL")
            pdf.save()
            with self.assertRaises(ExtractionError):
                extract_pdf(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
