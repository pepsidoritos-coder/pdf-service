"""
Fallback inteligente por regex quando a IA não está disponível.
Extrai entidades, valores e padrões do texto bruto.
"""
import re
from backend.config import logger

# Ano com 2 dígitos: 00–30 → 2000–2030; 31–99 → 1931–1999.
# (Pivô 70 tratava 31–69 como 2031–2069; ex.: 45 virava 2045 em vez de 1945.)
_TWO_DIGIT_YEAR_PIVOT = 30

# Mensagem única para o usuário final (evita jargão técnico)
NOTE_NO_LLM = (
    "Nesta análise o modelo de IA não respondeu ou não está disponível. "
    "Os dados abaixo foram obtidos automaticamente a partir do texto do PDF — "
    "confira sempre com o documento original."
)


def _dedupe_preserve(items: list) -> list:
    """Remove duplicatas exatas mantendo a ordem."""
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _canonical_date_key(s: str):
    """
    Retorna (chave_canônica, texto_exibição) para deduplicar datas.
    Une variantes como 31/05/25 e 31/05/2025 na mesma chave.
    """
    s = s.strip()
    m = re.match(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})$", s)
    if not m:
        return None, s
    d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
    yi = int(y)
    if len(y) == 2:
        yi = 2000 + yi if yi <= _TWO_DIGIT_YEAR_PIVOT else 1900 + yi
    key = (d, mo, yi)
    display = f"{d:02d}/{mo:02d}/{yi}"
    return key, display


def _unique_dates(date_strings: list) -> list:
    """Datas únicas, formato DD/MM/AAAA quando possível."""
    seen = set()
    out = []
    for raw in date_strings:
        key, display = _canonical_date_key(raw)
        dedupe_key = key if key is not None else ("raw", raw)
        if dedupe_key not in seen:
            seen.add(dedupe_key)
            out.append(display)
    return out


def intelligent_fallback(text: str, doc_type: str) -> dict:
    """
    Análise por regex quando o LLM falha ou não responde.
    Sempre retorna dados úteis, mesmo sem IA.
    """
    logger.info(f"🔄 Executando fallback inteligente para tipo: {doc_type}")

    lines = [l.strip() for l in text.split('\n') if l.strip()]

    # Entidades comuns extraídas por regex
    entities = _extract_common_entities(text)

    result = {
        "classification_confidence": 75,
        "source": "fallback_regex",
        "common_entities": entities,
    }

    # Sempre gera um resumo baseado nas primeiras linhas
    preview_lines = [l for l in lines[:10] if len(l) > 10]
    result["detailed_summary"] = (
        f"Documento classificado como '{doc_type}'. "
        f"Contém {len(text.split())} palavras em {len(lines)} linhas. "
        f"Primeiras informações: {' | '.join(preview_lines[:3])}"
    )

    # Lógica específica por tipo
    _type_handlers = {
        "resume": _handle_resume,
        "educational_certificate": _handle_certificate,
        "bank_statement": _handle_bank_statement,
        "tax_document": _handle_tax_document,
        "medical_prescription": _handle_prescription,
        "medical_report": _handle_medical_report,
        "invoice": _handle_invoice,
        "contract": _handle_contract,
        "legal_document": _handle_legal,
        "technical_report": _handle_technical,
    }

    handler = _type_handlers.get(doc_type, _handle_generic)
    result.update(handler(text, lines, entities))

    logger.info(f"🎯 Fallback concluído: {len(result)} campos extraídos")
    return result


