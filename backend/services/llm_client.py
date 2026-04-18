"""
Cliente LLM local via API compatível com OpenAI (Chat Completions).
Recomendado: LM Studio, llama.cpp server ou qualquer host com modelo Qwen leve em GGUF.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import requests

from backend.config import (
    DOCUMENT_TYPES,
    LLM_CHUNK_OVERLAP,
    LLM_CHUNK_SIZE,
    LLM_MAX_CHUNKS,
    LLM_HEAD_TAIL_FACTOR,
    LLM_API_BASE,
    LLM_API_KEY,
    LLM_JSON_MODE,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_CONNECT_TIMEOUT,
    LLM_TIMEOUT,
    LOG_DIR,
    MAX_TEXT_CHARS,
    logger,
)

HINT_CONNECTION_REFUSED_PT = (
    "Conexão recusada (porta fechada): suba o runtime local de IA (ex.: Ollama). "
    "Com Docker Compose deste projeto, use LLM_API_BASE=http://ollama:11434/v1. "
    "Se estiver fora do Docker, confirme o endpoint local (ex.: http://127.0.0.1:11434/v1)."
)

HINT_MODEL_NOT_READY_PT = (
    "Runtime IA online, mas modelo indisponível: faça pull do modelo e tente novamente "
    "(ex.: ollama pull qwen2.5:0.5b)."
)


def hint_pt_for_llm_error(err: str | None) -> str | None:
    """Dica curta em PT quando o erro é típico de «nada a escutar na porta»."""
    if not err:
        return None
    el = err.lower()
    if (
        "111" in err
        or "10061" in err
        or "connection refused" in el
        or "recusou" in el
        or "failed to establish a new connection" in el
    ):
        return HINT_CONNECTION_REFUSED_PT
    return None


def agent_debug_ndjson(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    # #region agent log
    try:
        # Usar LOG_DIR (ex.: /app/logs no Docker com volume → ./logs no host), não a raiz do
        # container — caso contrário o NDJSON nunca aparece no workspace.
        os.makedirs(LOG_DIR, exist_ok=True)
        path = os.path.join(LOG_DIR, "debug-1aa2f1.log")
        line = {
            "sessionId": "1aa2f1",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError as e:
        try:
            sys.stderr.write(f"[pdf-service] debug_ndjson: não foi possível escrever em {LOG_DIR}: {e}\n")
        except OSError:
            pass
    # #endregion


UNIVERSAL_PROMPT = """Você é um especialista em análise de documentos e extração de dados meticulosa.
Analise o documento abaixo com extrema atenção aos detalhes e retorne APENAS um JSON válido.
O documento foi previamente classificado como o tipo: '{doc_type_label}'.

ESTRUTURA DO JSON ESPERADA:
{
  "document_purpose": "Explique de forma detalhada o propósito deste documento, para que serve e o seu contexto geral.",
  "document_type": "Classificação detalhada do tipo de documento (livre e específica).",
  "document_domain": "Domínio macro do documento (ex.: financeiro, jurídico, acadêmico, identificação, médico, educacional, avaliação, administrativo, técnico, outro).",
  "document_subtype": "Subtipo mais preciso possível (ex.: IRPF declaração anual, extrato de conta corrente, diploma de graduação, petição inicial, prova objetiva, etc.).",
  "detailed_summary": "Resumo completo em 4 a 6 frases englobando os pontos fundamentais, partes envolvidas e conclusões do documento.",
  "grouped_info": {
    "NOME_DA_CATEGORIA_DE_DADOS_1": {
      "Chave ou nome da informação extraída": "Valor exato extraído do documento com todas as especificidades"
    },
    "NOME_DA_CATEGORIA_DE_DADOS_2": {
      "Outro detalhe": "Outro valor"
    }
  },
  "key_findings": [
    "Fato extraordinário ou importante 1",
    "Fato 2"
  ],
  "recommendations": [
    "Observação, atenção ou recomendação baseada nos dados do documento 1"
  ]
}

