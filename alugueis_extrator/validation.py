"""Business validation for parsed rental records."""

from dataclasses import replace
from decimal import Decimal, InvalidOperation

from .errors import ValidationError
from .models import RentalRecord
from .normalization import normalize_cpf, normalize_name
from .rubrics import RubricClassification


def is_valid_cpf(value: str) -> bool:
    """Check CPF length, repeated-digit rejection, and both check digits."""

    try:
        formatted = normalize_cpf(value)
    except ValueError:
        return False
    digits = [int(character) for character in formatted if character.isdigit()]
    if len(set(digits)) == 1:
        return False

    def check_digit(prefix: list[int], weights: range) -> int:
        result = (sum(digit * weight for digit, weight in zip(prefix, weights)) * 10) % 11
        return 0 if result == 10 else result

    return (
        digits[9] == check_digit(digits[:9], range(10, 1, -1))
        and digits[10] == check_digit(digits[:10], range(11, 1, -1))
    )


def validate_record(record: RentalRecord) -> RentalRecord:
    """Normalize and validate all fields without consulting fixture data."""

    try:
        cpf = normalize_cpf(record.cpf)
    except ValueError as exc:
        raise ValidationError(f"CPF ausente ou inválido: {exc}") from exc
    if not is_valid_cpf(cpf):
        raise ValidationError("CPF inválido: dígitos verificadores não conferem")

    try:
        name = normalize_name(record.name)
    except ValueError as exc:
        raise ValidationError(f"nome inválido: {exc}") from exc
    if not name:
        raise ValidationError("nome do inquilino vazio")

    try:
        rent = record.rent if isinstance(record.rent, Decimal) else Decimal(str(record.rent))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("valor do aluguel não é numérico") from exc
    if not rent.is_finite():
        raise ValidationError("valor do aluguel não é finito")
    try:
        cents = rent.quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValidationError("valor do aluguel não pode ser representado em centavos") from exc
    if rent != cents:
        raise ValidationError("valor do aluguel contém fração menor que um centavo")
    if cents <= 0:
        raise ValidationError("valor do aluguel deve ser positivo")
    if not record.source_file:
        raise ValidationError("arquivo PDF de origem ausente")

    try:
        category = RubricClassification(record.category)
    except (TypeError, ValueError) as exc:
        raise ValidationError("categoria da rubrica ausente ou inválida") from exc
    if category not in {
        RubricClassification.ALUGUEL,
        RubricClassification.MULTA_CONTRATUAL,
    }:
        raise ValidationError("categoria da rubrica não é um evento principal suportado")
    original_history = " ".join(str(record.original_history).split())
    if not original_history:
        raise ValidationError("histórico original da rubrica vazio")

    return replace(
        record,
        cpf=cpf,
        name=name,
        rent=cents,
        category=category,
        original_history=original_history,
    )