def _extract_common_entities(text: str) -> dict:
    """Extrai entidades comuns a qualquer tipo de documento."""
    dates_raw = re.findall(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", text)
    cnpjs_raw = re.findall(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", text)
    money_raw = re.findall(r"R\$\s*[\d.,]+", text)
    return {
        "emails": _dedupe_preserve(
            re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text)
        ),
        "phones": _dedupe_preserve(
            re.findall(r"\(?\d{2}\)?[-.\s]?\d{4,5}[-.\s]?\d{4}", text)
        ),
        "dates": _unique_dates(dates_raw),
        "cpfs": _dedupe_preserve(re.findall(r"\d{3}\.\d{3}\.\d{3}-\d{2}", text)),
        "cnpjs": _dedupe_preserve(cnpjs_raw),
        "monetary_values": _dedupe_preserve(money_raw),
        "urls": _dedupe_preserve(
            re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', text)
        ),
    }


def _handle_resume(text, lines, entities):
    """Extração específica para currículos."""
    text_lower = text.lower()
    name = lines[0] if lines else "Não identificado"

    # Skills técnicas (palavras capitalizadas com 4+ chars)
    tech_words = re.findall(r'\b[A-Z][a-zA-Z+#]{3,}\b', text)
    skills = list(set(tech_words))[:15]

    # Seções do currículo
    sections = [l for l in lines if len(l) < 40 and any(
        k in l.lower() for k in ["experiência", "formação", "educação", "habilidades",
                                   "competências", "idiomas", "certificações", "objetivo"]
    )]

    return {
        "personal_info": {
            "name": name,
            "emails": entities["emails"],
            "phones": entities["phones"],
            "urls": entities["urls"]
        },
        "skills_found": skills,
        "sections_found": sections,
        "dates_found": entities["dates"],
        "key_findings": [
            f"Nome identificado: {name}",
            f"{len(skills)} competências técnicas encontradas",
            f"{len(entities['emails'])} email(s) encontrado(s)",
            f"{len(sections)} seções do currículo identificadas"
        ],
        "note": NOTE_NO_LLM
    }


def _handle_certificate(text, lines, entities):
    """Extração para certificados/diplomas."""
    name = lines[0] if lines else "Não identificado"
    institutions = [l for l in lines if any(
        k in l.lower() for k in ["universidade", "faculdade", "instituto", "centro", "escola"]
    )]
    courses = [l for l in lines if len(l) > 20 and not any(
        k in l.lower() for k in ["universidade", "faculdade", "certificado", "diploma"]
    )]

    return {
        "student_name": name,
        "institution": institutions[0] if institutions else "Não identificado",
        "course": courses[0] if courses else "Não identificado",
        "dates": entities["dates"],
        "key_findings": [
            f"Estudante: {name}",
            f"Instituição: {institutions[0] if institutions else 'não identificada'}",
            f"{len(entities['dates'])} datas encontradas"
        ],
        "note": NOTE_NO_LLM
    }


def _handle_bank_statement(text, lines, entities):
    """Extração para extratos bancários."""
    amounts = entities["monetary_values"]

    # Calcula maior valor fora do f-string (backslash não permitido em f-string no Python < 3.12)
    _pat = re.compile(r'[R$.\s]')
    def _to_float(v):
        try:
            return float(_pat.sub('', v).replace(',', '.'))
        except ValueError:
            return 0.0

    maior_valor = max(amounts, key=_to_float) if amounts else 'N/A'

    return {
        "account_holder": lines[0] if lines else "Não identificado",
        "values_found": amounts[:10],
        "total_transactions": len(amounts),
        "dates": entities["dates"],
        "key_findings": [
            f"{len(amounts)} valores monetários encontrados",
            f"{len(entities['dates'])} datas de movimentação",
            f"Maior valor: {maior_valor}"
        ],
        "note": NOTE_NO_LLM
    }


def _handle_prescription(text, lines, entities):
    """Extração para receitas médicas."""
    meds = re.findall(r'([A-Z][a-zA-Zà-ú\s]+)\s+(\d+\s*mg|\d+\s*ml|\d+\s*mcg)', text)
    crm = re.findall(r'CRM[:\s]*(\d+)', text, re.IGNORECASE)

    return {
        "medications": [{"name": m[0].strip(), "dosage": m[1]} for m in meds[:10]],
        "doctor_crm": crm[0] if crm else "Não encontrado",
        "dates": entities["dates"],
        "key_findings": [
            f"{len(meds)} medicamento(s) identificado(s)",
            f"CRM: {crm[0] if crm else 'não encontrado'}",
        ],
        "note": NOTE_NO_LLM
    }


def _handle_tax_document(text, lines, entities):
    """Extração específica para IRPF e documentos fiscais/tributários."""
    text_lower = text.lower()
    years = re.findall(r"(?:20\d{2})", text)
    years = _dedupe_preserve(years)[:8]

    ano_calendario = re.findall(r"ano[-\s]*calend[aá]rio[:\s-]*(20\d{2})", text, re.IGNORECASE)
    exercicio = re.findall(r"exerc[ií]cio[:\s-]*(20\d{2})", text, re.IGNORECASE)
    cpf = entities.get("cpfs", [])
    valores = entities.get("monetary_values", [])

    sinais = {
        "irpf": "irpf" in text_lower or "imposto de renda" in text_lower,
        "receita_federal": "receita federal" in text_lower,
        "darf": "darf" in text_lower,
        "restituicao": "restitui" in text_lower,
    }

    findings = []
    if sinais["irpf"]:
        findings.append("Documento com forte indicação de declaração/imposto de renda (IRPF).")
    if ano_calendario:
        findings.append(f"Ano-calendário identificado: {ano_calendario[0]}.")
    if exercicio:
        findings.append(f"Exercício identificado: {exercicio[0]}.")
    if cpf:
        findings.append(f"{len(cpf)} CPF(s) encontrado(s).")
    if valores:
        findings.append(f"{len(valores)} valor(es) monetário(s) detectado(s).")

    return {
        "document_scope": "tributario_fiscal",
        "tax_document_type": "IRPF/Declaração Fiscal" if sinais["irpf"] else "Documento fiscal",
        "taxpayer_cpfs": cpf,
        "ano_calendario": ano_calendario[0] if ano_calendario else None,
        "exercicio": exercicio[0] if exercicio else None,
        "years_found": years,
        "values_found": valores[:15],
        "dates": entities["dates"],
        "key_findings": findings or [
            "Documento fiscal identificado por padrões textuais.",
            f"{len(years)} ano(s) e {len(valores)} valor(es) detectados."
        ],
        "note": NOTE_NO_LLM,
    }


def _handle_medical_report(text, lines, entities):
    """Extração para laudos/prontuários médicos."""
    crm = re.findall(r'CRM[:\s]*(\d+)', text, re.IGNORECASE)
    cid = re.findall(r'CID[:\s-]*([A-Z]\d{2,3})', text, re.IGNORECASE)

    return {
        "doctor_crm": crm[0] if crm else "Não encontrado",
        "cid_codes": cid,
        "dates": entities["dates"],
        "key_findings": [
            f"CRM: {crm[0] if crm else 'não encontrado'}",
            f"CIDs encontrados: {', '.join(cid) if cid else 'nenhum'}",
        ],
        "note": NOTE_NO_LLM
    }


def _handle_invoice(text, lines, entities):
    """Extração para notas fiscais."""
    nf_number = re.findall(r'(?:NF|Nota\s+Fiscal)[:\s-]*(\d+)', text, re.IGNORECASE)
    chave = re.findall(r'\d{44}', text)
    nf_display = nf_number[0] if nf_number else None
    cnpjs = entities["cnpjs"]
    money = entities["monetary_values"]

    findings = []
    if nf_display:
        findings.append(f"Nota fiscal identificada: nº {nf_display}.")
    if cnpjs:
        shown = ", ".join(cnpjs[:3])
        suffix = f" (+{len(cnpjs) - 3} outro(s))" if len(cnpjs) > 3 else ""
        findings.append(f"CNPJ(s) no documento: {shown}{suffix}.")
    else:
        findings.append("Nenhum CNPJ no formato XX.XXX.XXX/XXXX-XX encontrado no texto.")
    if money:
        shown_m = ", ".join(money[:5])
        suffix_m = f" (+{len(money) - 5} outro(s))" if len(money) > 5 else ""
        findings.append(f"Valores em R$: {shown_m}{suffix_m}.")
    else:
        findings.append("Nenhum valor em R$ no formato esperado foi encontrado.")

    preview = " | ".join([l for l in lines[:6] if len(l.strip()) > 8][:3])
    summary_parts = ["Este PDF foi classificado como nota fiscal ou documento fiscal semelhante."]
    if nf_display:
        summary_parts.append(f"Número da NF: {nf_display}.")
    if cnpjs:
        summary_parts.append(f"{len(cnpjs)} CNPJ identificado(s) no texto.")
    if money:
        summary_parts.append(f"{len(money)} ocorrência(s) de valores em reais.")
    if preview:
        summary_parts.append(f"Trecho inicial: {preview}")
    friendly_summary = " ".join(summary_parts)

    return {
        "invoice_number": nf_number[0] if nf_number else "Não encontrado",
        "access_key": chave[0] if chave else "Não encontrada",
        "cnpjs": cnpjs,
        "values": money[:10],
        "values_found": money[:10],
        "dates": entities["dates"],
        "key_findings": findings,
        "detailed_summary": friendly_summary,
        "note": NOTE_NO_LLM,
    }


def _handle_contract(text, lines, entities):
    """Extração para contratos."""
    clauses = [l for l in lines if re.match(r'^(CLÁUSULA|Cláusula|cláusula)\s', l)]

    return {
        "parties_cpf_cnpj": entities["cpfs"] + entities["cnpjs"],
        "clauses_count": len(clauses),
        "values": entities["monetary_values"][:5],
        "dates": entities["dates"],
        "key_findings": [
            f"{len(clauses)} cláusulas identificadas",
            f"{len(entities['cpfs'])} CPF(s) e {len(entities['cnpjs'])} CNPJ(s)",
        ],
        "note": NOTE_NO_LLM
    }


def _handle_legal(text, lines, entities):
    """Extração para documentos jurídicos."""
    processo = re.findall(r'(?:Processo|Autos)\s*(?:n[ºo°]?\.?\s*)(\d[\d./-]+)', text, re.IGNORECASE)
    oab = re.findall(r'OAB[:/\s]*([A-Z]{2})\s*(\d+)', text, re.IGNORECASE)

    return {
        "case_number": processo[0] if processo else "Não encontrado",
        "lawyers_oab": [f"OAB/{o[0]} {o[1]}" for o in oab],
        "dates": entities["dates"],
        "key_findings": [
            f"Processo: {processo[0] if processo else 'não encontrado'}",
            f"{len(oab)} advogado(s) identificado(s)",
        ],
        "note": NOTE_NO_LLM
    }


def _handle_technical(text, lines, entities):
    """Extração para relatórios técnicos."""
    sections = [l for l in lines if len(l) < 50 and l.isupper() or (
        len(l) < 60 and any(k in l.lower() for k in [
            "introdução", "metodologia", "resultados", "conclusão",
            "referências", "abstract", "objetivo"
        ])
    )]

    return {
        "sections_found": sections[:10],
        "dates": entities["dates"],
        "urls": entities["urls"],
        "key_findings": [
            f"{len(sections)} seções do relatório identificadas",
            f"{len(text.split())} palavras no documento",
        ],
        "note": NOTE_NO_LLM
    }


def _handle_generic(text, lines, entities):
    """Extração genérica para qualquer documento."""
    return {
        "summary_preview": " ".join(lines[:5])[:300],
        "word_count": len(text.split()),
        "line_count": len(lines),
        "key_findings": [
            f"Documento com {len(text.split())} palavras",
            f"{len(entities['emails'])} email(s), {len(entities['phones'])} telefone(s)",
            f"{len(entities['monetary_values'])} valor(es) monetário(s)",
        ],
        "note": NOTE_NO_LLM
    }