REGRAS:
0. Trate a classificação recebida como hipótese inicial, não como verdade absoluta.
1. Agrupe as informações extraídas dentro de "grouped_info" de forma lógica usando categorias pertinentes ao tipo do documento (Ex: "Dados do Paciente", "Dados Financeiros", "Experiência Profissional", "Cláusulas do Contrato", "Valores e Taxas").
2. NÃO crie chaves genéricas se puder ser específico.
3. Extraia TODOS os detalhes importantes. Não seja superficial.
4. "document_purpose" é obrigatório: escreva 2-4 frases objetivas explicando a finalidade prática do documento.
5. "detailed_summary" deve ser complementar ao propósito, com contexto factual e evidências do conteúdo.
6. Se detectar sinais fortes de que o tipo real difere da classificação inicial, reflita isso em "document_type" (pode ser qualquer tipo válido de documento) e descreva no resumo.
7. Preencha "document_domain" e "document_subtype" com termos úteis para buscas e filtros futuros.
8. O resultado DEVE ser um JSON válido, sem formatações Markdown adicionais (sem ```json no começo ou fim).
"""


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if LLM_API_KEY:
        h["Authorization"] = f"Bearer {LLM_API_KEY}"
    return h


def _chat_url() -> str:
    base = LLM_API_BASE.rstrip("/")
    return f"{base}/chat/completions"


def _request_timeout():
    """(connect, read) — conexão curta; leitura até LLM_TIMEOUT na inferência."""
    return (max(3, LLM_CONNECT_TIMEOUT), max(30, LLM_TIMEOUT))


def _debug_ndjson_target() -> str:
    """Caminho absoluto onde a instrumentação NDJSON tenta gravar (útil com volumes Docker)."""
    return os.path.abspath(os.path.join(LOG_DIR, "debug-1aa2f1.log"))


def probe_llm_connectivity() -> dict:
    """
    GET {LLM_API_BASE}/models — diagnóstico leve (LM Studio / OpenAI-compatible).
    Não envia PDF; só verifica se o host responde e se o modelo configurado consta na lista.
    """
    base = LLM_API_BASE.rstrip("/")
    url = f"{base}/models"
    ct = max(3, min(LLM_CONNECT_TIMEOUT, 20))
    try:
        r = requests.get(url, headers=_headers(), timeout=(ct, ct + 5))
        reachable = r.status_code == 200
        out: dict = {
            "reachable": reachable,
            "http_status": r.status_code,
            "probe_url": url,
            "configured_model": LLM_MODEL,
        }
        if reachable:
            try:
                j = r.json()
                ids = [m.get("id") for m in (j.get("data") or []) if isinstance(m, dict)]
                out["models_count"] = len(ids)
                out["configured_model_listed"] = LLM_MODEL in ids if ids else None
                if ids and LLM_MODEL not in ids:
                    out["hint_pt"] = HINT_MODEL_NOT_READY_PT
            except (json.JSONDecodeError, ValueError, TypeError):
                out["configured_model_listed"] = None
        else:
            out["error"] = (r.text or "")[:200]
        out["debug_ndjson_target"] = _debug_ndjson_target()
        # #region agent log
        agent_debug_ndjson(
            "H0",
            "llm_client.py:probe_llm_connectivity",
            "probe_result",
            {
                "probe_url": url,
                "reachable": out.get("reachable"),
                "http_status": out.get("http_status"),
                "log_dir": LOG_DIR,
            },
        )
        # #endregion
        return out
    except requests.RequestException as e:
        err_s = str(e)[:240]
        # #region agent log
        agent_debug_ndjson(
            "H1",
            "llm_client.py:probe_llm_connectivity",
            "probe_exception",
            {"probe_url": url, "error_type": type(e).__name__, "err": err_s},
        )
        # #endregion
        out = {
            "reachable": False,
            "probe_url": url,
            "configured_model": LLM_MODEL,
            "error": err_s,
            "error_type": type(e).__name__,
        }
        hp = hint_pt_for_llm_error(err_s)
        if hp:
            out["hint_pt"] = hp
        out["debug_ndjson_target"] = _debug_ndjson_target()
        return out


def _raw_chat(prompt: str, max_tokens: int | None = None, use_json: bool = True) -> tuple[str, str]:
    """Retorna (texto_do_assistant, provedor_label)."""
    mt = max_tokens or LLM_MAX_TOKENS
    messages = [
        {
            "role": "system",
            "content": "Você é um assistente focado em extração estruturada. Responda estritamente em JSON quando o usuário pedir JSON.",
        },
        {"role": "user", "content": prompt},
    ]
    payload: dict = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": max(256, min(int(mt), 8192)),
    }
    if use_json and LLM_JSON_MODE:
        payload["response_format"] = {"type": "json_object"}

    url = _chat_url()
    to = _request_timeout()
    resp = requests.post(url, json=payload, headers=_headers(), timeout=to)
    if resp.status_code == 400 and "response_format" in json.dumps(payload):
        payload.pop("response_format", None)
        resp = requests.post(url, json=payload, headers=_headers(), timeout=to)
    resp.raise_for_status()
    data = resp.json()
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    text = str(content).strip()
    return text, f"openai_compatible ({LLM_MODEL})"


def _head_tail_excerpt(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    sep_len = 120
    mid = max_chars - sep_len - 400
    if mid < 2000:
        mid = max_chars - sep_len - 200
    tail = 380
    sep = (
        "\n\n--- [... trecho central omitido (limite de contexto); "
        "início e fim do documento preservados abaixo] ---\n\n"
    )
    return text[:mid] + sep + text[-tail:]


def _chunk_text(text: str, chunk_size: int, overlap: int, max_chunks: int) -> list[str]:
    chunks = []
    start = 0
    n = len(text)
    while start < n and len(chunks) < max_chunks:
        end = min(n, start + chunk_size)
        chunks.append(text[start:end])
        if end >= n:
            break
        start = max(0, end - overlap)
    return chunks


def _single_shot_llm(body: str, doc_type: str, strategy: str) -> tuple[dict | None, dict]:
    doc_label = DOCUMENT_TYPES.get(doc_type, doc_type)
    prompt = UNIVERSAL_PROMPT.replace("{doc_type_label}", doc_label) + "\nTexto do Documento:\n" + body

    logger.info(f"🤖 Preparando análise single_shot [{strategy}], len={len(body)}")
    llm_text, provider = _raw_chat(prompt, max_tokens=LLM_MAX_TOKENS, use_json=True)
    parsed = _extract_json(llm_text)
    meta = {
        "strategy": strategy,
        "provider": provider,
        "body_chars": len(body),
        "raw_response_chars": len(llm_text),
    }
    return parsed, meta


def _fragment_prompt(doc_type: str, chunk: str, idx: int, total: int) -> str:
    doc_label = DOCUMENT_TYPES.get(doc_type, doc_type)
    return f"""Trecho {idx}/{total} de um documento classificado como '{doc_label}'.
Extraia TODAS as informações concretas e completas deste trecho. Responda em JSON válido:
{{
  "detalhes_do_trecho": "Resumo do que contém este trecho em 2 frases",
  "informacoes_extraidas": {{"Categoria": {{"Campo": "Valor extraído"}}}}
}}
Texto do trecho:
{chunk}
"""


def _chunked_pipeline(full_text: str, doc_type: str) -> tuple[dict | None, dict]:
    chunks = _chunk_text(full_text, LLM_CHUNK_SIZE, LLM_CHUNK_OVERLAP, LLM_MAX_CHUNKS)
    digest_parts = []
    provider_used = "unknown"
    for i, ch in enumerate(chunks):
        try:
            frag, prov = _raw_chat(_fragment_prompt(doc_type, ch, i + 1, len(chunks)), max_tokens=1000, use_json=True)
            provider_used = prov
            part = _extract_json(frag)
            if part:
                digest_parts.append(json.dumps(part, ensure_ascii=False)[:3200])
        except Exception as e:
            logger.warning(f"⚠️ Fragmento {i + 1}/{len(chunks)} falhou: {e!s}")

    digest = "\n\n---\n\n".join(digest_parts)[:18000]
    if not digest.strip():
        return None, {"strategy": "chunked_failed", "chunks": len(chunks)}

    doc_label = DOCUMENT_TYPES.get(doc_type, doc_type)
    synth = UNIVERSAL_PROMPT.replace("{doc_type_label}", doc_label) + f"""
=== Leitura Multi-Trechos ===
O PDF original é longo. Abaixo estão as extrações preliminares de {len(chunks)} trechos.
Faça a síntese FINAL e completa unificando as informações desses trechos no JSON final pedido.

NOTAS POR TRECHO:
{digest}
"""
    logger.info(f"🤖 Sintetizando {len(chunks)} trechos...")
    llm_text, prov = _raw_chat(synth, max_tokens=LLM_MAX_TOKENS, use_json=True)
    parsed = _extract_json(llm_text)
    meta = {
        "strategy": "chunked_synthesis",
        "provider": prov,
        "chunks": len(chunks),
        "chunk_size": LLM_CHUNK_SIZE,
        "digest_chars": len(digest),
        "raw_response_chars": len(llm_text),
    }
    return parsed, meta


def call_llm(text: str, doc_type: str) -> tuple[dict | None, dict]:
    """
    Analisa o texto do PDF com o modelo local (API compatível com OpenAI).
    Mantém alias histórico em analyze: importação pode usar call_llm.
    """
    meta: dict = {"strategy": "none", "total_input_chars": len(text)}
    n = len(text)
    if n == 0:
        return None, meta

    approx_prompt_chars = 1500

    if n <= MAX_TEXT_CHARS:
        parsed, m = _single_shot_llm(text, doc_type, "full_document")
        meta.update(m)
        return parsed, meta

    head_tail_limit = int(MAX_TEXT_CHARS * LLM_HEAD_TAIL_FACTOR)
    if n <= head_tail_limit:
        body_budget = max(4000, MAX_TEXT_CHARS - min(1200, approx_prompt_chars))
        body = _head_tail_excerpt(text, body_budget)
        parsed, m = _single_shot_llm(body, doc_type, "head_tail")
        meta.update(m)
        meta["omitted_chars"] = max(0, n - len(body))
        return parsed, meta

    try:
        parsed, m = _chunked_pipeline(text, doc_type)
        meta.update(m)
        return parsed, meta
    except Exception as e:
        logger.error(f"❌ Pipeline em trechos falhou: {e}", exc_info=True)
        meta["error"] = str(e)[:200]
        return None, meta


def generate_missing_purpose(text: str, doc_type: str, current_summary: str = "") -> str | None:
    """
    Gera apenas o propósito do documento quando o campo vier vazio/inútil.
    Usa um prompt curto para reduzir custo/latência e melhorar consistência do card de propósito.
    """
    short_text = text[:7000]
    doc_label = DOCUMENT_TYPES.get(doc_type, doc_type)
    prompt = f"""Você irá preencher APENAS o campo 'document_purpose' em português.
Documento classificado como: {doc_label}.
Resumo atual (pode estar incompleto): {current_summary[:500]}

Escreva em 2 a 4 frases diretas:
- para que este documento existe;
- quem normalmente usa;
- qual decisão/ação ele suporta.

Responda SOMENTE JSON válido:
{{"document_purpose":"..."}}

Trecho do documento:
{short_text}
"""
    try:
        llm_text, _ = _raw_chat(prompt, max_tokens=260, use_json=True)
        parsed = _extract_json(llm_text) or {}
        dp = parsed.get("document_purpose")
        if isinstance(dp, str) and len(dp.strip()) >= 20:
            return dp.strip()
    except Exception as e:
        logger.warning(f"⚠️ Falha ao gerar purpose complementar: {e!s}")
    return None


def _extract_json(text: str) -> dict | None:
    try:
        out = json.loads(text)
        if isinstance(out, dict):
            return out
    except (json.JSONDecodeError, ValueError):
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            out = json.loads(match.group())
            if isinstance(out, dict):
                return out
        except (json.JSONDecodeError, ValueError):
            pass

    logger.warning("⚠️ Não foi possível extrair JSON limpo. Tentando remover tags markdown.")

    clean_text = text.replace("```json", "").replace("```", "").strip()
    try:
        out = json.loads(clean_text)
        if isinstance(out, dict):
            return out
    except Exception:
        pass

    logger.error("Falha absoluta na extração JSON.")
    return None
