# Semantic retrieval evaluation

The judgments in `data/queries.json` were selected before running semantic retrieval.
There are ten plot intents, each phrased in English and Russian (20 queries).
Relevant IDs are explicit plot matches in the current catalog. This small,
hand-selected set checks behavior; it is not a general movie search benchmark.

`data/legacy.json` preserves the top five neighbors for ten source movies, computed
independently from the original ten-dimensional vectors using exhaustive cosine.
Ties use ascending stable IDs. Qdrant may order equal scores differently.

Recall@5 is `len(set(top_5_ids) & set(relevant_ids)) / len(set(relevant_ids))`.
Report the arithmetic mean overall and separately for RU and EN. Do not change
judgments after observing retrieval. Compare the ten source recommendation lists
using overlap@5 and retain both lists for inspection, without claiming that
changed recommendations necessarily improve quality.

Measure wall-clock latency with `time.perf_counter` in one sequential process.
Report the first description request separately, then min/median/p95 of subsequent
requests, including TEI encoding and Qdrant retrieval. These are client-observed
latencies on a locally running, ready stack; the first request does not include
initial model download or process startup. Record platform and model identity.

# Text contract: movie-en-v1

Documents use the English translation only, in this exact format, with a single
space after `passage:` and LF separators, no trailing newline:

```text
passage: Title: {title}
Genres: {genres joined by comma and space}
Description: {description}
```

The original strings and genre order are preserved. Queries are trimmed and
encoded as `query: {query}` in either English or Russian. Embeddings have 384
finite components and nonzero norm; negative components are allowed. TEI uses
mean pooling from the model configuration, float32, and normalized output.

Model: `intfloat/multilingual-e5-small`.
Revision: `614241f622f53c4eeff9890bdc4f31cfecc418b3`.
ARM64 image: `ghcr.io/huggingface/text-embeddings-inference:cpu-arm64-1.9@sha256:798cd7615e060a72ccbdf19aa0ada52289c6a0147490195bafaece6ce04d70f1`.

Official references:
- https://huggingface.co/intfloat/multilingual-e5-small
- https://huggingface.co/docs/text-embeddings-inference/supported_models
- https://github.com/huggingface/text-embeddings-inference

Run the probe and evaluation sequentially against the ready stack:

```sh
.venv/bin/python -m evaluation.runners.probe
.venv/bin/python -m evaluation.runners.run
```

Settings are resolved from the engine defaults and environment variables in
`config/settings.py`. Data and result paths are package-relative, independent
of the working directory. Frozen judgments and the legacy baseline live in
`data/`; measurements live in `results/`. Markdown reports stay in this directory.

Fresh runs write `results/probe-latest.json`, `results/results-latest.json` and
`REPORT-latest.md`; historical measurements and `REPORT.md` are preserved.
