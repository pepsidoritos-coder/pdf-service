# Arquitetura — PDF AI Service

## Visão Geral

O PDF AI Service segue uma arquitetura em pipeline com 5 estágios:

```
Upload → Extração → Classificação → IA → Fallback → Resposta
```

## Componentes

### 1. Ingestão (PyMuPDF)
- **Arquivo:** `backend/services/pdf_extractor.py`
- Lê bytes do PDF via `fitz.open(stream=...)`
- Extrai texto **por página** com contagem de caracteres
- Coleta **metadados** do PDF (título, autor, datas)

### 2. Classificador
- **Arquivo:** `backend/services/classifier.py`
- Scoring por keywords para 10 tipos de documento
- 13+ keywords por tipo com score de confiança
- Retorna `doc_type`, `label`, `confidence`, `scores`

### 3. Motor cognitivo (LLM local)
- **Arquivo:** `backend/services/llm_client.py` — HTTP `POST /v1/chat/completions` (OpenAI-compatible)
- Modelo recomendado: **Qwen2.5-0.5B-Instruct** (ou equivalente leve) no LM Studio / llama.cpp server
- Prompt pede JSON com `document_purpose`, `detailed_summary`, `grouped_info`, `key_findings`, `recommendations`
- Configuração via `LLM_MAX_TOKENS`, `LLM_TIMEOUT`, `LLM_JSON_MODE`, `temperature=0.1`
- Extrai JSON da resposta (markdown ou texto extra é tolerado)

### 4. Fallback Inteligente
- **Arquivo:** `backend/utils/fallback_parser.py`
- 10 handlers especializados (um por tipo de documento)
- Extrai: emails, telefones, CPFs, CNPJs, datas, URLs, valores monetários
- Sempre executa para **complementar** a IA

### 5. API (Flask)
- **Arquivo:** `backend/routes/analyze.py`
- Blueprint com `/health` e `/analyze`
- Merge: IA tem prioridade, fallback complementa
- Retorna: metadados do PDF + classificação + dados extraídos

## App Factory
- **Arquivo:** `backend/__init__.py`
- Cria instância Flask com CORS
- Registra blueprints
- Entry point: `app.py` (15 linhas)

## Configuração
- **Arquivo:** `backend/config.py`
- Todas as variáveis via `os.getenv()` com defaults
- Logging estruturado em JSON
