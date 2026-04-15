import os, logging, json, requests, fitz, re, time
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

OLLAMA_API = os.getenv("OLLAMA_API", "http://127.0.0.1:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "phi3:mini")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_MB", 10)) * 1024 * 1024
MAX_TEXT_CHARS = int(os.getenv("MAX_TEXT_CHARS", 800))
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", 45))  # ← Reduzido para 45s

logging.basicConfig(level=logging.INFO, format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"pdf-service","message":"%(message)s"}')
logger = logging.getLogger(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE


@app.route("/health")
def health():
    return jsonify({"status":"healthy","service":"pdf-service","version":"2.3-fallback"}), 200


@app.route("/analyze", methods=["POST"])
def analyze_pdf():
    start_time = time.time()
    
    if "file" not in request.files:
        return jsonify({"error":"Nenhum arquivo enviado"}), 400
    file = request.files["file"]
    if file.filename == "" or not file.filename.lower().endswith(".pdf"):
        return jsonify({"error":"Apenas PDFs válidos"}), 400

    try:
        # 1️⃣ Extração (sempre funciona)
        doc = fitz.open(stream=file.read(), filetype="pdf")
        raw_text = "\n".join(p.get_text() for p in doc)
        doc.close()
        if not raw_text.strip():
            return jsonify({"error":"PDF vazio ou não legível"}), 400

        truncated = raw_text[:MAX_TEXT_CHARS]
        logger.info(f"Extraído: {len(raw_text)} → {len(truncated)} chars | Modelo: {LLM_MODEL}")

        # 2️⃣ TENTA IA com timeout curto + fallback automático
        ai_result = None
        try:
            ai_result = _call_ollama(truncated)
            logger.info(f"✅ IA respondeu em {time.time()-start_time:.1f}s")
        except Exception as e:
            logger.warning(f"⚠️ IA falhou ({type(e).__name__}), usando fallback: {str(e)[:100]}")

        # 3️⃣ Retorna resultado (IA ou fallback)
        response = {
            "filename": file.filename,
            "text_length": len(raw_text),
            "truncated_to": MAX_TEXT_CHARS,
            "model_used": LLM_MODEL,
            "processing_time_sec": round(time.time() - start_time, 2),
            "ai_analysis": ai_result or _fallback_analysis(raw_text[:500])
        }
        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Erro crítico: {e}", exc_info=True)
        return jsonify({"error":"Erro interno ao processar"}), 500


def _call_ollama(text):
    """Chama Ollama com timeout curto e parsing robusto"""
    prompt = f"""Return ONLY valid JSON, no explanations:
{{
  "summary": "One sentence summary",
  "key_topics": ["topic1", "topic2"],
  "glossary": {{"term": "definition"}},
  "next_steps": ["action1"]
}}
Text: {text}"""

    payload = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0, "num_ctx": 512, "num_predict": 150}
    }
    if "phi3" in LLM_MODEL or "qwen" in LLM_MODEL:
        payload["format"] = "json"

    resp = requests.post(f"{OLLAMA_API}/api/generate", json=payload, timeout=OLLAMA_TIMEOUT)
    resp.raise_for_status()
    
    llm_text = resp.json().get("response", "").strip()
    return _parse_json_fallback(llm_text)


def _parse_json_fallback(text):
    """Extrai JSON de texto misto"""
    for try_parse in [
        lambda: json.loads(text),
        lambda: json.loads(re.search(r'\{.*\}', text, re.DOTALL).group()),
        lambda: json.loads(re.search(r'\[.*\]', text, re.DOTALL).group()),
    ]:
        try:
            return try_parse()
        except:
            continue
    return None  # Signal to use text fallback


def _fallback_analysis(text_sample):
    """Fallback quando a IA falha: retorna análise básica baseada em regras"""
    # Extrai primeiras linhas como "resumo"
    lines = [l.strip() for l in text_sample.split('\n') if l.strip()]
    
    # Tenta identificar possíveis tópicos (palavras-chave comuns em docs técnicos)
    keywords = ["docker", "kubernetes", "aws", "azure", "terraform", "ci/cd", "python", "api", "cloud", "devops"]
    found_topics = [kw.upper() for kw in keywords if kw in text_sample.lower()][:3]
    
    return {
        "summary": lines[0] if lines else "Texto extraído com sucesso",
        "key_topics": found_topics if found_topics else ["Conteúdo técnico", "Documento processado"],
        "glossary": {},
        "next_steps": ["Revisar conteúdo completo", "Validar informações"],
        "note": "Análise por fallback (IA indisponível ou lenta). Texto extraído com sucesso."
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)), debug=False)