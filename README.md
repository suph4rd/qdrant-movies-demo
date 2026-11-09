# Movie recommendations with Qdrant

A local demo with 250 movies, semantic embeddings, an async Python engine and
loader, and a FastAPI interface in English and Russian. Python **3.15.2** is used
locally and in Docker. No JavaScript or build pipeline is required.

The default index is `movies_semantic_v1`: one named `semantic` vector, 384
components, Cosine distance. Embeddings come from a local Hugging Face Text
Embeddings Inference (TEI) CPU service using `intfloat/multilingual-e5-small`.
The original `movies` collection and the ten manual features in `movies.json`
are preserved as historical data. The runtime supports semantic search only;
`movies` is reserved and rejected. IDs and both catalog languages are preserved.

## Docker startup

Run from the repository root. Docker Engine with Compose is sufficient:

```sh
cp env/.env.example env/.env  # Once; merge new settings if this file already exists.
docker compose --env-file env/.env -f docker/compose.yaml config
docker compose --env-file env/.env -f docker/compose.yaml up -d --build
docker compose --env-file env/.env -f docker/compose.yaml ps -a
```

Open http://127.0.0.1:18000 after the loader exits successfully. First startup
requires internet to download the Docker images and approximately 470 MB of
model weights, plus tokenizers. Allow several minutes. The ARM64 CPU image was
verified on Apple Silicon; Docker uses CPU cores, without Metal/MPS acceleration.

TEI has a `/health` readiness check. Compose waits for TEI to be healthy before
starting the loader. The loader additionally waits up to 60 seconds for Qdrant's
`/readyz`. Web starts only after a successful load. A failure prevents web startup;
inspect logs, fix the problem and repeat the startup command:

```sh
docker compose --env-file env/.env -f docker/compose.yaml logs --tail=100 tei loader web qdrant
curl --fail http://127.0.0.1:18080/health
curl --fail http://127.0.0.1:6333/readyz
```

The application runs as an unprivileged user. Ports are bound to IPv4 loopback:
web 18000, TEI 18080, Qdrant REST 6333 and gRPC 6334. On macOS use `127.0.0.1`;
`localhost:18000` may reach AirPlay over IPv6 instead. This is a local demo without
TLS or external access. Qdrant dashboard: http://127.0.0.1:6333/dashboard.

For an existing `env/.env`, merge `WEB_PORT=18000` and `TEI_PORT=18080`;
if it defines `EMBEDDING_URL`, change it to `http://tei:18080`.
Do not replace the file: preserve other local settings. Web and TEI listen on
18000 and 18080 inside their containers as well.

Settings in `env/.env`:

| Setting | Docker default | Local Python default |
| --- | --- | --- |
| `QDRANT_URL` | `http://qdrant:6333` | `http://127.0.0.1:6333` |
| `EMBEDDING_URL` | `http://tei:18080` | `http://127.0.0.1:18080` |
| `MOVIES_COLLECTION` | `movies_semantic_v1` | `movies_semantic_v1` |
| `EMBEDDING_CACHE` | `/home/app/.cache/embeddings` (fixed in Compose) | package-relative `.cache/embeddings` |
| `MOVIES_PATH` | `/app/movies.json` | package-relative `movies.json` |

`WEB_PORT`, `TEI_PORT`, `QDRANT_HTTP_PORT` and `QDRANT_GRPC_PORT` change host ports
only. Update browser/local URLs accordingly. Compose's env file is not read by
local Python. The ignored `env/` directory and local caches are excluded from
image builds; code, catalog and translations are copied into the app image.

The ARM64 TEI **1.9.4** image is pinned by immutable digest:

```text
ghcr.io/huggingface/text-embeddings-inference:cpu-arm64-1.9@sha256:798cd7615e060a72ccbdf19aa0ada52289c6a0147490195bafaece6ce04d70f1
```

On **x86_64 CPU**, set `TEI_IMAGE` in `env/.env` to the official x86_64 image:

