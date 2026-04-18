"""
Rotas de análise de PDFs.
Blueprint Flask para /health e /analyze.
"""
import time
from flask import Blueprint, request, jsonify
from backend.config import DOCUMENT_TYPES, logger
from backend.services.pdf_extractor import extract_text
from backend.services.classifier import classify_document
from backend.services.llm_normalize import (
    build_document_profile,
    enrich_summary_with_purpose,
    normalize_llm_extracted_data,
)
from backend.services.llm_client import (
    agent_debug_ndjson,
    call_llm,
    generate_missing_purpose,
    hint_pt_for_llm_error,
    probe_llm_connectivity,
)
from backend.utils.fallback_parser import intelligent_fallback

analyze_bp = Blueprint("analyze", __name__)


def _is_effectively_empty(val) -> bool:
    """Trata string só com espaço / listas vazias como ausência de valor."""
    if val is None:
        return True
    if isinstance(val, bool):
        return False
    if isinstance(val, str):
        return len(val.strip()) < 2
    if isinstance(val, (list, tuple, set)):
        return len(val) == 0
    if isinstance(val, dict):
        return len(val) == 0
    return False


@analyze_bp.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "pdf-service",
        "version": "6.0-local-llm"
    }), 200


@analyze_bp.route("/health/llm")
def health_llm():
    """Verifica se o servidor OpenAI-compatible (LM Studio, etc.) responde em GET /v1/models."""
    out = probe_llm_connectivity()
    # #region agent log
    out["health_llm_marker"] = "health-llm-marker-2026-04-17-a"
    # #endregion
    return jsonify(out), 200


@analyze_bp.route("/analyze", methods=["POST"])
def analyze_pdf():
    """
    Endpoint principal de análise de PDF.
    Pipeline: Upload → Extração → Classificação → IA → Fallback → Resposta
    """
    start_time = time.time()

    # Validação de entrada
    if "file" not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    file = request.files["file"]
    if file.filename == "" or not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Apenas PDFs válidos"}), 400

    try:
        # 1. EXTRAÇÃO do PDF
        pdf_bytes = file.read()
        extraction = extract_text(pdf_bytes)
        raw_text = extraction["raw_text"]
        extraction_quality = extraction.get("extraction_quality", {})

        if not raw_text.strip():
            return jsonify({"error": "PDF vazio ou não legível"}), 400

        logger.info(f"📄 PDF: {file.filename} | {len(raw_text)} chars | {extraction['num_pages']} páginas")

        # 2. CLASSIFICAÇÃO do documento
        classification = classify_document(raw_text)
        doc_type = classification["doc_type"]
        logger.info(f"🎯 Tipo: {classification['label']} (confiança: {classification['confidence']}%)")

        # 3. ANÁLISE via IA (leitura profunda: contexto longo e/ou trechos + síntese)
        ai_result = None
        llm_coverage: dict = {}
        analysis_method = "fallback_intelligent"
        try:
            ai_raw, llm_cov = call_llm(raw_text, doc_type)
            llm_coverage = llm_cov or {}
            if ai_raw:
                ai_result = enrich_summary_with_purpose(
                    normalize_llm_extracted_data(doc_type, ai_raw)
                )
                analysis_method = "ai"
                logger.info(
                    f"✅ IA respondeu em {time.time() - start_time:.1f}s "
                    f"(estratégia={llm_coverage.get('strategy')})"
                )
        except Exception as e:
            err_s = str(e)[:500]
            llm_coverage = {"error": err_s[:200], "strategy": "error"}
            hp = hint_pt_for_llm_error(err_s)
            if hp:
                llm_coverage["hint_pt"] = hp
            # #region agent log
            agent_debug_ndjson(
                "H2",
                "analyze.py:analyze_pdf",
                "llm_call_exception",
                {"err_type": type(e).__name__, "err": err_s[:220]},
            )
            # #endregion
            logger.warning(f"⚠️ IA falhou ({type(e).__name__}): {str(e)[:100]}")

        # 4. FALLBACK inteligente (sempre executa para complementar)
        fallback_result = intelligent_fallback(raw_text, doc_type)

        # 5. MERGE (IA na frente; fallback só preenche o que está vazio ou inútil)
        final_result = dict(ai_result) if ai_result else {}
        skip_merge = {"source"}
        for key, value in fallback_result.items():
            if key in skip_merge:
                continue
            if key not in final_result or _is_effectively_empty(final_result.get(key)):
                final_result[key] = value

        # 5.1 Se "Propósito" vier vazio, faz uma chamada curta para preencher com IA.
        purpose_missing = _is_effectively_empty(final_result.get("document_purpose"))
        if purpose_missing and analysis_method == "ai":
            ai_purpose = generate_missing_purpose(
                raw_text,
                doc_type,
                str(final_result.get("detailed_summary") or ""),
            )
            if ai_purpose:
                final_result["document_purpose"] = ai_purpose

        profile = build_document_profile(
            final_result,
            DOCUMENT_TYPES.get(doc_type, doc_type),
        )

        # 6. RESPOSTA estruturada
        quality_warnings = []
        if extraction_quality.get("low_text_density"):
            quality_warnings.append(
                "Texto extraído muito baixo para a quantidade de páginas. "
                "O PDF pode ser foto/scan e pode exigir OCR para máxima precisão."
            )
        response = {
            "filename": file.filename,
            "document_type": doc_type,
            "document_type_label": DOCUMENT_TYPES.get(doc_type, doc_type),
            "document_type_open_set": classification.get("open_set", False),
            "document_type_reason": classification.get("reason"),
            "confidence": classification["confidence"],
            "text_length": len(raw_text),
            "pages": extraction["num_pages"],
            "pdf_metadata": extraction.get("pdf_metadata", {}),
            "extraction_quality": extraction_quality,
            "quality_warnings": quality_warnings,
            "processing_time_sec": round(time.time() - start_time, 2),
            "analysis_method": analysis_method,
            "classification_scores": classification.get("scores", {}),
            "document_profile": profile,
            "extracted_data": final_result,
            "llm_coverage": llm_coverage,
        }
        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Erro crítico: {e}", exc_info=True)
        return jsonify({"error": "Erro interno ao processar"}), 500
