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
JWT role/department → bounded conversation resolver → deterministic active-workflow authority
→ published department-scoped Snowflake evidence → evidence-bounded reasoner or local Ollama synthesis
→ source-ID/claim/citation/confidence validation → grounded response or canonical fallback → escalation
```

The Copilot is a grounded operational agent, not an open-ended chatbot. Persisted workflow state
owns step order, completion, and decision transitions. Conversation history supplies context only;
it is never accepted as organizational evidence. Deterministic reasoning handles current-step
explanations, matching exceptions, future-step deferral, typo-tolerant workflow navigation, and
unambiguous natural-language decision selection before model synthesis is considered.

## Audit and root causes

| Capability | Previous implementation | Current replacement | Functional status | Required correction/result |
| --- | --- | --- | --- | --- |
| Semantic retrieval | Managed Snowflake search call, later per-request local re-embedding | Cached typo-aware matching, `LocalSemanticIndex`, and scoped SQL fallback | Implemented and live-evaluated | Paged, bounded cache; rebuild from Snowflake; invalidate after publication |
| Embeddings | Managed embedding metadata/defaults; no honest runtime ingestion embeddings | Ollama `/api/embed`, `nomic-embed-text` configurable | Implemented; real model smoke pending | Batch and cache; never persist as a second database |
| Grounded generation | Managed completion call or unstructured local text | Evidence-bounded agent prompt plus Ollama `/api/chat` structured JSON | Implemented and contract-tested | Exact retrieved `source_ids` required; model has no workflow authority |
| Answer extraction | Not built | Ollama runtime method plus deterministic extractive fallback | Implemented provider capability | Not inserted into ingestion |
| Summarization | Original vision only | Ollama runtime method over authorized evidence | Implemented provider capability | No ingestion-time summary |
| Classification suggestions | Original vision only | Non-authoritative Ollama suggestion method | Implemented provider capability | Cannot set department/RBAC |
| Citation generation | Fabricated default IDs when metadata was absent | Citations only from complete retrieved metadata | Corrected | Missing IDs fail closed |
| Confidence | Retrieval score with fabricated default `0.8` | Measured retrieval score × measured answer/evidence support | Corrected | Missing score produces no confidence |
| Grounding | Any retrieved chunk meant `True` | Exact source mapping plus lexical claim-support check | Corrected and live-evaluated | Current-state rules, contextual follow-ups, typo paths, and unrelated queries verified |
| Department isolation | Query filters plus post-filter | Pre-query department predicate and post-ranking check | Preserved and tested | No role, including admin, bypasses evidence scope |
| Publication filtering | Configured status plus service filter | Configured SQL predicate plus post-ranking check | Preserved and tested | Production template is `published` |
| Safe fallback | Canonical no-evidence and extractive paths | Extractive verified evidence or canonical fallback | Implemented | Both preserve escalation |
| Escalation | Synchronous DB/webhook could suppress response | Side-effect isolation | Implemented | Monitor persistence failure separately |
| Health | Reachability only | Required/installed/missing models and per-model readiness | Implemented | Live container result pending |
| Docker | Hidden profile, wrong loopback URL, manual pulls | Ollama + idempotent model-init + health-aware backend | Corrected config | Requires Docker/network verification |
| Model installation | Manual and undocumented variants | Compose init plus Bash/PowerShell host/Compose scripts | Implemented | Model license approval remains required |
| Voice input/output | Original vision only | Browser Web Speech recognition and synthesis | Implemented in the Copilot UI | Browser capability and microphone permission required |
| Translation/OCR/PDF/DOCX | Original vision only; no API contract | None | **Not built** | Do not add unused fake services |

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

The grounded agent prompt requires every operational claim to be entailed by verified evidence. It
may explain explicit rules and connect them to the active step, but it may not invent commands,
values, thresholds, locations, tools, people, steps, policies, or transitions. It must not expose
hidden reasoning. If evidence does not answer the question, it states that the missing detail is
not present and the validation gate decides whether to return the canonical escalation response.

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
LOCAL_AI_TIMEOUT_SECONDS=8
LOCAL_AI_CANDIDATE_LIMIT=100
LOCAL_AI_INDEX_MAX_CANDIDATES=5000
LOCAL_AI_MIN_SIMILARITY=0.35
COPILOT_RETRIEVAL_LIMIT=5
COPILOT_HISTORY_LIMIT=6
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

Functional parity is **not claimed** from unit tests alone. The release gate includes live
Snowflake-backed workflow conversations covering contextual reasoning, typo recovery, future-step
deferral, decision routing, non-invention, and latency, in addition to the hermetic suite. Repeat
the live checks for each production environment by following `snowflake_runtime_runbook.md`.

## Deliberately unbuilt features

Translation, PDF/DOCX/OCR, arbitrary-document ingestion, and ingestion-time AI have no current
API-to-runtime contract. They remain unbuilt rather than being represented by unused libraries or
fake methods. Voice recognition and playback are browser-native UI capabilities and do not send
audio to the backend or create a second AI service.

## Remaining environment/dependency limitations

Live Snowflake verification requires owner credentials and cannot be replaced by mocks. Real Ollama
quality/latency verification requires Docker or a host Ollama installation plus model downloads.
Browser speech support varies by browser and operating system, so microphone and playback behavior
must also be checked on each supported employee device profile.