```text
ghcr.io/huggingface/text-embeddings-inference:cpu-1.9@sha256:2538ea1c9640d3763b15af668039d24172d063b42337b0c27796fc2be180c78d
```

The x86_64 image manifest was checked; inference was tested on ARM64 only.
Qdrant v1.20.0 is also pinned by digest in Compose.

## Persistence and reloads

Compose keeps three named volumes: `movies-storage` for Qdrant, `model-weights`
for TEI and `embedding-cache` for document embeddings. A normal restart reuses
weights and cached embeddings. Reload the catalog included in the image:

```sh
docker compose --env-file env/.env -f docker/compose.yaml run --rm loader
```

After editing code, JSON, translations or templates, rebuild/recreate:

```sh
docker compose --env-file env/.env -f docker/compose.yaml up -d --build --force-recreate loader web
```

Two loads of unchanged IDs preserve the 250 original movies and any imported movies. The loader validates JSON
and an existing collection's schema/model metadata before encoding. Documents
are encoded in batches of 32. It obtains and validates the complete set before
creating a collection or issuing one Qdrant upsert with `wait=true`; an inference
failure never writes an incomplete set. This is not a transactional replacement
of an index across network/server failures. Extra records are preserved. The loader checks that every original ID is present
instead of requiring a total of exactly 250.

Cache keys hash the exact prepared text and the model, revision, text version,
dimension, pooling, dtype and normalization contract. Every cached vector is
validated before use. Missing/corrupt entries regenerate; unchanged entries do
not call TEI. Files are replaced atomically. The cache is regenerable and ignored
by Git. Removing it only makes the next load encode documents again.

Stop with `docker compose --env-file env/.env -f docker/compose.yaml stop`.
`down` removes containers while preserving volumes. **`down -v` deletes all three
volumes**, including Qdrant data, weights and cached embeddings.

## Local Python

Use a virtual environment with Python 3.15.2:

```sh
python3.15 --version
python3.15 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
docker compose --env-file env/.env -f docker/compose.yaml up -d qdrant tei
curl --fail http://127.0.0.1:6333/readyz
curl --fail http://127.0.0.1:18080/health
python -m engine.load --url http://127.0.0.1:6333 --embedding-url http://127.0.0.1:18080 --data movies.json
python -m uvicorn web.app:create_app --factory --host 127.0.0.1 --port 18000
```

Retry readiness checks until both return successfully. Stop Docker web first if
it already occupies port 18000. Loader flags `--url`, `--embedding-url`,
`--collection`, `--cache`, `--data` and `--lang` override defaults; environment
variables provide defaults for the endpoint, collection and cache settings.
`python -m engine.load --lang ru --help` shows Russian help/errors.

## Search and languages

**By movie** is the default. Enter an internal ID, a title, or `Title (2005)`
in English or Russian. Matching normalizes Unicode, case and whitespace. A
numeric query always means an internal ID; for a numeric title use its year,
for example `1917 (2019)`. Original-catalog title fragments remain supported.
Each matching movie has a separate recommendation group, labelled with its
year, original title and Wikidata QID where available. All source movies are excluded
from every recommendation group.

The search checks the original catalog and saved Qdrant movies first. If neither
contains a match, submitting **By movie** searches Wikidata in English and Russian
and automatically imports exact title/year matches, including aliases and original
titles. Only film entities with complete required metadata are imported. English
names, descriptions and genres are required. Missing Russian metadata falls back
to English, with a visible description-language label. New movies receive semantic
embeddings from TEI and deterministic internal IDs `2000000000000 + numeric QID`
(for example, `Q83495` maps to `2000000083495`). Their Wikidata source links appear
in the interface. Successful imports remain saved if a later import fails; status
messages explain added and skipped cards. Repeated imports do not create duplicate
records. Existing TMDB imports retain their original IDs, metadata and source links.

