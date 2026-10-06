"""Windows OCR child-process and GUI build configuration checks."""

from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from alugueis_extrator import process_folder
from alugueis_extrator.errors import PdfReadError
from alugueis_extrator import pdf_reader


ROOT = Path(__file__).resolve().parents[1]


class _FakeImage:
    def save(self, stream, format: str) -> None:
        self.format = format
        stream.write(b"synthetic-render")

    def close(self) -> None:
        pass


class _FakeBitmap:
    def to_pil(self) -> _FakeImage:
        return _FakeImage()


class _FakePage:
    def render(self, *, scale: int) -> _FakeBitmap:
        if scale != 3:
            raise AssertionError(f"unexpected render scale: {scale}")
        return _FakeBitmap()


class _FakeDocument:
    def __init__(self, _path: str) -> None:
        pass

    def __len__(self) -> int:
        return 1

    def __getitem__(self, _index: int) -> _FakePage:
        return _FakePage()

    def close(self) -> None:
        pass


class OcrSubprocessWindowsTests(unittest.TestCase):
    _TSV = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\t"
        "top\twidth\theight\tconf\ttext\n"
        "5\t1\t1\t1\t1\t1\t10\t20\t30\t12\t96.0\tpalavra\n"
    ).encode("utf-8")

    def _run_with_tesseract_result(self, returncode: int, stderr: bytes = b""):
        completed = subprocess.CompletedProcess(
            args=["tesseract"],
            returncode=returncode,
            stdout=self._TSV if returncode == 0 else b"",
            stderr=stderr,
        )
        with tempfile.TemporaryDirectory() as runtime_dir:
            runtime = Path(runtime_dir)
            (runtime / "tesseract.exe").touch()
            (runtime / "tessdata").mkdir()
            (runtime / "tessdata" / "por.traineddata").touch()
            with (
                patch.object(pdf_reader, "_ocr_runtime_dir", return_value=runtime),
                patch.object(pdf_reader.pypdfium2, "PdfDocument", _FakeDocument),
                patch.object(pdf_reader.subprocess, "run", return_value=completed) as run,
            ):
                error_message = ""
                if returncode == 0:
                    words = pdf_reader.read_pdf_ocr_words("synthetic.pdf")
                else:
                    with self.assertRaises(PdfReadError) as captured:
                        pdf_reader.read_pdf_ocr_words("synthetic.pdf")
                    words = []
                    error_message = str(captured.exception)
        return words, run, error_message

    def test_ocr_wrapper_hides_windows_console_and_keeps_captured_streams(self) -> None:
        words, run, _error_message = self._run_with_tesseract_result(0)

        self.assertEqual([word.text for word in words], ["palavra"])
        kwargs = run.call_args.kwargs
        self.assertTrue(kwargs["capture_output"])
        self.assertFalse(kwargs["check"])
        self.assertEqual(kwargs["timeout"], 60)
        if os.name == "nt":
            self.assertEqual(kwargs["creationflags"], subprocess.CREATE_NO_WINDOW)
            startup_info = kwargs["startupinfo"]
            self.assertTrue(startup_info.dwFlags & subprocess.STARTF_USESHOWWINDOW)
            self.assertEqual(startup_info.wShowWindow, subprocess.SW_HIDE)
        else:
            self.assertNotIn("creationflags", kwargs)
            self.assertNotIn("startupinfo", kwargs)

    def test_tesseract_failure_code_and_stderr_remain_diagnostic(self) -> None:
        _words, run, error_message = self._run_with_tesseract_result(
            17, b"synthetic tesseract diagnostic"
        )
        kwargs = run.call_args.kwargs
        self.assertTrue(kwargs["capture_output"])
        self.assertFalse(kwargs["check"])

        completed = run.return_value
        self.assertEqual(completed.returncode, 17)
        self.assertEqual(completed.stderr, b"synthetic tesseract diagnostic")
        self.assertIn("código 17", error_message)
        self.assertIn("synthetic tesseract diagnostic", error_message)

    def test_tesseract_failure_is_written_to_batch_diagnostics(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["tesseract"],
            returncode=17,
            stdout=b"",
            stderr=b"synthetic tesseract diagnostic",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scanned.pdf").write_bytes(b"synthetic PDF placeholder")
            runtime = root / "ocr-runtime"
            (runtime / "tessdata").mkdir(parents=True)
            (runtime / "tesseract.exe").touch()
            (runtime / "tessdata" / "por.traineddata").touch()
            with (
                patch.object(pdf_reader, "_ocr_runtime_dir", return_value=runtime),
                patch.object(pdf_reader.pypdfium2, "PdfDocument", _FakeDocument),
                patch.object(pdf_reader.subprocess, "run", return_value=completed),
                patch("alugueis_extrator.parser.read_pdf_tables", return_value=[[]]),
            ):
                report = process_folder(root)

            diagnostics = json.loads(report.diagnostics_path.read_text(encoding="utf-8"))
            self.assertEqual(len(diagnostics["errors"]), 1)
            issue = diagnostics["errors"][0]
            self.assertEqual(issue["stage"], "pdf_read")
            self.assertIn("código 17", issue["reason"])
            self.assertIn("synthetic tesseract diagnostic", issue["reason"])

    def test_pyinstaller_application_entry_is_windowed(self) -> None:
        spec = (ROOT / "ExtratorAlugueis.spec").read_text(encoding="utf-8")
        self.assertRegex(spec, r"(?m)^\s*console=False,\s*$")


if __name__ == "__main__":
    unittest.main(verbosity=2)
