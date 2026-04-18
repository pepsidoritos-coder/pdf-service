# Deploy — PDF AI Service

## Opção 1: Docker (recomendado)

### Pré-requisitos

- Docker e Docker Compose
- No **host**, um servidor LLM com API **OpenAI-compatible** (ex.: LM Studio na porta 1234 com Qwen2.5-0.5B)

### Deploy

```bash
git clone https://github.com/marvincoast/pdf-service.git
cd pdf-service
docker compose up -d --build
curl http://localhost:8080/health
```

### Variáveis de ambiente

Use `docker-compose.yml` ou um ficheiro `.env` passado ao Compose. Principais:

```env
LLM_API_BASE=http://host.docker.internal:1234/v1
LLM_MODEL=qwen2.5-0.5b-instruct
LLM_TIMEOUT=600
LLM_JSON_MODE=1
MAX_FILE_SIZE_MB=15
```

---

## Opção 2: Local (desenvolvimento)

```bash
pip install -r requirements.txt
cp .env.example .env
# Inicie LM Studio (ou llama.cpp server) com o modelo antes de:
python app.py
```

---

## Opção 3: Gunicorn (produção)

```bash
pip install -r requirements.txt
gunicorn --bind 0.0.0.0:8080 --workers 2 --threads 2 --timeout 600 app:app
```

---

## Rede Docker ↔ host

O Compose define `extra_hosts: host.docker.internal:host-gateway` e `LLM_API_BASE` apontando para o host, para o container alcançar o LM Studio (ou outro) na máquina física.
