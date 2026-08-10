# Local AI runtime

## Final architecture

Snowflake is the only durable database and file stage. It stores OWD sources, normalized workflow
records, users/RBAC, workflow state, conversations, audits, escalations, analytics, and retrieval
candidate text. It performs no AI, embedding, generation, extraction, summarization,
classification, or search-service work.

The production pipelines are:

```text
Admin UTF-8 OWD Markdown → deterministic parser → validator → AST compiler
→ transactional Snowflake loader → normalized tables → semantic-cache invalidation
```

```text
JWT role/department → published department-scoped Snowflake candidate pages
→ disposable in-memory Ollama embedding index → local grounded JSON answer
→ source-ID/claim/citation/confidence validation → response or extractive fallback → escalation
```

## Audit and root causes

| Capability | Previous implementation | Current replacement | Functional status | Required correction/result |
| --- | --- | --- | --- | --- |
| Semantic retrieval | Managed Snowflake search call, later per-request local re-embedding | `LocalSemanticIndex` plus scoped SQL fallback | Implemented; live quality not measured | Paged, bounded cache; rebuild from Snowflake; invalidate after publication |
| Embeddings | Managed embedding metadata/defaults; no honest runtime ingestion embeddings | Ollama `/api/embed`, `nomic-embed-text` configurable | Implemented; real model smoke pending | Batch and cache; never persist as a second database |
| Grounded generation | Managed completion call or unstructured local text | Ollama `/api/chat` structured JSON | Implemented; live quality pending | Exact retrieved `source_ids` required |
| Answer extraction | Not built | Ollama runtime method plus deterministic extractive fallback | Implemented provider capability | Not inserted into ingestion |
| Summarization | Original vision only | Ollama runtime method over authorized evidence | Implemented provider capability | No ingestion-time summary |
| Classification suggestions | Original vision only | Non-authoritative Ollama suggestion method | Implemented provider capability | Cannot set department/RBAC |
| Citation generation | Fabricated default IDs when metadata was absent | Citations only from complete retrieved metadata | Corrected | Missing IDs fail closed |
| Confidence | Retrieval score with fabricated default `0.8` | Measured retrieval score × measured answer/evidence support | Corrected | Missing score produces no confidence |
| Grounding | Any retrieved chunk meant `True` | Exact source mapping plus lexical claim-support check | Corrected baseline | Representative live evaluation still required |
| Department isolation | Query filters plus post-filter | Pre-query department predicate and post-ranking check | Preserved and tested | No role, including admin, bypasses evidence scope |
| Publication filtering | Configured status plus service filter | Configured SQL predicate plus post-ranking check | Preserved and tested | Production template is `published` |
| Safe fallback | Canonical no-evidence and extractive paths | Extractive verified evidence or canonical fallback | Implemented | Both preserve escalation |
| Escalation | Synchronous DB/webhook could suppress response | Side-effect isolation | Implemented | Monitor persistence failure separately |
| Health | Reachability only | Required/installed/missing models and per-model readiness | Implemented | Live container result pending |
| Docker | Hidden profile, wrong loopback URL, manual pulls | Ollama + idempotent model-init + health-aware backend | Corrected config | Requires Docker/network verification |
| Model installation | Manual and undocumented variants | Compose init plus Bash/PowerShell host/Compose scripts | Implemented | Model license approval remains required |
| Voice/TTS/translation/OCR/PDF/DOCX | Original vision only; no API contract | None | **Not built** | Do not add unused fake services |

The critical defects were vendor-specific gateway coupling, managed-service remnants, embedding a
bounded *prefix* of candidates on each request (which could omit a relevant later row), accepting
any generated text as grounded whenever a chunk existed, fabricating citation IDs and confidence,
and a Docker topology that did not start ready-to-use models.

## Provider responsibilities

`OllamaLocalAIProvider` is the only AI provider. It may call only a local/private URL. Public host
URLs are rejected before an HTTP request. It provides:

- batch embeddings;
- structured grounded generation;
- extractive question answering;
- authorized-evidence summarization;
- non-authoritative classification suggestions;
- installed-model health.

Model output is JSON with `answer` and exact `source_ids`. Evidence is labelled untrusted data in
the prompt so OWD content cannot override system instructions. No JWT, password, audit payload, or
unrelated conversation content is sent to Ollama.

## Semantic index lifecycle

