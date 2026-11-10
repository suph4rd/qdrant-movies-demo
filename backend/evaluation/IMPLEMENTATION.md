# Implementation and verification record

Completed on 2026-11-09 using Python 3.15.2 on macOS ARM64 and Docker Desktop.
The stages were implemented and checked in the order below. No catalog entries,
stable IDs or manual features were changed.

| Stage | Change | Verification |
| --- | --- | --- |
| 1 | Pinned E5 revision and ARM64 TEI 1.9.4; text contract; 20 judgments; ten legacy recommendation lists | Real RU/EN batch returned two normalized 384-dimensional vectors; `results/probe.json`; original 52 offline tests and legacy integration passed before engine changes |
| 2 | Independent async HTTPX embedding client with 15-second timeout, identity/output checks and EN/RU errors | Four offline embedding tests with malformed vectors, HTTP errors, timeout and ownership; real query returned 384 components |
| 3 | Content-addressed cache; batches of 32; complete-set validation before Qdrant writes; separate semantic collection | Six loader/cache tests; two actual loads retained 250 points; patched encoding to fail on any repeat inference and second load succeeded; legacy count stayed 250 |
| 4 | ID/title recommendations and description search; index compatibility; exact Query Points | Independent cosine checks against all 250 stored embeddings; source exclusion, unknown IDs, limits, RU/EN and no source inference; offline search tests |
| 5 | Explicit modes, source-free description results, localized form/errors, persistent URL/language parameters | Web tests cover both modes/languages/counts, old URLs, POST redirects and escaping; 16 real HTTP checks saved in `results/stack.json` |
| 6 | TEI readiness, pinned images, shared settings, persistent weights/cache, loopback ports | Compose config/build/start succeeded; loader exited 0; backend/api/TEI healthy; full stop/start preserved data; additional TEI restart reused the same 470268510-byte weight file (size, mtime and inode unchanged) |
| 7 | Frozen quality evaluation, source comparisons, timing, README startup/reindex/rollback guidance | 70 offline tests passed locally and inside Docker; explicit integration passed locally and inside Docker; `REPORT.md`, `results/results.json`; `git diff --check` passed |

Commands used for the final checks (from the repository root):

```sh
.venv/bin/python -m unittest -q
.venv/bin/python -m backend.engine.tests.verify
.venv/bin/python -m backend.evaluation.runners.probe
.venv/bin/python -m backend.evaluation.runners.run
docker compose --env-file env/.env.example -f docker/compose.yaml config --quiet
docker compose --env-file env/.env.example -f docker/compose.yaml up -d --build
docker compose --env-file env/.env.example -f docker/compose.yaml run --rm --no-deps backend python -m unittest -q
docker compose --env-file env/.env.example -f docker/compose.yaml run --rm loader python -m backend.engine.tests.verify
docker compose --env-file env/.env.example -f docker/compose.yaml stop
docker compose --env-file env/.env.example -f docker/compose.yaml up -d --build
git diff --check
```

TEI's restart logs use the word “Downloading” even for cache hits. The measured
ONNX cache retrieval took less than a millisecond; file metadata was unchanged.
A missing optional `config_sentence_transformers.json` causes a TEI startup
warning but does not prevent readiness or encoding. Client batches of 32 worked;
the ONNX backend internally limits inference batches to eight.

The x86_64 image manifest was inspected and documented, but no x86_64 inference
was run on this ARM64 computer. Existing FastAPI TestClient runs emit a Starlette
HTTPX deprecation warning; all tests pass with the repository's pinned versions.

Quality results are limited to the frozen sample: Recall@5 0.83 (EN 0.84, RU 0.82).
The report retains weak cases and the changed recommendation lists. It does not
claim a general or guaranteed improvement.
