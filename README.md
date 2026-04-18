# PDF AI Service

Motor de análise de PDFs com **classificação automática**, **extração de texto (PyMuPDF)** e **LLM local leve** (recomendado: **Qwen 2.5 0.5B**) via **API compatível com OpenAI**. O padrão do projeto é **Ollama em Docker**. O resultado detalhado é exibido na página **Relatório** do frontend.

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0-green?logo=flask&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker&logoColor=white)
![LLM](https://img.shields.io/badge/LLM-OpenAI--compatible%20local-purple)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## O que faz?

1. Recebe o PDF em `POST /analyze`
2. Extrai texto e metadados com **PyMuPDF**
3. Classifica o tipo (currículo, NF, contrato, etc.) por heurística
4. Envia o texto ao **servidor LLM local** (chat completions) com prompt que pede **JSON** (propósito, resumo, `grouped_info`, achados, recomendações)
5. Mescla com **fallback** baseado em regex quando a IA não responde ou o JSON não fecha
6. O front grava a resposta em `sessionStorage` e abre **`analise.html`** com o relatório rico (accordions por categoria, achados, recomendações)

---

## Arquitetura (resumo)

```
PDF → POST /analyze → PyMuPDF → Classificador → LLM local (HTTP /v1/chat/completions) → merge fallback → JSON
                                                                                              ↓
                                                                              index.html → sessionStorage → analise.html
```

---

## Stack

| Camada | Tecnologia |
|--------|------------|
| API | Python 3.11, Flask, Gunicorn |
| PDF | PyMuPDF (fitz) |
| IA | Modelo local via **OpenAI-compatible** (`LLM_API_BASE` + `LLM_MODEL`) — padrão: Ollama + `qwen2.5:0.5b` |
| Front | HTML/CSS/JS (páginas `index.html`, `analise.html`, …) |
| Deploy | Docker Compose |

---

## Estrutura do repositório

```
pdf-service/
├── backend/
│   ├── config.py
│   ├── routes/analyze.py
│   └── services/
│       ├── pdf_extractor.py
│       ├── classifier.py
│       ├── llm_client.py       # cliente HTTP OpenAI-compatible
│       └── llm_normalize.py
├── frontend/
│   ├── index.html              # upload
│   ├── analise.html            # relatório pós-análise
│   ├── arquitetura.html
│   ├── stacks.html
│   └── assets/ (css, js)
├── logs/                     # logs da app (Git: só `.gitkeep`; resto ignorado via `/logs/*` + `!/logs/.gitkeep`)
├── app.py
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── requirements.txt
```

---

## Pré-requisitos

- Python 3.11+ **ou** Docker
- Um **servidor local** com API **POST** `{LLM_API_BASE}/chat/completions` no formato OpenAI, carregando um modelo **Qwen** pequeno (ex.: **Qwen2.5-0.5B-Instruct**).

### Exemplo recomendado: Ollama

1. Instale [Ollama](https://ollama.com/).
2. Faça pull do modelo leve: `ollama pull qwen2.5:0.5b`.
3. A API local fica em `http://127.0.0.1:11434/v1` com `LLM_MODEL=qwen2.5:0.5b`.

### Exemplo alternativo: LM Studio

1. Instale [LM Studio](https://lmstudio.ai), baixe um Qwen leve (GGUF).
2. Carregue o modelo e inicie o servidor local na porta **1234**.
3. Base da API: `http://127.0.0.1:1234/v1`.

### Exemplo: llama.cpp server

Suba o binário `llama-server` com o GGUF do Qwen e use a URL `/v1` indicada na documentação do projeto (tipicamente `http://127.0.0.1:8080/v1`).

---

## Configuração (.env)

Copie `.env.example` para `.env` e ajuste:

| Variável | Descrição |
|----------|-----------|
| `LLM_API_BASE` | URL base com `/v1` (ex.: `http://127.0.0.1:11434/v1`) |
| `LLM_MODEL` | Nome do modelo no servidor |
| `LLM_API_KEY` | Opcional (Bearer) |
| `LLM_TIMEOUT` | Timeout de leitura da resposta HTTP (s) |
| `LLM_CONNECT_TIMEOUT` | Timeout de conexão TCP ao host do LLM (s) |
| `LLM_MAX_TOKENS` | Limite de tokens na resposta |
| `LLM_JSON_MODE` | `1` tenta `response_format: json_object`; `0` desliga se o host não suportar |
| `MAX_TEXT_CHARS`, `LLM_CHUNK_*` | Controle de tamanho e pipeline multi-trecho |
| `LOG_DIR` | Pasta dos ficheiros de log (predef.: `logs/` no repo). **Relativo = sempre à raiz do projeto** (não ao `cwd`). Se for `.` ou a própria raiz do repo, usa-se `logs/` para não criar `.log` na raiz |
| `LOG_TO_FILE` | `1` grava em ficheiro com rotação + consola; `0` só consola |
| `LOG_FILE_NAME`, `LOG_FILE_MAX_BYTES`, `LOG_FILE_BACKUP_COUNT` | Nome do ficheiro em `LOG_DIR` (só **basename**; `../` é descartado), rotação |

**Docker:** em `docker-compose.yml` o padrão é `LLM_API_BASE=http://ollama:11434/v1`, com serviço Ollama interno e pull automático do modelo. Os logs são gravados em **`./logs`** no host (volume montado em `/app/logs`).

---

## Rodar localmente

```bash
pip install -r requirements.txt
cp .env.example .env
# suba o LM Studio (ou outro) com o modelo Qwen antes de:
python app.py
```

Abra `http://localhost:8080` — faça upload na **Início**; ao terminar, o fluxo redireciona para **Relatório**.

---

## Docker

```bash
docker compose up -d --build
```

Este comando sobe:
- `pdf-service`
- `ollama`
- `ollama-pull` (faz `ollama pull qwen2.5:0.5b` na primeira inicialização)

Observação: a porta do Ollama **não é publicada no host** por padrão para evitar conflito (ex.: `11434` já ocupada). O `pdf-service` comunica com ele pela rede interna Docker em `http://ollama:11434/v1`.

Verificações rápidas:

```bash
curl http://localhost:8080/health
curl http://localhost:8080/health/llm
```

Se `reachable=false` no `/health/llm`, confirme se o modelo foi baixado:

```bash
docker compose logs ollama-pull
docker compose exec ollama ollama list
```

---

## API

### `GET /health`

Retorna `status`, `service`, `version`.

### `GET /health/llm`

Testa `GET {LLM_API_BASE}/models` (rápido). Resposta JSON com `reachable`, `configured_model`, `probe_url`, etc. A UI usa isto para avisar se o LLM está inacessível.

### `POST /analyze`

`multipart/form-data` com campo `file` (PDF).

Resposta inclui `analysis_method` (`ai` ou `fallback_intelligent`), `extracted_data`, `llm_coverage` (estratégia, provedor, erros resumidos).

**Só cai em fallback:** runtime de IA parado, modelo não baixado, URL errada, ou `LLM_MODEL` diferente do id em `/models`. Corrija e reenvie o PDF.

Notas de qualidade da análise:
- O backend tenta preencher `document_purpose` com uma chamada complementar de IA quando esse campo vier vazio.
- A classificação foi reforçada para documentos tributários/fiscais (ex.: IRPF, declaração de ajuste anual, DARF), reduzindo confusão com extrato bancário.

---

## Testes

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

---

## Autor

**Marvin Costa** — [LinkedIn](https://linkedin.com/in/marvincost) · [GitHub](https://github.com/marvincoast)

Licença: **MIT**.
