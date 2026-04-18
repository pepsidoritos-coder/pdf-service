"""
Configurações centralizadas do PDF Service.
Todas as variáveis de ambiente são carregadas aqui.
"""
import logging
import logging.handlers
import os
import sys

# Raiz do repositório (pasta que contém `backend/`)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# === LLM local (API compatível com OpenAI — Ollama, LM Studio, llama.cpp server, etc.) ===
# Ex.: Ollama local: http://127.0.0.1:11434/v1 | LM Studio: http://127.0.0.1:1234/v1
LLM_API_BASE = os.getenv("LLM_API_BASE", "http://127.0.0.1:11434/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:0.5b")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "600"))
# Timeout só da fase de conexão TCP (evita esperar minutos quando o host está offline)
LLM_CONNECT_TIMEOUT = int(os.getenv("LLM_CONNECT_TIMEOUT", "12"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4000"))
# Alguns backends locais não suportam response_format json_object; use LLM_JSON_MODE=0
LLM_JSON_MODE = os.getenv("LLM_JSON_MODE", "1").strip().lower() in ("1", "true", "yes")

# === Limites ===
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_MB", 15)) * 1024 * 1024
MAX_TEXT_CHARS = int(os.getenv("MAX_TEXT_CHARS", "22000"))
LLM_CHUNK_SIZE = int(os.getenv("LLM_CHUNK_SIZE", "9000"))
LLM_CHUNK_OVERLAP = int(os.getenv("LLM_CHUNK_OVERLAP", "350"))
LLM_MAX_CHUNKS = int(os.getenv("LLM_MAX_CHUNKS", "8"))
LLM_HEAD_TAIL_FACTOR = float(os.getenv("LLM_HEAD_TAIL_FACTOR", "2.25"))

# === Tipos de documentos suportados ===
DOCUMENT_TYPES = {
    "resume": "Currículo/Resume",
    "medical_prescription": "Receita Médica",
    "medical_report": "Prontuário/Laudo Médico",
    "bank_statement": "Extrato Bancário",
    "tax_document": "Documento Tributário/Fiscal",
    "invoice": "Nota Fiscal/Fatura",
    "contract": "Contrato",
    "educational_certificate": "Certificado/Diploma",
    "legal_document": "Documento Jurídico",
    "technical_report": "Relatório Técnico",
    "qa_assessment": "Perguntas e Respostas/Prova",
    "identity_document": "Documento de Identidade",
    "other": "Outro/Genérico",
}

# === Logging (ficheiros em logs/ — pasta dedicada; nunca na raiz por engano) ===
def _resolve_log_dir() -> str:
    """
    LOG_DIR vazio → <repo>/logs.
    Caminho absoluto → usado tal como (exceto se for a própria raiz do repo — ver abaixo).
    Caminho relativo → sempre relativo à raiz do repositório, não ao cwd do processo.
    Se o diretório resolvido for a raiz do repo (ex.: LOG_DIR=. ou caminho absoluto = raiz),
    usa <repo>/logs para nunca criar pdf-service.log na raiz do projeto.
    """
    root = os.path.abspath(_PROJECT_ROOT)
    raw = os.getenv("LOG_DIR", "").strip()
    if not raw:
        candidate = os.path.join(root, "logs")
    else:
        expanded = os.path.expanduser(raw)
        if os.path.isabs(expanded):
            candidate = os.path.abspath(expanded)
        else:
            candidate = os.path.abspath(os.path.join(root, expanded))
    if os.path.abspath(candidate) == root:
        candidate = os.path.join(root, "logs")
    return os.path.abspath(candidate)


LOG_DIR = _resolve_log_dir()
LOG_TO_FILE = os.getenv("LOG_TO_FILE", "1").strip().lower() in ("1", "true", "yes")
# Só o nome do ficheiro — ignora `../` para nunca escrever fora de LOG_DIR por engano
_LOG_FILE_RAW = os.getenv("LOG_FILE_NAME", "pdf-service.log").strip() or "pdf-service.log"
LOG_FILE_BASENAME = os.path.basename(_LOG_FILE_RAW.replace("\\", "/")) or "pdf-service.log"
# Nome efectivo no disco (só basename); mantém o nome `LOG_FILE_NAME` para imports antigos
LOG_FILE_NAME = LOG_FILE_BASENAME
LOG_FILE_MAX_BYTES = int(os.getenv("LOG_FILE_MAX_BYTES", str(5 * 1024 * 1024)))
LOG_FILE_BACKUP_COUNT = int(os.getenv("LOG_FILE_BACKUP_COUNT", "5"))

_LOG_FORMAT = '{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"pdf-service","message":"%(message)s"}'


def _configure_logger() -> logging.Logger:
    log = logging.getLogger("pdf-service")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    fmt = logging.Formatter(_LOG_FORMAT)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    log.addHandler(sh)

    if LOG_TO_FILE:
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            path = os.path.join(LOG_DIR, LOG_FILE_BASENAME)
            fh = logging.handlers.RotatingFileHandler(
                path,
                maxBytes=max(LOG_FILE_MAX_BYTES, 100_000),
                backupCount=max(LOG_FILE_BACKUP_COUNT, 1),
                encoding="utf-8",
            )
            fh.setFormatter(fmt)
            log.addHandler(fh)
        except OSError as e:
            sys.stderr.write(f"[pdf-service] Aviso: não foi possível escrever logs em {LOG_DIR}: {e}\n")

    log.propagate = False
    return log


logger = _configure_logger()
