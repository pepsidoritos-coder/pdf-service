# API — PDF AI Service

Base URL: `http://localhost:8080`

---

## `GET /health`

Health check do serviço.

**Response** `200 OK`:
```json
{
  "status": "healthy",
  "service": "pdf-service",
  "version": "6.0-local-llm"
}
```

---

## `GET /health/llm`

Verifica conectividade com o servidor OpenAI-compatible (`LLM_API_BASE`) via `GET …/models` (rápido, sem inferência).

**Response** `200 OK` (sempre): corpo JSON com `reachable`, `probe_url`, `configured_model` e, quando aplicável, `configured_model_listed`, `http_status` ou `error`.

---

## `POST /analyze`

Analisa um documento PDF.

### Request

- **Content-Type:** `multipart/form-data`
- **Body:** campo `file` com o arquivo PDF

```bash
curl -X POST http://localhost:8080/analyze \
  -F "file=@documento.pdf"
```

### Response `200 OK`

```json
{
  "filename": "documento.pdf",
  "document_type": "resume",
  "document_type_label": "Currículo/Resume",
  "confidence": 85,
  "text_length": 3200,
  "pages": 2,
  "pdf_metadata": {
    "title": "Currículo - João Silva",
    "author": "João Silva"
  },
  "processing_time_sec": 12.5,
  "analysis_method": "ai",
  "classification_scores": {
    "resume": 8,
    "technical_report": 2
  },
  "extracted_data": {
    "detailed_summary": "Resumo detalhado do documento...",
    "key_findings": ["achado 1", "achado 2"],
    "recommendations": ["sugestão 1"],
    "...campos_específicos_do_tipo": "..."
  }
}
```

### Errors

| Code | Body | Causa |
|---|---|---|
| `400` | `{"error": "Nenhum arquivo enviado"}` | Sem campo `file` |
| `400` | `{"error": "Apenas PDFs válidos"}` | Arquivo não é PDF |
| `400` | `{"error": "PDF vazio ou não legível"}` | PDF sem texto extraível |
| `413` | — | Arquivo maior que 15MB |
| `500` | `{"error": "Erro interno ao processar"}` | Erro não tratado |

### Campos de `extracted_data` por Tipo

**resume**: `personal_info`, `skills`, `experience`, `education`, `languages`, `certifications`

**medical_prescription**: `patient_name`, `doctor_info`, `medications`, `diagnosis`

**bank_statement**: `account_holder`, `bank_name`, `balance`, `major_transactions`

**invoice**: `issuer`, `recipient`, `invoice_number`, `items`, `total_value`, `taxes`

**educational_certificate**: `student_name`, `institution`, `course`, `workload`

**contract**: `contract_type`, `parties`, `object`, `value`, `key_clauses`

**legal_document**: `document_type`, `case_number`, `court`, `parties`, `decision`

**technical_report**: `title`, `authors`, `objective`, `methodology`, `main_results`, `conclusions`
