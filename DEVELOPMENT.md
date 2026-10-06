# Development

## Environment and tests

- Windows x64 is the target for the desktop package; the parsing and synthetic test suite can also run on other Python 3.12 platforms.
- Runtime dependencies are pinned in `requirements-runtime.txt`.
- Development and build dependencies are pinned in `requirements-dev.txt`.
- PyInstaller creates a windowed, one-folder (`onedir`) distribution.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The public tests do not need real documents, OCR model files, or a running Tesseract binary. OCR parsing is tested with synthetic word coordinates; subprocess flags and error capture are tested with a mocked child process.

## Local OCR runtime for a Windows build

The repository excludes OCR executables and trained data. Before a local build, provision Tesseract 5.5.0.20241111 (or a reviewed compatible release) under `vendor\tesseract\`, including `tesseract.exe`, its required runtime libraries, `tessdata\por.traineddata`, and `SHA256SUMS.txt`. Review applicable third-party notices and redistribution terms for the exact files before distributing a packaged build.

The build script validates the OCR file manifest, installs pinned dependencies, and creates `dist\ExtratorAlugueis\`. To launch the desktop application from source after provisioning OCR:

```powershell
.\.venv\Scripts\python.exe run_desktop.py
```

## Architecture

- `pdf_reader.py`: native PDF text/table access and local OCR subprocess wrapper.
- `parser.py`: structural table and OCR-coordinate parsing.
- `rubrics.py`: centralized event classification.
- `normalization.py` and `validation.py`: identifier, name, and monetary normalization/validation.
- `batch.py`: folder ingestion, byte-level duplicate suppression, per-file error isolation, and orchestration.
- `excel_writer.py`: three-column workbook export.
- `diagnostics.py`: structured diagnostic output and readable execution logs.
- `application_service.py` and `gui.py`: GUI-facing service and Tkinter interface.

The runtime package does not read the test directory or use a reference workbook. New behavior should be covered by synthetic tests in `tests/`.