External imports require no account, API key or token. The web server reads the
public [Wikidata API](https://www.wikidata.org/wiki/Wikidata:Data_access) over HTTPS;
network access to Wikidata is required. Its structured data is published under
CC0. No requests are sent to the TMDB API. `TMDB_API_TOKEN` is no longer used and
can be removed from existing local environment files.

Wikidata descriptions are short identifying phrases, not plot summaries. Imported
movies can therefore produce less precise plot-based recommendations than the
original catalog. The interface marks these descriptions. Incomplete entities are
skipped rather than filled with invented text. Wikipedia text is not imported.

Only POST `/search` can import. GET links, refreshes and language switches never
contact Wikidata or write movies. Movie POST results and messages are kept in a
bounded server-side cache of 128 searches, addressed by an opaque `result`
parameter through the redirect. This demo uses one web worker; snapshots expire
on restart or eviction. An expired link performs a read-only search of saved
movies. Imported movies themselves persist in Qdrant across restarts.

**By description** accepts free text in Russian or English. Select that mode,
enter a plot or mood and submit. TEI encodes the query and Qdrant searches all
movies. There is no source movie in the results. Empty descriptions are rejected.

Choose 5, 10, 20 or 50 results. Mode, text, count and language persist through
POST → GET redirects, refreshes and language links (`mode`, `q`, `limit`, `lang`).
Old links without `mode` use movie search. The interface works without JavaScript.
Cosine scores measure vector similarity, not a probability of liking a movie.

Language priority: supported `lang=en|ru`, saved cookie, `Accept-Language`, then
English. Each request uses its own gettext translator. Catalog metadata is
localized from the application catalog by result ID or from imported Qdrant
payloads, without mutating them.

## Model and text format

Model revision: `614241f622f53c4eeff9890bdc4f31cfecc418b3`. Mean pooling,
float32, normalized output. Text format **`movie-en-v1`** is defined in
[evaluation/README.md](evaluation/README.md). Documents use English title,
genres (original order) and description, with LF separators and no trailing LF:

```text
passage: Title: {title}
Genres: {genres joined with comma and space}
Description: {description}
```

Queries use `query: {trimmed query}` in either language. Embeddings must be 384
finite numbers with nonzero norm; negative components are valid. Requests have
15-second timeouts and disable truncation so oversized text fails explicitly.
The client verifies TEI model/revision/pooling/dtype through `/info` before
encoding. Collection metadata records the complete contract; every search and
load checks compatibility. An incompatible index is rejected with a reindexing
message. Collections are never deleted automatically.

To change the model or text contract, update the pinned specification and TEI
configuration together, bump the text version when appropriate and choose a
**new collection name**, for example `movies_semantic_v2`. Load it before switching
web's `MOVIES_COLLECTION`; recreate web to apply settings. Changed contracts use
new cache keys. Keep the prior collection for rollback.

## Preserved manual features

The original manual vector order remains: science fiction, action, drama,
comedy, romance, suspense/thriller, fantasy/magic, animation, darkness, optimism.
Each vector contains ten finite values in `[0, 1]` and is nonzero. These subjective
annotations are preserved in JSON and the legacy collection.

## Engine and lifecycle

`engine/constants.py` defines shared defaults. `engine/stores/semantic.py` owns
Qdrant calls and resources; `engine/stores/factory.py` configures this single
implementation. `engine/embeddings/` separates the HTTP client, cache, model
specification, text preparation and validation. Public imports are available
from `engine.stores` and `engine.embeddings`. The engine has no web dependency.
The official async Qdrant SDK uses REST with a 15-second timeout and exact search.

`engine/wikidata/` separates transport, entity pagination and batching, parsing,
validation, classification, movie mapping and search. `WikidataClient` is the
public facade for `search`, `movie` and `close`; `EntityClassifier`, `MovieMapper`
and `WikidataSearch` implement the provider-specific work. Each search shares an
entity cache, and injected HTTP clients remain owned by their caller.

`engine/imports/` owns title normalization, matching, external identifiers and
imported-card validation, including legacy TMDB cards. Its public exports remain
available through `engine.imports`. `engine.services.MovieSearchService` receives
the store, catalog and optional Wikidata client. It searches exact catalog titles,
saved cards and partial catalog titles in that order, then imports only when
explicitly allowed. `services.search_movies` remains a compatible wrapper with
structured `groups` and `messages` results.

`engine.i18n` handles shared source-string translation and movie localization;
`engine.errors` formats structured notifications and nested expected errors.
The web layer chooses the request language and uses `MovieSearchService` without
moving HTTP language selection into the engine.

```python
from engine import services
from engine.stores import create_store

store = create_store('http://127.0.0.1:6333')
try:
    similar = await services.search(store, 'The Matrix', catalog, limit=5)
    matching = await services.semantic_search(store, 'a lonely astronaut', limit=5)
finally:
    await store.close()
```

The engine limit is an integer 1–249 in both modes. An injected SDK or embedding
client stays owned by its caller. Owned clients close in `finally` or lifespan.

`web/app.py`'s `ApplicationLifespan` has a fresh instance per startup. The factory performs no catalog reads or network requests. Lifespan
reads/validates JSON once per application, creates clients and closes them on
shutdown; it never indexes data. Restart after catalog/settings changes.
`web/services.py` prepares request-scoped results; routes stay thin. Templates
and CSS are package-relative. Shared `movies.json` resolution does not depend on
working directory; no `sys.path` changes are used.

## Verification and evaluation

Offline tests need neither Qdrant nor TEI. Explicit integration verification
requires both services ready and tests the semantic collection:

```sh
python -m unittest -v
python -m engine.tests.verify
python -m engine.tests.verify_imports
python -m evaluation.runners.probe
python -m evaluation.runners.run
```

`verify_imports` uses a separate temporary collection with real Qdrant and TEI
to check concurrent/repeated import, restart persistence, source exclusion and
reloading all original movies while retaining imports; it deletes only that
temporary collection in `finally`. It does not call Wikidata.

`verify` performs repeated loads, checks the original 250 IDs, both languages, 5/10/20/50
results, source exclusion, unknown IDs, localized catalog metadata and
independent cosine ranking. Verification also proves repeat loads use
no inference. Offline tests cover schema/model incompatibility before writes,
corrupt cache regeneration, generation failures, HTTP errors/timeouts, resource
ownership, and both web modes including localization/navigation. Do not use
Python's `-O` flag, which disables integration assertions.

In Docker:

```sh
docker compose --env-file env/.env -f docker/compose.yaml run --rm --no-deps web python --version
docker compose --env-file env/.env -f docker/compose.yaml run --rm --no-deps web python -m unittest -v
docker compose --env-file env/.env -f docker/compose.yaml run --rm loader python -m engine.tests.verify
```

The verifier respects `QDRANT_URL` and `EMBEDDING_URL`. It writes the cache; use
the loader service, which mounts the persistent cache volume. Quality/latency
artifacts are generated locally in `evaluation/results/`; frozen inputs live in
`evaluation/data/` and package-relative paths in `evaluation/config/`. Run probe
and evaluation sequentially without competing loads. Historical JSON measurements
remain unchanged; fresh measurements use separate `*-latest.json` files. See [the recorded report](evaluation/REPORT.md)
for Recall@5 on 20 frozen RU/EN queries, comparison for ten source movies,
first/subsequent request timings and limitations. This narrow evaluation does
not guarantee better recommendations. Descriptions are short; there is no
personalization, reranker, hybrid search or model training.

Translations live in `engine/translations`. English source strings fall back
through gettext; reviewed Russian `.po` and compiled `.mo` files are committed:

```sh
pybabel extract -F babel.cfg -k N_ -o engine/translations/messages.pot engine web
pybabel update -i engine/translations/messages.pot -d engine/translations
# Translate new entries and review fuzzy flags before compiling.
pybabel compile -d engine/translations
python -m unittest -v
```

Official references: [TEI hardware/images](https://huggingface.co/docs/text-embeddings-inference/supported_models),
[model card](https://huggingface.co/intfloat/multilingual-e5-small),
[Qdrant Query Points](https://api.qdrant.tech/api-reference/search/query-points),
[Compose startup order](https://docs.docker.com/compose/how-tos/startup-order/).
