# Cortex exit strategy: Snowflake as database only

## Decision and immediate operating mode

Snowflake remains WorkMate AI's only durable system of record: relational data, OWD source files,
workflow state, conversations, audits, and analytics stay there. Snowflake Cortex is no longer
required by default. Cortex adapters remain temporarily for compatibility while replacements are
evaluated.

```dotenv
CORTEX_SEARCH_ENABLED=false
CORTEX_COMPLETE_ENABLED=false
```

This mode works now without another AI service. Retrieval uses the existing published,
department-scoped lexical SQL path; answer generation uses the grounded extractive response; the
validation and canonical fallback gates remain mandatory.

"Free" below means no per-request vendor charge and software that can be self-hosted. Hardware,
operations, storage, and security are not free. Library and model-weight licenses are separate:
legal/security must approve the exact version, model card, weight source, and intended commercial
use before production deployment.

## Cortex capability-by-capability replacement

| Cortex capability | Current status | No-AI/default replacement | Optional self-hosted enhancement |
| --- | --- | --- | --- |
| Cortex Search / `SEARCH_PREVIEW` | Implemented but opt-in | Existing scoped Snowflake SQL lexical retrieval | `sentence-transformers` embeddings and a disposable FAISS CPU index rebuilt from Snowflake |
| Cortex `AI_COMPLETE` | Implemented but opt-in | Existing grounded extractive response | Ollama or llama.cpp with an owner-approved instruction model |
| Cortex Embed | Not called by runtime | No embeddings | `sentence-transformers` with an approved small embedding model |
| Cortex Summarize | Not implemented | Deterministic compiler metadata | The same local instruction model with a grounded summarization prompt |
| Cortex Extract Answer | Not implemented | Highest-ranked verified OWD excerpt | Local extractive-QA model or local instruction model |
| Document AI / OCR | Not implemented | Strict OWD Markdown remains required | Docling conversion plus Tesseract for scanned pages |
| AI categorization / department tagging | Not implemented | Admin selection and OWD metadata | Local classifier as a suggestion only, never an authorization decision |
| Translation | Not implemented | No automatic translation | Argos Translate or license-approved MarianMT weights |
| Speech-to-text | Not implemented | Text input | faster-whisper with locally stored, approved weights |
| Text-to-speech | Not implemented | Text output | A locally hosted Piper-compatible voice after license review |

Snowflake Stage is storage, not an AI service. The SQL lexical fallback is database querying, not
Cortex. The deterministic parser/compiler, RBAC, workflow state, citations, confidence gate, audit,
and escalation logic need no AI replacement.

## Recommended tiers

### Tier 0 — deploy now with no AI process

1. Fetch only published `workflow_search_metadata` rows for the JWT's exact department.
2. Rank lexical matches in Snowflake SQL.
3. Return the best verified OWD excerpt with document/version/step citations.
4. Return the canonical no-evidence fallback when no verified row matches.

This requires no model server, GPU, vector database, managed-AI permission, or new data store. The
trade-off is weaker synonym and natural-language matching.

### Tier 1 — local semantic retrieval, no generative model

- Use `sentence-transformers` locally. Evaluate a small all-MiniLM- or BGE-small-class embedding
  model only after approving its exact model-card license.
- Use FAISS CPU as an in-memory, disposable index—not as an authoritative database.
- Rebuild the index on startup and publication events from published Snowflake rows. Store only
  Snowflake IDs plus department/status metadata beside vectors.
- Enforce department and lifecycle filters before ranking and again after ranking.
- Keep SQL retrieval available whenever the local index is missing, stale, or unhealthy.

Do not add Qdrant, Pinecone, Weaviate, Chroma persistence, PostgreSQL, or another durable vector
store under this decision. A local derived index must be deletable and rebuildable from Snowflake.

### Tier 2 — local grounded generation

- **Ollama:** simplest local developer/server operation.
- **llama.cpp server:** small dependency surface, CPU/GPU quantization support, and a local
  OpenAI-compatible HTTP endpoint.
- **vLLM:** consider only with dedicated GPU capacity and concurrency requirements.

The serving engine and model weights are separate choices. Evaluate a small instruction model with
a commercially acceptable license and sufficient context. A Qwen2.5-7B-Instruct-class model is a
reasonable candidate for evaluation, but do not hard-code it before verifying its exact model
card, license, source, quantization, memory, latency, and safety behavior.

