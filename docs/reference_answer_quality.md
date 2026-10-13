# WorkMate — Reference retrieval and answer quality (Phase 5)

## Runtime implementation

- The authenticated user's department is resolved server-side. Two Snowflake queries fetch: (a) a keyword shortlist and (b) a bounded list of current approved chunks. Both apply department and APPROVED filters in SQL.
- Candidate IDs, department, approval and nonempty source excerpts are verified again in the retrieval service. No cached embedding can override archive or approval status.
- A deterministic tokenizer supports English and Hindi Unicode combining marks. A small reviewed synonym map expands common warehouse nouns without expanding safety-critical actions.
- Optional self-hosted Ollama embedding reranks a maximum of 32 chunks per request using 70% lexical token coverage and 30% positive cosine similarity. Configuration: REFERENCE_HYBRID_ENABLED, REFERENCE_POOL_LIMIT (default 80), REFERENCE_EMBED_MAX_CANDIDATES (default 32), REFERENCE_SEMANTIC_TIMEOUT_SECONDS (default 5).
- If the embedding model times out or is unavailable, the request returns approved keyword evidence only. A semantic match alone does NOT authorize a definitive procedural answer; the final answer must still pass the deterministic source-span support check.
- The current candidate pool is limited to recently updated approved documents. This is not a full vector database and can miss older evidence when a department contains more than 80 indexed chunks. Production-scale recall requires an authorized maintained embedding index with revocation/invalidation tests.

## Answer behavior

Copilot's Ask documents mode returns a short verbatim excerpt, actual source title and character offsets. It never creates workflow transitions or claims an automatic step completion. It abstains and requests review when evidence is missing. SOP guidance mode remains separate and uses the validated OWD workflow graph.

The score in reference mode is a query-term evidence coverage proxy, **not** a calibrated probability that a procedure is correct. Semantic similarity is an uncalibrated relevance hint, never a confidence score.

## Reproducible evaluation

Run: PYTHONPATH=backend python backend/evals/reference_quality_smoke.py
Run tests: PYTHONPATH=backend python -m pytest -q backend/tests/test_reference_quality_smoke.py backend/tests/test_reference_hybrid.py

The committed JSON fixture contains 16 synthetic questions covering receiving, putaway, cycle counts, packing, returns, Hindi text, cross-department sources, draft/archived documents and queries with no answer.
Metrics include lexical top-1 / recall@3, abstention rate, exact citation span integrity and local offline p95 latency. These numbers do not measure Ollama semantic ranking, authentic user language, real Snowflake performance, reasoning quality or speech accuracy.

## Release gates before claiming production-quality AI

1. An independently annotated held-out collection with >100 real organizational queries in Hindi, English and Hinglish, including contradictory SOP revisions and deliberately missing facts.
2. Citation precision, correct abstention, retrieval recall@5, factual faithfulness, wrong-action prevention and p50/p95 latency measured with a real deployed embedding model and approved Snowflake sources.
3. E2E tests for authorization changes, archiving while queries run, local AI outage and conservative reference answer fallback.
4. Capacity/performance testing, encrypted at-rest source handling, observability and deployment configuration review.
5. The four earlier stacked PRs require review and merge; none of this new work has migrated live Snowflake.