# Pipeline architecture

The desktop interface delegates to the application service, which calls the same batch pipeline used by the command-line entry point. The parser and validation logic stay independent of Tkinter.

```text
Folder input
  → PDF discovery and SHA-256 byte-duplicate check
  → native PDF table/text extraction
  → local OCR fallback when native content is unavailable
  → table/coordinate parsing
  → explicit event classification
  → CPF, name, and Decimal amount validation
  → per-file result, warning, or review issue
  → Excel workbook and diagnostics
```

Each successful event keeps its source PDF internally. A byte-identical file is only processed once; distinct files are not removed based on matching business fields. Unsupported or ambiguous documents become review issues instead of guessed records.

The public test suite uses generated documents and synthetic OCR coordinates. It is deliberately independent from the private historical validation corpus and from the local Tesseract binaries used in a Windows release build.
