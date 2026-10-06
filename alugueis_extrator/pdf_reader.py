"""PDF file access, separate from field parsing."""

import csv
from dataclasses import dataclass
from io import BytesIO, StringIO
import os
from pathlib import Path
import subprocess
import sys

import pdfplumber
import pypdfium2

from .errors import PdfReadError


PdfTables = list[list[list[str | None]]]


@dataclass(frozen=True)
class OcrWord:
    """A locally recognized word and its position on the rendered PDF page."""

    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float
    line_id: tuple[int, int, int]

    @property
    def center_x(self) -> float:
        return self.left + self.width / 2


def _ocr_runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "ocr"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1] / "vendor" / "tesseract"


def _ocr_subprocess_options() -> dict[str, object]:
    """Hide the OCR console window in Windows GUI builds.

    Keep the normal subprocess behavior on other platforms. The OCR process
    still captures stdout and stderr in ``read_pdf_ocr_words`` for parsing and
    diagnostics.
    """

    if os.name != "nt":
        return {}

    startup_info = subprocess.STARTUPINFO()
    startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup_info.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startup_info,
    }


def _process_error_detail(value: bytes | str | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return value.strip() if value else ""


def read_pdf_tables(pdf_path: str | Path) -> PdfTables:
    """Read table cells from the supported one-page PDF format."""

    path = Path(pdf_path)
    if not path.is_file():
        raise PdfReadError(f"arquivo PDF não encontrado: {path}")
    try:
        with pdfplumber.open(path) as pdf:
            if len(pdf.pages) != 1:
                raise PdfReadError(
                    f"esperada uma página; encontrado(s) {len(pdf.pages)}"
                )
            return pdf.pages[0].extract_tables()
    except PdfReadError:
        raise
    except Exception as exc:
        raise PdfReadError(f"não foi possível ler o PDF: {exc}") from exc


def read_pdf_ocr_words(pdf_path: str | Path) -> list[OcrWord]:
    """Render one-page, image-only PDFs and recognize them with bundled OCR.

    OCR runs locally using the packaged Tesseract engine and Portuguese and
    English language data. It returns word coordinates so downstream parsing
    can still identify the labeled ``Aluguel`` row and ``Bruto`` column.
    """

    path = Path(pdf_path)
    runtime_dir = _ocr_runtime_dir()
    executable = runtime_dir / "tesseract.exe"
    tessdata_dir = runtime_dir / "tessdata"
    if not executable.is_file() or not (tessdata_dir / "por.traineddata").is_file():
        raise PdfReadError("OCR local indisponível; reinstale a distribuição do aplicativo")

    try:
        document = pypdfium2.PdfDocument(str(path))
        try:
            if len(document) != 1:
                raise PdfReadError(f"esperada uma página; encontrado(s) {len(document)}")
            rendered = document[0].render(scale=3).to_pil()
            image_stream = BytesIO()
            rendered.save(image_stream, format="PNG")
            rendered.close()
        finally:
            document.close()

        environment = os.environ.copy()
        environment["TESSDATA_PREFIX"] = str(tessdata_dir)
        result = subprocess.run(
            [
                str(executable),
                "stdin",
                "stdout",
                "-l",
                "por+eng",
                "--psm",
                "6",
                "-c",
                "tessedit_create_tsv=1",
            ],
            input=image_stream.getvalue(),
            capture_output=True,
            check=False,
            timeout=60,
            env=environment,
            **_ocr_subprocess_options(),
        )
    except PdfReadError:
        raise
    except subprocess.TimeoutExpired as exc:
        detail = _process_error_detail(exc.stderr)
        suffix = f": {detail[:1000]}" if detail else ""
        raise PdfReadError(f"o OCR local excedeu o tempo limite{suffix}") from exc
    except Exception as exc:
        raise PdfReadError(f"não foi possível renderizar o PDF para OCR: {exc}") from exc

    if result.returncode != 0:
        detail = _process_error_detail(result.stderr)
        suffix = f": {detail[:1000]}" if detail else ""
        raise PdfReadError(
            f"o OCR local falhou com código {result.returncode}{suffix}"
        )

    try:
        reader = csv.DictReader(
            StringIO(result.stdout.decode("utf-8-sig")), delimiter="\t"
        )
        words: list[OcrWord] = []
        for row in reader:
            text = (row.get("text") or "").strip()
            if row.get("level") != "5" or not text:
                continue
            words.append(
                OcrWord(
                    text=text,
                    left=int(row["left"]),
                    top=int(row["top"]),
                    width=int(row["width"]),
                    height=int(row["height"]),
                    confidence=float(row["conf"]),
                    line_id=(
                        int(row["block_num"]),
                        int(row["par_num"]),
                        int(row["line_num"]),
                    ),
                )
            )
    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise PdfReadError("resposta do OCR local em formato inesperado") from exc

    if not words:
        raise PdfReadError("nenhum texto reconhecível encontrado na página")
    return words