The local index is process memory only. The cache key includes department, allowed statuses, and
embedding model. Rebuild reads Snowflake in `LOCAL_AI_CANDIDATE_LIMIT` pages until exhausted or
`LOCAL_AI_INDEX_MAX_CANDIDATES` is reached, embeds batches once, and stores Snowflake metadata plus
vectors in memory. A successful publication invalidates that department; its next query rebuilds
from Snowflake. Process restart or model/status change also causes a rebuild.

SQL lexical retrieval is always available if Ollama or the index fails. Its parameterized query
filters department and status before rows are returned and never returns arbitrary related rows.

## Grounding rules

A generated answer is accepted only when:

1. every candidate belongs to the authenticated department and an allowed status;
2. every cited source ID exists in the retrieved candidate set;
3. each cited row has real chunk/document/version/step/content/score metadata;
4. generated answer terms have material overlap with cited evidence;
5. confidence calculated from retrieval score and claim-support ratio meets the threshold.

Failure returns an exact verified extract with real citation metadata and escalation. If no complete
verified row exists, the canonical no-evidence response is returned with escalation.

## Configuration

```dotenv
LOCAL_AI_ENABLED=true
LOCAL_AI_BASE_URL=http://ollama:11434
LOCAL_CHAT_MODEL=qwen2.5:3b
LOCAL_EMBEDDING_MODEL=nomic-embed-text
LOCAL_AI_TIMEOUT_SECONDS=30
LOCAL_AI_CANDIDATE_LIMIT=100
LOCAL_AI_INDEX_MAX_CANDIDATES=5000
LOCAL_AI_MIN_SIMILARITY=0.35
COPILOT_RETRIEVAL_LIMIT=5
COPILOT_ALLOWED_KNOWLEDGE_STATUSES=published
```

Model names are configurable. Review exact model cards, licenses, revisions, sources, and
quantizations before production use.

## Docker and model installation

```bash
cp backend/.env.example backend/.env
# Fill only local backend/.env with Snowflake/JWT secrets.
docker compose up --build
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/health/ai
curl --fail http://localhost:11434/api/tags
```

Compose starts Ollama without a profile, waits for it to become healthy, pulls both models into the
persistent `ollama_data` volume, then starts the backend. Host and explicit Compose setup are also
available:

```bash
scripts/setup_local_ai.sh host
scripts/setup_local_ai.sh compose
```

Windows PowerShell:

```powershell
.\scripts\setup_local_ai.ps1 -Mode Host
.\scripts\setup_local_ai.ps1 -Mode Compose
```

## Hardware expectations

The default 3B quantized chat model is intended for CPU-capable development machines. Start with at
least 8 GB system RAM and several GB of free model storage; a GPU is optional. Actual memory,
latency, throughput, and disk use depend on the exact model revision and Ollama packaging and must
be benchmarked on the deployment host. Increase or change models only after representative OWD
retrieval and grounding evaluation.

## Fallback and operations

If Ollama is unreachable, semantic retrieval falls back to scoped SQL and generation falls back to
an exact verified extract. `/health/ai` becomes degraded and reports required, installed, and
missing models without secrets. The backend remains operational provided Snowflake is reachable.

The index is not shared across backend replicas. Each replica rebuilds its own disposable cache.
For large departments or many replicas, measure rebuild load and configure a safe candidate cap;
do not add a durable vector database.

## Testing and live verification

Default tests are hermetic and block unmocked Snowflake connections. Live tests require the
`live_integration` marker and `WORKMATE_RUN_LIVE_TESTS=1`.

Functional parity is **not claimed** from unit tests. Before production, measure retrieval quality,
grounding, latency, outage behavior, and department isolation with representative WorkMate OWDs.
Live Snowflake validation must follow `snowflake_runtime_runbook.md` and must be reported as not run
when credentials are unavailable.

## Deliberately unbuilt features

Voice, TTS, translation, PDF/DOCX/OCR, arbitrary-document ingestion, and ingestion-time AI have no
current API-to-runtime contract. They remain unbuilt rather than being represented by unused
libraries or fake methods.

## Remaining environment/dependency limitations

Live Snowflake verification requires owner credentials and cannot be replaced by mocks. Real Ollama
quality/latency verification requires Docker or a host Ollama installation plus model downloads.
The requested Next.js security upgrade could not be selected or installed in the current execution
environment because both official web lookup and the npm registry returned authorization/403
errors; the existing lockfile was left internally consistent rather than guessing a version or
committing an unverified lockfile. This upgrade remains a release blocker.
