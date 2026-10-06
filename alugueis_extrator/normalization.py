"""Input normalization that does not infer missing data."""

import re
import unicodedata


_CPF_ALLOWED_RE = re.compile(r"[0-9.\-\s]+")


def normalize_cpf(value: str) -> str:
    """Return a formatted CPF string, preserving all eleven digits."""

    if not isinstance(value, str) or not _CPF_ALLOWED_RE.fullmatch(value):
        raise ValueError("CPF contém caracteres fora do formato permitido")
    digits = "".join(character for character in value if "0" <= character <= "9")
    if len(digits) != 11:
        raise ValueError("CPF deve conter exatamente 11 dígitos")
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"


def normalize_name(value: str) -> str:
    """Normalize Unicode and whitespace while keeping the extracted wording."""

    if not isinstance(value, str):
        raise ValueError("nome não é texto")
    name = unicodedata.normalize("NFC", " ".join(value.split())).strip()
    if any(character == "�" or unicodedata.category(character).startswith("C") for character in name):
        raise ValueError("nome contém caractere ilegível ou de controle")
    return name.upper()
