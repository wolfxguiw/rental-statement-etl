"""Central classification rules for principal statement history rows."""

from enum import Enum
import re
import unicodedata


class RubricClassification(str, Enum):
    """A supported main event, a known non-event, or a row needing review."""

    ALUGUEL = "ALUGUEL"
    MULTA_CONTRATUAL = "MULTA_CONTRATUAL"
    IGNORAR = "IGNORAR"
    DESCONHECIDO = "DESCONHECIDO"


def normalize_history(text: str) -> str:
    """Fold accents and punctuation while retaining words and parcel digits."""

    decomposed = unicodedata.normalize("NFKD", text).upper()
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.category(character).startswith("M")
    )
    return " ".join(re.findall(r"[A-Z0-9]+", without_marks))


def _starts_with_phrase(history: str, phrase: str) -> bool:
    return history == phrase or history.startswith(phrase + " ")


def classify_history(text: str) -> RubricClassification:
    """Classify only explicitly supported principal rubrics.

    Supported categories are matched at the start of the history. Known fees,
    totals and aggregate movements are excluded centrally. A new financial
    history remains unknown so the caller can send the statement for review.
    """

    history = normalize_history(text)
    if not history:
        return RubricClassification.IGNORAR

    if _starts_with_phrase(history, "ALUGUEL"):
        return RubricClassification.ALUGUEL
    if _starts_with_phrase(history, "MULTA CONTRATUAL"):
        return RubricClassification.MULTA_CONTRATUAL

    ignored_prefixes = (
        "TAXA",
        "TAXAS",
        "OUTRA TAXA",
        "OUTRAS TAXA",
        "OUTRAS TAXAS",
        "ADMINISTRACAO",
        "ADMINISTRATIVA",
        "ADMINISTRATIVO",
        "CONDOMINIO",
        "IPTU",
        "SUBTOTAL",
        "TOTAL",
        "PAGAMENTO",
        "PAGO",
        "CREDITO",
        "CREDITOS",
        "DEBITO",
        "DEBITOS",
    )
    if any(_starts_with_phrase(history, prefix) for prefix in ignored_prefixes):
        return RubricClassification.IGNORAR
    return RubricClassification.DESCONHECIDO
