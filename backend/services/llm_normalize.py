"""
Normaliza a saída JSON do LLM (agora usando categorias dinâmicas) e retrocompatibilidade com UI antiga.
"""

def normalize_llm_extracted_data(doc_type: str, data: dict) -> dict:
    """
    Enriquece `data` com campos planos a partir de `grouped_info` se presentes.
    Como o LLM agora gera estruturas dinâmicas agnósticas, nós mantemos tudo que for gerado intacto
    e tentamos varrer o dicionário atrás de campos chave apenas para fallback da UI antiga, caso precise.
    """
    if not data or not isinstance(data, dict):
        return data

    out = dict(data)
    gi = out.get("grouped_info") or {}
    
    # Se o grouped_info já veio no formato dinâmico, o analisador do frontend vai percorrê-lo normalmente.
    # Mas para garantir que os cards antigos não quebrem, vamos tentar mapear chaves "conhecidas" se não existirem
    
    # Flatten simples baseado no título do grupo, para a UI retrocompativel
    if not out.get("dynamic_groups"):
        out["dynamic_groups"] = gi

    return out


def enrich_summary_with_purpose(data: dict) -> dict:
    """Se houver document_purpose e resumo curto, une para o cartão principal."""
    if not data or not isinstance(data, dict):
        return data
    out = dict(data)
    dp = out.get("document_purpose")
    ds = out.get("detailed_summary") or ""
    if isinstance(dp, str) and len(dp.strip()) > 15:
        if len(ds.strip()) < 120:
            out["detailed_summary"] = f"{dp.strip()}\n\n{ds.strip()}".strip()
    return out


def build_document_profile(data: dict, fallback_label: str) -> dict:
    """
    Perfil hierárquico e aberto do documento para cenários com muitos tipos.
    Mantém os campos livres da IA e preenche defaults úteis quando ausentes.
    """
    safe = data if isinstance(data, dict) else {}
    doc_type = (safe.get("document_type") or fallback_label or "Outro/Genérico")
    domain = (safe.get("document_domain") or "geral")
    subtype = (safe.get("document_subtype") or str(doc_type))
    purpose = (safe.get("document_purpose") or "")
    return {
        "type": str(doc_type).strip(),
        "domain": str(domain).strip(),
        "subtype": str(subtype).strip(),
        "purpose_preview": str(purpose).strip()[:240],
    }
