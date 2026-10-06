"""Strict parser for the supported one-page rental-statement format.

The parser reads labeled tenant data and the "Bruto" cell on the rent row.
Unknown or ambiguous layouts raise :class:`ExtractionError` for review.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import unicodedata

from .errors import ExtractionError
from .models import RentalRecord
from .pdf_reader import OcrWord, read_pdf_ocr_words, read_pdf_tables
from .rubrics import RubricClassification, classify_history


_CPF_RE = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")
_DATE_RE = re.compile(r"\d{2}/\d{2}/\d{4}")
_BRL_RE = re.compile(r"\d+(?:\.\d{3})*,\d{2}")
_TENANT_LABEL_RE = re.compile(r"\bINQ\.\s*:", re.IGNORECASE)
_TENANT_LINE_RE = re.compile(
    r"\bINQ\.\s*:\s*(.*?)\s*-\s*CPF\s*:\s*(\d{3}\.\d{3}\.\d{3}-\d{2})\b",
    re.IGNORECASE,
)

def _decode_doubled_token(token: str) -> str:
    """Undo duplicated glyph runs in a text token, rejecting odd runs."""

    result: list[str] = []
    index = 0
    while index < len(token):
        end = index + 1
        while end < len(token) and token[end] == token[index]:
            end += 1
        run_length = end - index
        if run_length % 2:
            raise ExtractionError(
                f"texto com codificação inesperada no campo: {token!r}"
            )
        result.append(token[index] * (run_length // 2))
        index = end
    return "".join(result)


def _normalize_extracted_cell(cell: str) -> str:
    """Undo a consistent doubled-glyph text map, or preserve ordinary text.

    Some PDFs expose every glyph twice in extracted table cells even though
    the page renders once. Decode only when every non-space character run in
    the cell is paired. Mixed or ordinary text is kept as-is and must still
    satisfy the labeled-field parser below.
    """

    tokens = cell.split()
    runs: list[int] = []
    for token in tokens:
        index = 0
        while index < len(token):
            end = index + 1
            while end < len(token) and token[end] == token[index]:
                end += 1
            runs.append(end - index)
            index = end
    is_consistently_doubled = len(runs) >= 3 and all(length % 2 == 0 for length in runs)
    if is_consistently_doubled:
        return " ".join(_decode_doubled_token(token) for token in tokens)
    return " ".join(tokens)


def _extract_tenant(tables: list[list[list[str | None]]]) -> tuple[str, str]:
    candidates: list[str] = []
    for table in tables:
        for row in table:
            for cell in row:
                if cell and _TENANT_LABEL_RE.search(_normalize_extracted_cell(cell)):
                    candidates.append(cell)

    if len(candidates) != 1:
        raise ExtractionError(
            f"esperada uma única linha INQ./CPF; encontradas {len(candidates)}"
        )

    decoded = _normalize_extracted_cell(candidates[0])
    if len(re.findall(r"\bINQ\.\s*:", decoded, re.IGNORECASE)) != 1:
        raise ExtractionError("rótulo INQ. ausente ou ambíguo")
    if len(re.findall(r"\bCPF\s*:", decoded, re.IGNORECASE)) != 1:
        raise ExtractionError("CPF ausente ou ambíguo na linha do inquilino")
    matches = list(_TENANT_LINE_RE.finditer(decoded))
    if len(matches) != 1:
        raise ExtractionError(
            "a linha INQ./CPF não contém um nome e um CPF claramente delimitados"
        )

    name = unicodedata.normalize(
        "NFC", " ".join(matches[0].group(1).split()).strip(" -")
    )
    cpf = matches[0].group(2)

    if "�" in name:
        raise ExtractionError("nome contém caractere ilegível; requer revisão")
    if not name or not any(character.isalpha() for character in name):
        raise ExtractionError("nome vazio ou fora do padrão textual esperado; requer revisão")
    if any(
        character == "�" or unicodedata.category(character).startswith("C")
        for character in name
    ):
        raise ExtractionError("nome fora do padrão textual esperado; requer revisão")
    if not _CPF_RE.fullmatch(cpf):
        raise ExtractionError("CPF fora do formato esperado; requer revisão")
    return cpf, name


def _fold_header(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).upper()
    return "".join(
        character for character in decomposed
        if not unicodedata.category(character).startswith("M")
    )


def _statement_columns(row: list[str | None]) -> tuple[int, int, int] | None:
    """Find due-date, history, and gross columns by their header labels."""

    if len(row) < 6:
        return None
    try:
        headers = [
            _fold_header(_normalize_extracted_cell(cell or ""))
            for cell in row
        ]
    except (IndexError, TypeError, ExtractionError):
        return None

    predicates = (
        lambda value: value == "VENCIMENTO",
        lambda value: value.startswith("HIST"),
        lambda value: value == "BRUTO",
        lambda value: value.startswith("PARTICIPA"),
        lambda value: value.startswith("DEBIT"),
        lambda value: value.startswith("CREDIT"),
    )
    indexes: list[int] = []
    for predicate in predicates:
        matches = [index for index, header in enumerate(headers) if predicate(header)]
        if len(matches) != 1:
            return None
        indexes.append(matches[0])
    if len(set(indexes)) != len(indexes):
        return None
    return indexes[0], indexes[1], indexes[2]


def _parse_brl(value: str) -> Decimal:
    value = value.strip()
    if not _BRL_RE.fullmatch(value):
        raise ExtractionError(f"valor bruto em formato inesperado: {value!r}")
    try:
        result = Decimal(value.replace(".", "").replace(",", "."))
    except InvalidOperation as exc:
        raise ExtractionError(f"valor bruto inválido: {value!r}") from exc
    return result.quantize(Decimal("0.01"))


def _extract_main_events(
    tables: list[list[list[str | None]]],
) -> list[tuple[RubricClassification, str, Decimal]]:
    matching_rows: list[tuple[RubricClassification, str, str | None]] = []
    unknown_rows: list[str] = []
    for table in tables:
        for header_index, header_row in enumerate(table):
            columns = _statement_columns(header_row)
            if columns is None:
                continue
            due_date_index, history_index, gross_index = columns
            for row in table[header_index + 1 :]:
                if len(row) <= max(due_date_index, history_index, gross_index):
                    continue
                due_date = (row[due_date_index] or "").strip()
                history = (row[history_index] or "").strip()
                if not _DATE_RE.fullmatch(due_date) or not history:
                    continue
                classification = classify_history(history)
                gross_cell = row[gross_index]
                if classification is RubricClassification.IGNORAR:
                    continue
                if classification is RubricClassification.DESCONHECIDO:
                    unknown_rows.append(history)
                    continue
                matching_rows.append((classification, history, gross_cell))

    if unknown_rows:
        labels = "; ".join(dict.fromkeys(unknown_rows))
        raise ExtractionError(
            f"rubrica financeira desconhecida no histórico {labels!r}; requer revisão"
        )
    if not matching_rows:
        raise ExtractionError(
            "nenhuma rubrica principal suportada identificada "
            "(ALUGUEL ou MULTA CONTRATUAL)"
        )

    events: list[tuple[RubricClassification, str, Decimal]] = []
    for classification, history, gross_cell in matching_rows:
        if gross_cell is None or not gross_cell.strip():
            raise ExtractionError(
                f"célula Bruto vazia na linha principal {history!r}"
            )
        events.append((classification, history, _parse_brl(gross_cell)))
    return events


def _extract_gross_rent(tables: list[list[list[str | None]]]) -> Decimal:
    """Compatibility helper for callers expecting one principal event."""

    events = _extract_main_events(tables)
    if len(events) != 1:
        raise ExtractionError(
            f"esperado um único evento principal; encontrados {len(events)}"
        )
    return events[0][2]


def _ocr_lines(words: list[OcrWord]) -> list[list[OcrWord]]:
    grouped: dict[tuple[int, int, int], list[OcrWord]] = {}
    for word in words:
        grouped.setdefault(word.line_id, []).append(word)
    return sorted(
        (sorted(line, key=lambda word: word.left) for line in grouped.values()),
        key=lambda line: (min(word.top for word in line), min(word.left for word in line)),
    )


def _join_ocr_line(words: list[OcrWord]) -> str:
    text = ""
    attach_left = {".", ",", ":", ";", "%", ")", "]"}
    attach_right = {"(", "["}
    for word in words:
        token = word.text
        if not text:
            text = token
        elif token in attach_left or text[-1:] in attach_right:
            text = text.rstrip() + token
        else:
            text += " " + token
    return text


def _extract_ocr_tenant(words: list[OcrWord]) -> tuple[str, str]:
    candidate_cells = [
        [_join_ocr_line(line)]
        for line in _ocr_lines(words)
        if _TENANT_LABEL_RE.search(_join_ocr_line(line))
    ]
    return _extract_tenant([candidate_cells])


def _ocr_header_key(word: OcrWord) -> str:
    folded = _fold_header(word.text)
    return "".join(character for character in folded if character.isalnum())


def _extract_ocr_main_events(
    words: list[OcrWord],
) -> list[tuple[RubricClassification, str, Decimal]]:
    lines = _ocr_lines(words)
    header_candidates: list[tuple[list[OcrWord], dict[str, OcrWord]]] = []
    header_checks = (
        ("due", lambda value: value == "VENCIMENTO"),
        ("history", lambda value: value.startswith("HIST")),
        ("gross", lambda value: value == "BRUTO"),
        ("participation", lambda value: value.startswith("PARTICIP")),
        ("debit", lambda value: value.startswith("DEBIT")),
        ("credit", lambda value: value.startswith("CREDIT")),
    )
    for line in lines:
        normalized = [(_ocr_header_key(word), word) for word in line]
        columns: dict[str, OcrWord] = {}
        for field, predicate in header_checks:
            matches = [word for key, word in normalized if predicate(key)]
            if len(matches) == 1:
                columns[field] = matches[0]
        if len(columns) == len(header_checks):
            header_candidates.append((line, columns))

    if len(header_candidates) != 1:
        raise ExtractionError(
            "cabeçalho da tabela principal não foi identificado com segurança por OCR"
        )

    header_line, columns = header_candidates[0]
    ordered_centers = [columns[field].center_x for field, _ in header_checks]
    if any(left >= right for left, right in zip(ordered_centers, ordered_centers[1:])):
        raise ExtractionError("ordem das colunas da tabela não pôde ser confirmada por OCR")
    header_bottom = max(word.top + word.height for word in header_line)
    history_gross_boundary = (
        columns["history"].center_x + columns["gross"].center_x
    ) / 2
    gross_participation_boundary = (
        columns["gross"].center_x + columns["participation"].center_x
    ) / 2
    due_history_boundary = (
        columns["due"].center_x + columns["history"].center_x
    ) / 2

    matching_rows: list[tuple[RubricClassification, str, list[OcrWord]]] = []
    unknown_rows: list[str] = []
    for line in lines:
        if max(word.top for word in line) <= header_bottom:
            continue
        ordered = sorted(line, key=lambda word: word.left)
        due_dates = [
            word
            for word in ordered
            if _DATE_RE.fullmatch(word.text)
            and word.center_x < due_history_boundary
        ]
        for due_date in due_dates:
            history_words = [
                word
                for word in ordered
                if word.left >= due_date.left + due_date.width
                and word.center_x < history_gross_boundary
                and word.text.strip("-:;,.")
            ]
            if not history_words:
                continue
            history = _join_ocr_line(history_words)
            classification = classify_history(history)
            gross_candidates = [
                word
                for word in ordered
                if _BRL_RE.fullmatch(word.text)
                and history_gross_boundary <= word.center_x < gross_participation_boundary
            ]
            if classification is RubricClassification.IGNORAR:
                break
            if classification is RubricClassification.DESCONHECIDO:
                unknown_rows.append(history)
                break
            matching_rows.append((classification, history, gross_candidates))
            break

    if unknown_rows:
        labels = "; ".join(dict.fromkeys(unknown_rows))
        raise ExtractionError(
            f"rubrica financeira desconhecida no histórico OCR {labels!r}; requer revisão"
        )
    if not matching_rows:
        raise ExtractionError(
            "nenhuma rubrica principal suportada identificada por OCR "
            "(ALUGUEL ou MULTA CONTRATUAL)"
        )

    events: list[tuple[RubricClassification, str, Decimal]] = []
    for classification, history, gross_candidates in matching_rows:
        if len(gross_candidates) != 1:
            raise ExtractionError(
                f"valor da coluna Bruto na linha principal {history!r} não foi "
                f"identificado com segurança por OCR; candidatos encontrados: "
                f"{len(gross_candidates)}"
            )
        events.append((classification, history, _parse_brl(gross_candidates[0].text)))
    return events


def _extract_ocr_gross_rent(words: list[OcrWord]) -> Decimal:
    """Compatibility helper for OCR tests/callers expecting a single event."""

    events = _extract_ocr_main_events(words)
    if len(events) != 1:
        raise ExtractionError(
            f"esperado um único evento principal; encontrados {len(events)}"
        )
    return events[0][2]


def extract_pdf_events(pdf_path: str | Path) -> list[RentalRecord]:
    """Extract every supported principal event from one supported PDF.

    ``source_file`` always preserves the input PDF's basename for traceability.
    Any unsupported, unreadable, missing or duplicate field raises
    :class:`ExtractionError` so the caller can route the file for review.
    """

    path = Path(pdf_path)
    tables = read_pdf_tables(path)
    has_native_table_text = any(
        cell and cell.strip()
        for table in tables
        for row in table
        for cell in row
    )
    if has_native_table_text:
        cpf, name = _extract_tenant(tables)
        events = _extract_main_events(tables)
    else:
        words = read_pdf_ocr_words(path)
        cpf, name = _extract_ocr_tenant(words)
        events = _extract_ocr_main_events(words)
    source = str(path.resolve())
    return [
        RentalRecord(
            source_file=path.name,
            cpf=cpf,
            name=name,
            rent=amount,
            source_path=source,
            category=category,
            original_history=history,
        )
        for category, history, amount in events
    ]


def extract_pdf(pdf_path: str | Path) -> RentalRecord:
    """Extract exactly one principal event for legacy single-record callers.

    Batch processing uses :func:`extract_pdf_events` so all supported events
    from a PDF are preserved. This wrapper fails clearly if the document has
    no event or more than one event rather than silently choosing one.
    """

    events = extract_pdf_events(pdf_path)
    if len(events) != 1:
        raise ExtractionError(
            f"esperado um único evento principal; encontrados {len(events)}"
        )
    return events[0]
