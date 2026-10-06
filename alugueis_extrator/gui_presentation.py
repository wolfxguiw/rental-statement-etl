"""Human-readable result text for the GUI, kept outside the batch parser."""

from .models import BatchReport, ProcessingIssue, ProcessingWarning


def result_summary(report: BatchReport) -> str:
    return "\n".join(
        (
            f"PDFs encontrados: {report.total_pdfs}",
            f"Documentos processados com sucesso: {report.processed}",
            f"Registros gerados: {report.records_generated}",
            f"Documentos para revisão: {report.review_count}",
            "Falhas técnicas do lote: 0",
            f"Avisos: {len(report.warnings)}",
        )
    )


def friendly_issue(issue: ProcessingIssue) -> str:
    reason = issue.reason.casefold()
    if issue.stage == "pdf_read":
        return "Não foi possível abrir este PDF. Verifique se o arquivo está íntegro."
    if "rubrica financeira desconhecida" in reason:
        return "Rubrica financeira não reconhecida; o documento requer revisão."
    if "aluguel" in reason or "rubrica principal suportada" in reason:
        return "Valor do aluguel não identificado com segurança."
    if "cpf" in reason or "inq." in reason:
        return "CPF ou nome do inquilino ausente, inválido ou ambíguo."
    if issue.stage == "validation":
        return "Os dados extraídos não passaram pela validação."
    return "Formato ou campos não reconhecidos com segurança; requer revisão."


def friendly_warning(warning: ProcessingWarning) -> str:
    reason = warning.reason.casefold()
    if "binariamente idêntico" in reason:
        return "PDF idêntico a outro arquivo; esta cópia foi ignorada."
    if "possível duplicidade" in reason:
        return "Possível duplicidade. O registro foi mantido no Excel."
    return "Aviso de processamento; consulte os diagnósticos para detalhes."


def result_details(report: BatchReport) -> str:
    lines: list[str] = []
    for issue in report.errors:
        lines.extend((issue.file, friendly_issue(issue), ""))
    for warning in report.warnings:
        lines.extend((warning.file, friendly_warning(warning), ""))
    return "\n".join(lines).strip()
