"""Centralized business classification for statement history rows."""

import unittest

from alugueis_extrator.rubrics import RubricClassification, classify_history


class RubricClassificationTests(unittest.TestCase):
    def test_supported_principal_rubrics_allow_parcel_suffixes(self) -> None:
        self.assertEqual(
            classify_history("Aluguel 04/12 - Ref. 10/06/2026"),
            RubricClassification.ALUGUEL,
        )
        self.assertEqual(
            classify_history("Multa Contratual"),
            RubricClassification.MULTA_CONTRATUAL,
        )

    def test_administrative_and_aggregate_rows_are_excluded(self) -> None:
        for label in (
            "Taxa ADM./Aluguel",
            "Taxa Administração",
            "Outras Taxas",
            "Outra Taxa",
            "Condomínio",
            "IPTU",
            "Subtotal",
            "Total",
            "Pagamento efetuado",
            "Créditos",
            "Débitos",
        ):
            with self.subTest(label=label):
                self.assertEqual(classify_history(label), RubricClassification.IGNORAR)

    def test_unlisted_rubric_requires_review_classification(self) -> None:
        self.assertEqual(
            classify_history("Cobrança Especial"),
            RubricClassification.DESCONHECIDO,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
