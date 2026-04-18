"""
Classificador de tipos de documentos por keyword scoring.
"""
import json
import unicodedata
from backend.config import DOCUMENT_TYPES, logger


# Keywords por tipo de documento (peso implícito: mais keywords = mais específico)
_KEYWORD_MAP = {
    "resume": [
        "currículo", "curriculum vitae", "resume", "experiência profissional",
        "formação acadêmica", "habilidades", "competências", "objetivo profissional",
        "dados pessoais", "idiomas", "linkedin", "github", "portfólio"
    ],
    "medical_prescription": [
        "receita médica", "prescrição", "medicamento", "dosagem", "médico",
        "crm", "paciente", "tomar", "comprimido", "mg", "via oral",
        "posologia", "uso contínuo", "uso interno"
    ],
    "medical_report": [
        "prontuário", "laudo", "exame", "diagnóstico", "sintomas",
        "tratamento", "anamnese", "evolução", "hemograma", "ultrassom",
        "ressonância", "tomografia", "cid"
    ],
    "bank_statement": [
        "extrato bancário", "conta corrente", "saldo", "débito", "crédito",
        "agência", "banco", "transação", "movimentação", "pix",
        "transferência", "tarifa", "rendimento", "saldo anterior", "saldo final",
        "lançamentos", "periodo"
    ],
    "tax_document": [
        "imposto de renda", "irpf", "declaracao de ajuste anual", "declaracao",
        "receita federal", "cpf do contribuinte", "ano-calendario", "exercicio",
        "rendimentos tributaveis", "imposto devido", "imposto a restituir",
        "carne-leao", "bens e direitos", "demonstrativo de apuracao",
        "codigo da receita", "darf", "fisco", "declaracao retificadora"
    ],
    "invoice": [
        "nota fiscal", "nf-e", "nfe", "fatura", "cnpj", "valor total",
        "imposto", "emitente", "destinatário", "icms", "iss",
        "base de cálculo", "chave de acesso"
    ],
    "educational_certificate": [
        "certificado", "diploma", "certificação", "concluiu", "graduação",
        "universidade", "faculdade", "carga horária", "coordenador",
        "bacharelado", "licenciatura", "pós-graduação", "mestrado"
    ],
    "contract": [
        "contrato", "cláusula", "vigência", "partes contratantes", "obrigações",
        "rescisão", "foro", "assinatura", "testemunha", "contratante",
        "contratado", "objeto do contrato"
    ],
    "legal_document": [
        "processo nº", "autos", "sentença", "despacho", "petição",
        "advogado", "oab", "juízo", "vara", "tribunal",
        "intimação", "mandado", "recurso"
    ],
    "technical_report": [
        "relatório técnico", "metodologia", "resultados", "conclusão",
        "análise", "dados", "gráfico", "tabela", "referências",
        "abstract", "introdução", "objetivo geral"
    ],
    "qa_assessment": [
        "questão", "questoes", "pergunta", "resposta", "alternativa",
        "gabarito", "prova", "enunciado", "item", "marque a alternativa"
    ],
    "identity_document": [
        "registro geral", "rg", "cpf", "carteira de identidade", "cnh",
        "data de nascimento", "nome da mae", "orgao emissor", "nacionalidade"
    ],
}


def _normalize_text(value: str) -> str:
    """Normaliza para comparação robusta (sem acentos, lowercase)."""
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower()


def classify_document(text: str) -> dict:
    """
    Classifica o tipo de documento baseado em keywords.

    Returns:
        dict com: doc_type, label, confidence, scores
    """
    text_lower = _normalize_text(text)
    scores = {}
    text_tokens = text_lower.split()
    text_len = len(text_lower)

    for doc_type, keywords in _KEYWORD_MAP.items():
        score = sum(1 for kw in keywords if _normalize_text(kw) in text_lower)
        if score > 0:
            scores[doc_type] = score

    if not scores:
        return {
            "doc_type": "other",
            "label": DOCUMENT_TYPES["other"],
            "confidence": 0,
            "scores": {},
            "open_set": True,
            "reason": "no_keyword_match",
        }

    best_type = max(scores, key=scores.get)
    max_score = scores[best_type]
    total_keywords = len(_KEYWORD_MAP.get(best_type, []))
    confidence = min(100, int((max_score / max(total_keywords, 1)) * 100))

    # Open-set guard: evita forçar um tipo quando o sinal é fraco.
    # Em cenários com muitos tipos de PDFs, é melhor cair em "other" do que classificar errado.
    weak_signal = max_score < 2 or confidence < 12
    very_short_or_sparse = text_len < 120 or len(text_tokens) < 25
    if weak_signal or very_short_or_sparse:
        logger.info(
            "📊 Classificação open-set: sinal fraco "
            f"(best_type={best_type}, score={max_score}, confidence={confidence}%)"
        )
        return {
            "doc_type": "other",
            "label": DOCUMENT_TYPES["other"],
            "confidence": min(confidence, 25),
            "scores": scores,
            "open_set": True,
            "reason": "weak_signal_or_sparse_text",
        }

    logger.info(f"📊 Scores: {json.dumps(scores)}")
    logger.info(f"🎯 Classificado: {best_type} (confiança: {confidence}%)")

    return {
        "doc_type": best_type,
        "label": DOCUMENT_TYPES.get(best_type, best_type),
        "confidence": confidence,
        "scores": scores,
        "open_set": False,
        "reason": "keyword_match",
    }