Only already-authorized chunks may be sent to generation. Generated text still passes grounding,
RBAC, citation, confidence, and fallback validation. If local inference fails, return the extractive
answer—not an external cloud request.

### Tier 3 — local document conversion and OCR (separate scope)

If general PDF/DOCX/scanned ingestion is approved:

1. Convert locally with Docling; use Tesseract only on pages that require OCR.
2. Normalize output into an intermediate schema.
3. Require admin confirmation of department, title, version, and publication status.
4. Convert operational procedures into validated OWD rather than bypassing the compiler.
5. Store raw files and authoritative normalized data in Snowflake.
6. Add malware scanning, parser isolation, limits, and prompt-injection controls.

This is not a drop-in Cortex replacement and must not be mixed into the current `.md` endpoint
without its own product and security design.

## Provider boundary to build

Do not replace one hard-coded vendor with another. Introduce internal interfaces:

```python
class RetrievalProvider:
    async def search(self, query: str, department_id: str, limit: int) -> list[dict]: ...

class GenerationProvider:
    async def generate(self, query: str, authorized_chunks: list[dict]) -> str: ...
```

Implementations should be:

- `SqlLexicalRetrievalProvider` — mandatory baseline.
- `LocalEmbeddingRetrievalProvider` — optional sentence-transformers/FAISS enhancement.
- `ExtractiveGenerationProvider` — mandatory baseline.
- `LocalLlmGenerationProvider` — optional Ollama/llama.cpp enhancement.
- Cortex providers — compatibility-only until live parity and rollback tests pass.

Proposed settings:

```dotenv
RETRIEVAL_PROVIDER=sql
GENERATION_PROVIDER=extractive
LOCAL_LLM_BASE_URL=http://127.0.0.1:11434
LOCAL_LLM_MODEL=owner-approved-model
LOCAL_EMBEDDING_MODEL=owner-approved-model
```

Never silently fall from a local provider to an external API. The only automatic fallback is to
SQL retrieval and extractive generation.

## Security and operations

1. Snowflake stays authoritative; local indexes are derived and disposable.
2. Filter department/status before and after retrieval.
3. Never send JWTs, passwords, raw audit logs, or unrelated history to a model.
4. Bind local model servers to loopback/private networking; authenticate cross-host calls.
5. Pin dependency versions, model revision hashes, and quantization hashes.
6. Audit provider/model/version without logging sensitive prompts.
7. Preserve canonical fallback through retrieval, inference, escalation, and analytics failures.
8. Benchmark memory, latency, concurrency, and rebuild time with representative OWD data.
9. Test prompt injection, unsafe procedures, citation correctness, and department leakage.

## Migration sequence and acceptance

1. Deploy now with both Cortex flags false; run same- and cross-department tests.
2. Extract current SQL/extractive behavior behind provider interfaces without changing results.
3. Add local embeddings as opt-in and measure recall against SQL.
4. Add local generation as opt-in and retain extractive fallback.
5. Add conversion/OCR only as a separately approved project.
6. Remove Cortex migrations, grants, settings, and code only after local providers pass live parity,
   security, rollback, and operational acceptance.

Acceptance requires valid OWD ingestion with no Cortex privileges, verified same-department
citations, zero cross-department leakage, operation when every local AI process is stopped, no
external managed-AI data transfer, and deterministic rebuilding of every local index from
Snowflake.

## Implemented local provider

The active Copilot path now attempts an Ollama provider before any compatibility Cortex path:

- `nomic-embed-text` embeds the query and a bounded set of already department-scoped, published
  Snowflake candidates.
- Cosine ranking runs inside FastAPI without a vector database or numeric-library dependency.
- `qwen2.5:3b` is the initial configurable chat model; the response is still validated and cited
  from the authorized source set.
- Ollama failure falls through to optional Cortex only when explicitly enabled, then to mandatory
  scoped SQL/extractive behavior.
- `/health/ai` reports provider reachability and locally installed model names.

The model names are configuration defaults, not a permanent license approval. Replace them with
organization-approved model revisions when required. Document conversion/OCR, translation, STT,
and TTS remain recommendations because the product currently has no corresponding upload/audio
API contracts; adding unused libraries would not make those user features work.
