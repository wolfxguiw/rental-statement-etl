# Extrator de Demonstrativos de Aluguel

Local document-processing pipeline for structured extraction from digital and scanned rental statement PDFs.

This small local automation turns a recurring document workflow into validated tabular data. It is presented as an engineering example of ingestion, deterministic parsing, data quality checks, traceability, and export—not as an accounting platform.

## Problem and approach

Rental statements are semi-structured documents. Their values have meaning only when connected to the correct row and column, so the pipeline uses document structure to extract supported financial events and sends ambiguous or unfamiliar layouts for review.

```text
PDF
 ↓
Document detection
 ├── Native text extraction
 └── Local OCR fallback for image-only pages
        ↓
Structural table parsing
        ↓
Deterministic event classification
        ↓
Normalization
        ↓
Validation and data-quality checks
        ↓
Traceable records and duplicate checks
        ↓
Structured Excel export + diagnostics
```

## Pipeline capabilities

- Batch ingestion of PDFs from a selected folder, with each file isolated so one failure does not stop the rest.
- Native text extraction first, with local Tesseract OCR as a fallback when a page has no usable text layer.
- Structural selection of supported event rows and their `Bruto` values; totals, administrative fees, condominium, taxes, payments, and aggregate rows are not treated as the requested events.
- Explicit, deterministic classification for `ALUGUEL` and `MULTA_CONTRATUAL`. Unknown financial rubrics are reported for review.
- CPF normalization and validation while preserving the identifier as text, including leading zeroes.
- Decimal monetary parsing to preserve cents.
- Multiple supported events from one PDF remain separate output records.
- SHA-256 duplicate detection suppresses only byte-identical PDFs. Distinct files are preserved.
- Per-file source traceability, structured diagnostics, and a readable execution log.
- Excel output with the stable three-column layout `CPF | NOME | VALOR DO ALUGUEL`.

## Engineering decisions

1. **Values are selected by structure, not magnitude.** The parser associates a supported history row with the value under the `Bruto` column. It does not choose the largest amount or the first monetary token on a page.
2. **OCR is a fallback.** Text-based PDFs use their native text layer. Local OCR is used when native extraction cannot provide usable text.
3. **Ambiguity does not create invented data.** Missing identifiers, unknown financial rows, and unsupported layouts become review issues with a file and failure stage.
4. **Money uses decimal arithmetic.** Values are parsed and validated with decimal types to avoid floating-point cent loss.
5. **CPF is an identifier, not a number.** It is validated as text and remains text in the workbook so leading zeroes survive.
6. **Automatic deduplication is conservative.** Only identical file bytes (SHA-256) are automatically treated as a duplicate. Similar CPF/name/value combinations do not discard a distinct document.
7. **A document can produce several records.** Each supported financial event is retained with its internal category and source PDF.

## Project structure

```text
alugueis_extrator/   PDF reading, parsing, classification, validation, batch service, Excel and diagnostics
tests/               Synthetic unit and integration tests; no private document corpus
docs/                Architecture and project notes
build.ps1            Windows onedir packaging script
ExtratorAlugueis.spec PyInstaller GUI build configuration
```

## Run locally

The application targets Windows and Python 3.12. It uses Tkinter for the desktop interface. For development:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe run_desktop.py
```

To use local OCR while running from source, provision a compatible Tesseract distribution and Portuguese trained data at `vendor\tesseract\` as described in [DEVELOPMENT.md](DEVELOPMENT.md). The public source repository intentionally does not contain OCR binaries or language data.

## Windows build

On Windows, with Python 3.12 and the local OCR runtime provisioned, run:

```powershell
.\build.ps1
```

The script creates an onedir GUI distribution in `dist\ExtratorAlugueis\`. The executable and its `_internal` directory must be kept together. The build includes local OCR runtime files when they have been provisioned; it does not require Microsoft Excel.

## Tests and validation

The public suite creates synthetic PDFs and OCR word coordinates at test time. It covers digital PDF parsing, OCR structural parsing, both supported categories, multiple events, administrative-row exclusion, CPF validation and leading zeroes, cents, corrupt or unfamiliar input, duplicate handling, diagnostics, and GUI-facing service behavior. CI runs these tests on Windows without private data or an installed Tesseract process; OCR subprocess behavior is tested with a controlled synthetic process result.

During internal development, the application was also validated against 51 real documents across three historical monthly batches. That corpus is private, is not included here, and is not needed to run or test this public project. The public tests use synthetic fixtures only.

## Scope and privacy

- This is a local workflow tool for one document family, not a general-purpose PDF extraction framework.
- Documents are processed locally; the application does not send them to external APIs and has no LLM dependency at runtime.
- OCR runs locally when needed.
- No real statements, spreadsheets, names, or CPF values from the internal validation corpus are included in this repository.
- New layouts and unsupported financial events may require an explicit parser rule and synthetic regression test before they can be processed automatically.
- The project has no license file; no project license is being assigned by this repository.

## Limitations

Parsing depends on the supported statement table structure and labels. Scans with poor image quality, missing table headings, or unfamiliar layouts may require review. The supported principal categories are explicit and intentionally limited; the parser does not infer new categories.
