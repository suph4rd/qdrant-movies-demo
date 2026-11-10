# Movie recommendations with Qdrant

A local demo with 250 movies, semantic embeddings, an async Python engine and
loader, and a Vue 3 / TypeScript interface in English and Russian served by Nginx in Docker and FastAPI locally.
Python **3.15.2** is used locally and in Docker. Node **24** is required only
for client development and builds; Docker builds the client in a separate image.

The default index is `movies_semantic_v1`: one named `semantic` vector, 384
components, Cosine distance. Embeddings come from a local Hugging Face Text
Embeddings Inference (TEI) CPU service using `intfloat/multilingual-e5-small`.
The original `movies` collection and the ten manual features in `backend/api/movies.json`
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
`/readyz`. The backend starts after migration and loading succeed; the frontend
starts after the backend is healthy. A failure prevents application startup;
inspect logs, fix the problem and repeat the startup command:

```sh
docker compose --env-file env/.env -f docker/compose.yaml logs --tail=100 tei loader backend qdrant
curl --fail http://127.0.0.1:18080/health
curl --fail http://127.0.0.1:6333/readyz
```

The application runs as an unprivileged user. Ports are bound to IPv4 loopback:
web 18000, TEI 18080, Qdrant REST 6333, gRPC 6334 and Kafka 19092. On macOS use `127.0.0.1`;
`localhost:18000` may reach AirPlay over IPv6 instead. This is a local demo without
TLS or external access. Qdrant dashboard: http://127.0.0.1:6333/dashboard.

For an existing `env/.env`, merge `WEB_PORT=18000` and `TEI_PORT=18080`;
if it defines `EMBEDDING_URL`, change it to `http://tei:18080`.
Do not replace the file: preserve other local settings. The backend listens on 18000 inside the Docker network without a published port.
The frontend publishes host port 18000 to Nginx port 80; TEI listens on 18080.

Settings in `env/.env`:

| Setting | Docker default | Local Python default |
| --- | --- | --- |
| `QDRANT_URL` | `http://qdrant:6333` | `http://127.0.0.1:6333` |
| `EMBEDDING_URL` | `http://tei:18080` | `http://127.0.0.1:18080` |
| `MOVIES_COLLECTION` | `movies_semantic_v1` | `movies_semantic_v1` |
| `EMBEDDING_CACHE` | `/home/app/.cache/embeddings` (fixed in Compose) | repository-root `.cache/embeddings` |
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:9092` | `127.0.0.1:19092` |
| `MOVIES_PATH` | `/app/backend/api/movies.json` | package-relative `backend/api/movies.json` |

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

Compose keeps four named volumes: `movies-storage` for Qdrant, `model-weights`
for TEI, `embedding-cache` for document embeddings and `accounts-storage` for PostgreSQL. A normal restart reuses
weights and cached embeddings. Reload the catalog included in the image:

```sh
docker compose --env-file env/.env -f docker/compose.yaml run --rm loader
```

After editing code, JSON, translations or client files, rebuild/recreate:

```sh
docker compose --env-file env/.env -f docker/compose.yaml up -d --build --force-recreate loader backend frontend
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
`down` removes containers while preserving volumes. **`down -v` deletes all four
volumes**, including accounts, Qdrant data, weights and cached embeddings.

The repository root is the build context for both `backend/api/Dockerfile` and
`frontend/Dockerfile`. Backend, loader, migrate, publisher and worker share one Python image with
no Node dependency. Python startup and health scripts live in `backend/scripts/`;
the TEI entrypoint remains in `docker/scripts/`. Nginx returns 404 for missing
assets, disables index caching and caches hashed assets for one year.

## Local Python

Use a virtual environment with Python 3.15.2:

```sh
python3.15 --version
python3.15 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/api/requirements.txt
docker compose --env-file env/.env -f docker/compose.yaml up -d qdrant tei postgres kafka kafka-init
curl --fail http://127.0.0.1:6333/readyz
curl --fail http://127.0.0.1:18080/health
python -m backend.engine.load --url http://127.0.0.1:6333 --embedding-url http://127.0.0.1:18080 --data backend/api/movies.json
export DATABASE_URL='postgresql+psycopg://movies:movies@127.0.0.1:5432/movies'
python -m alembic -c backend/api/alembic.ini upgrade head
npm --prefix frontend ci
npm --prefix frontend run build
python -m uvicorn backend.api.app:create_app --factory --host 127.0.0.1 --port 18000
```

Retry readiness checks until both return successfully. Stop Docker frontend first if
it already occupies port 18000. Loader flags `--url`, `--embedding-url`,
`--collection`, `--cache`, `--data` and `--lang` override defaults; environment
variables provide defaults for the endpoint, collection and cache settings.
`python -m backend.engine.load --lang ru --help` shows Russian help/errors.

## Client development and verification

Use Node 24 and npm. From the repository root:

```sh
npm --prefix frontend ci
npm --prefix frontend run dev
# In another terminal, run FastAPI on 127.0.0.1:18000 as above.
```

Vite proxies `/api` to FastAPI, so development uses the same cookie/CSRF
contract. Open Vite's printed local address. Production uses one origin on
port 18000; Nginx serves the built assets and SPA, and proxies `/api` and `/api/*`
to `backend:18000` with the original URI, Host, Origin and cookies. Locally,
FastAPI serves the root `frontend/dist` build. Node is absent from the
Python runtime image. Build before running local production or after changes:

```sh
npm --prefix frontend run build
npm --prefix frontend test
cd frontend
npx playwright install chromium
npm run test:e2e
```

The build checks TypeScript. Component tests cover search, accounts, session
state and administrative actions. Playwright runs desktop/mobile browser flows
against a mocked API, including navigation, language, authentication, lists and
administration. Python API tests use mocked engine/database boundaries; optional
PostgreSQL tests exercise the same JSON contract with real transactions.
Docker Compose builds the client automatically. Missing builds are diagnosed
at request time; the application factory still performs no catalog/network I/O.

## Search and languages

**By movie** is the default. Enter an internal ID, a title, or `Title (2005)`
in English or Russian. Matching normalizes Unicode, case and whitespace. A
numeric query always means an internal ID; for a numeric title use its year,
for example `1917 (2019)`. Original-catalog title fragments remain supported.
Each matching movie has a separate recommendation group, labelled with its
year, original title and Wikidata QID where available. All source movies are excluded
from every recommendation group.

The search checks the original catalog and saved Qdrant movies first. If neither
contains a match, submitting **By movie** queues a background Wikidata search in
English and Russian and automatically imports verified title/year matches, including aliases and original
titles. Search tries the original query, normalized spelling, then English/Russian
Wikipedia search with Wikidata QIDs from page properties (at most 50 candidates
per language per stage). Wikipedia candidates undergo the same Wikidata checks.
Normalization ignores punctuation, quote/dash differences, whitespace and Russian ё/е.
Exact matches take priority; without a year, multiple exact films remain visible.
For titles of at least five characters, a Levenshtein similarity of at least 0.90
and a lead of at least 0.05 permits automatic correction with a notification.
A supplied year is mandatory. Uncertain matches are not imported. Only film entities with complete required metadata are imported. English
names, descriptions and genres are required. Missing Russian metadata falls back
to English, with a visible description-language label. New movies receive semantic
embeddings from TEI and deterministic internal IDs `2000000000000 + numeric QID`
(for example, `Q83495` maps to `2000000083495`). Their Wikidata source links appear
in the interface. Successful imports remain saved if a later import fails; status
messages explain added and skipped cards. Repeated imports do not create duplicate
records. Existing TMDB imports retain their original IDs, metadata and source links.

External imports require no account, API key or token. The queue worker reads the
public [Wikidata API](https://www.wikidata.org/wiki/Wikidata:Data_access) over HTTPS;
network access to Wikidata and Wikipedia is required. Its structured data is published under
CC0. No requests are sent to the TMDB API. `TMDB_API_TOKEN` is no longer used and
can be removed from existing local environment files.

Wikidata descriptions are short identifying phrases, not plot summaries. Imported
movies can therefore produce less precise plot-based recommendations than the
original catalog. The interface marks these descriptions. Incomplete entities are
skipped rather than filled with invented text. Wikipedia text is not imported.
Type and genre ancestry checks handle cycles and share a batched entity cache;
a 512-node bound produces an incomplete-verification notification. Series and
adult content remain excluded. Provider failures have separate notifications.
No external catalog can guarantee every film.

POST `/api/search` returns a synchronous result token for saved movies and description
queries. External searches return 202 and run through PostgreSQL outbox → Kafka →
worker → PostgreSQL → WebSocket. Only queue workers contact Wikidata or import movies;
GET links, refreshes and language switches never do. Local result snapshots use a
bounded process-local cache of 128 searches, addressed by `result` in the URL;
they expire on restart or eviction. An expired local link performs a read-only
search of saved movies. External task results are durable and addressed by `task`
in the URL. Their messages and movie cards are localized when read, with fresh
verified mark references. Imported movies persist in Qdrant across restarts.

**By description** accepts free text in Russian or English. Select that mode,
enter a plot or mood and submit. TEI encodes the query and Qdrant searches all
movies. There is no source movie in the results. Empty descriptions are rejected.

Choose 5, 10, 20 or 50 results. Mode, text, count and language persist through
POST → GET navigation, refreshes and language links (`mode`, `q`, `limit`, `lang`).
Old links without `mode` use movie search. The Vue interface requires JavaScript.
Cosine scores measure vector similarity, not a probability of liking a movie.

Language priority: supported `lang=en|ru`, saved cookie, `Accept-Language`, then
English. Each request uses its own gettext translator. Catalog metadata is
localized from the application catalog by result ID or from imported Qdrant
payloads, without mutating them.

## Model and text format

Model revision: `614241f622f53c4eeff9890bdc4f31cfecc418b3`. Mean pooling,
float32, normalized output. Text format **`movie-en-v1`** is defined in
[backend/evaluation/README.md](backend/evaluation/README.md). Documents use English title,
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
backend's `MOVIES_COLLECTION`; recreate backend to apply settings. Changed contracts use
new cache keys. Keep the prior collection for rollback.

## Preserved manual features

The original manual vector order remains: science fiction, action, drama,
comedy, romance, suspense/thriller, fantasy/magic, animation, darkness, optimism.
Each vector contains ten finite values in `[0, 1]` and is nonzero. These subjective
annotations are preserved in JSON and the legacy collection.

## Engine and lifecycle

`backend/engine/constants.py` defines shared defaults. `backend/engine/stores/semantic.py` owns
Qdrant calls and resources; `backend/engine/stores/factory.py` configures this single
implementation. `backend/engine/embeddings/` separates the HTTP client, cache, model
specification, text preparation and validation. Public imports are available
from `backend.engine.stores` and `backend.engine.embeddings`. The engine has no web dependency.
The official async Qdrant SDK uses REST with a 15-second timeout and exact search.

`backend/engine/wikidata/` separates transport, entity pagination and batching, parsing,
validation, classification, movie mapping and search. `WikidataClient` is the
public facade for `search`, `movie` and `close`; `EntityClassifier`, `MovieMapper`
and `WikidataSearch` implement the provider-specific work. Each search shares an
entity cache, and injected HTTP clients remain owned by their caller.

`backend/engine/imports/` owns title normalization, matching, external identifiers and
imported-card validation, including legacy TMDB cards. Its public exports remain
available through `backend.engine.imports`. `backend.engine.services.MovieSearchService` receives
the store, catalog and optional Wikidata client. It searches exact catalog titles,
saved cards and partial catalog titles in that order, then imports only when
explicitly allowed. `services.search_movies` remains a compatible wrapper with
structured `groups` and `messages` results.

`backend.engine.i18n` handles shared source-string translation and movie localization;
`backend.engine.errors` formats structured notifications and nested expected errors.
The web layer chooses the request language and uses `MovieSearchService` without
moving HTTP language selection into the engine.

```python
from backend.engine import services
from backend.engine.stores import create_store

store = create_store('http://127.0.0.1:6333')
try:
    similar = await services.search(store, 'The Matrix', catalog, limit=5)
    matching = await services.semantic_search(store, 'a lonely astronaut', limit=5)
finally:
    await store.close()
```

The engine limit is an integer 1–249 in both modes. An injected SDK or embedding
client stays owned by its caller. Owned clients close in `finally` or lifespan.

`backend/api/app.py`'s `ApplicationLifespan` has a fresh instance per startup. The factory performs no catalog reads or network requests. Lifespan
reads/validates JSON once per application, creates clients and closes them on
shutdown; it never indexes data. Restart after catalog/settings changes.
`backend/api/application/services/` contains search, authentication, account, and
administration scenarios with injected dependencies and transaction ownership.
`backend/api/application/` also holds plain DTOs, scenario errors, credential validation,
search constants, and movie snapshot cleaning. Services may depend on SQLAlchemy
and infrastructure, but never on HTTP or presentation.
`backend/api/infrastructure/repositories/` contains SQL and locking operations using the
caller's session, without committing. `backend/api/infrastructure/models.py` owns ORM
models; `database.py` manages database resources, `clock.py` supplies UTC time,
and `passwords.py` handles Argon2, rehash checks, and token hashing.
`backend/api/infrastructure/snapshots.py` owns per-application FIFO caches
(128 search results and 1024 movie card references).
`backend/api/http/dependencies.py` constructs application services. HTTP routes depend on
adapters and transport helpers; adapters depend on transport, while transport never
imports routes, adapters or service factories. The combined router registers SPA last.
`backend/api/http/routes/` exposes the same application services through JSON under `/api`.
`backend/api/http/adapters/security.py` resolves cookie sessions and checks roles.
`backend/api/http/transport/security.py` checks Origin and the `X-CSRF-Token`
header. `/api/context` supplies the user, language, CSRF token, catalog, marks
and search options; authentication rotates both session and CSRF tokens.
`backend/api/presentation/api.py` localizes and serializes data without database access.
Movie IDs are decimal strings throughout JSON, preserving unsigned 64-bit IDs.
`frontend/API.md` documents endpoints, errors and pagination.

`frontend/src/` contains Vue pages, shared components, a typed fetch client,
session state and EN/RU dictionaries. Vue Router preserves search snapshots,
query parameters, language and pagination in browser history. The original CSS
is retained in `frontend/src/style.css`. `backend/api/http/routes/spa.py` serves `frontend/dist`
relative to package files, including direct links to account and admin pages.
Unknown API/static paths return 404; a missing client build returns a localized
503 with build instructions. No Jinja2 templates or HTML form handlers remain.
`backend/api/config.py` holds settings; `python -m backend.api.create_admin` uses the same
application authentication service as the web interface. Shared `backend/api/movies.json`
resolution does not depend on working directory; no `sys.path` changes are used.

## Verification and evaluation

Offline tests need neither Qdrant nor TEI. Explicit integration verification
requires both services ready and tests the semantic collection:

```sh
python -m unittest -v
python -m backend.engine.tests.verify
python -m backend.engine.tests.verify_imports
python -m backend.evaluation.runners.probe
python -m backend.evaluation.runners.run
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
docker compose --env-file env/.env -f docker/compose.yaml run --rm --no-deps backend python --version
docker compose --env-file env/.env -f docker/compose.yaml run --rm --no-deps backend python -m unittest -v
docker compose --env-file env/.env -f docker/compose.yaml run --rm loader python -m backend.engine.tests.verify
```

The verifier respects `QDRANT_URL` and `EMBEDDING_URL`. It writes the cache; use
the loader service, which mounts the persistent cache volume. Quality/latency
artifacts are generated locally in `backend/evaluation/results/`; frozen inputs live in
`backend/evaluation/data/` and package-relative paths in `backend/evaluation/config/`. Run probe
and evaluation sequentially without competing loads. Historical JSON measurements
remain unchanged; fresh measurements use separate `*-latest.json` files. See [the recorded report](backend/evaluation/REPORT.md)
for Recall@5 on 20 frozen RU/EN queries, comparison for ten source movies,
first/subsequent request timings and limitations. This narrow evaluation does
not guarantee better recommendations. Descriptions are short; there is no
personalization, reranker, hybrid search or model training.

Translations live in `backend/engine/translations`. English source strings fall back
through gettext; reviewed Russian `.po` and compiled `.mo` files are committed:

```sh
pybabel extract -F backend/api/babel.cfg -k N_ -o backend/engine/translations/messages.pot backend/engine backend/api
pybabel update -i backend/engine/translations/messages.pot -d backend/engine/translations
# Translate new entries and review fuzzy flags before compiling.
pybabel compile -d backend/engine/translations
python -m unittest -v
```

Official references: [TEI hardware/images](https://huggingface.co/docs/text-embeddings-inference/supported_models),
[model card](https://huggingface.co/intfloat/multilingual-e5-small),
[Qdrant Query Points](https://api.qdrant.tech/api-reference/search/query-points),
[Compose startup order](https://docs.docker.com/compose/how-tos/startup-order/).

## Accounts, movie lists and administration

Guests retain access to search and recommendations. `/register` accepts an email,
a password of 12–128 characters and its confirmation. Emails are normalized and
remain reserved after soft deletion. Passwords use Argon2id. Registration signs
in the new user; `/login` creates a seven-day session. The HttpOnly session cookie
contains a random token; PostgreSQL stores only its SHA-256 hash. POST `/api/logout`
revokes the current session. Blocked and deleted users cannot sign in or use
protected routes. Every modifying API request, including search/import, requires a CSRF header.

`/account` shows Watched, Liked and Watchlist, with 20 movies per page. Movie cards
provide buttons that set the requested state, so repeating a POST is safe. Watched
and Watchlist are mutually exclusive; Liked is independent. Server-validated
bilingual snapshots are saved in PostgreSQL and survive restarts and Qdrant
outages. Imported-card references expire on server restart or cache eviction;
search again if an unsaved card's reference expires. Saved cards remain usable.
Changing a mark updates the current search or account page in place, preserving
query parameters and the result snapshot. Pagination controls appear only for
lists containing more than one page. Lists do not change recommendation rankings.

The search page reads the exact movie count from the active Qdrant collection on
every search result load, including after imports and snapshot refreshes. If Qdrant is
unavailable, the count is shown as unavailable while saved results remain visible.

PostgreSQL 18.1 has a separate `accounts-storage` volume and a readiness check.
Compose runs the `migrate` service before backend starts. Migrations are explicit;
the application factory and startup never apply schema changes. For local Python:

```sh
docker compose --env-file env/.env -f docker/compose.yaml up -d postgres
export DATABASE_URL='postgresql+psycopg://movies:movies@127.0.0.1:5432/movies'
export COOKIE_SECURE=false  # Explicit local HTTP setting; use true with HTTPS.
python -m alembic -c backend/api/alembic.ini upgrade head
python -m backend.api.create_admin --lang en
python -m uvicorn backend.api.app:create_app --factory --host 127.0.0.1 --port 18000
```

Use the credentials configured in `env/.env`; URL-encode special password
characters in `DATABASE_URL`. Compose's URL uses hostname `postgres`, whereas
local Python uses the published loopback endpoint. Set `POSTGRES_DB`,
`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`, `DATABASE_URL` and
`COOKIE_SECURE` in an existing env file without replacing other settings.
Changing PostgreSQL initialization variables does not change an existing database.
SQLAlchemy 2.1.8, psycopg 3.3.8, Alembic 1.20.1 and argon2-cffi 25.1.0 are pinned;
the installed packages were checked under Python 3.15.2.

Create the first administrator interactively; passwords are never command-line
arguments. In Docker:

```sh
docker compose --env-file env/.env -f docker/compose.yaml exec backend python -m backend.api.create_admin --lang ru
```

The command refuses if an active administrator already exists. `/admin/users`
provides email search, role/state filters, pagination and read-only user lists.
Administrators can block/unblock, grant/revoke administrator roles, and soft-delete
users by confirming their email in a separate form. Blocking and deletion revoke
all sessions. Restoring a deleted user preserves their email and lists and leaves
them blocked; unblock them separately before they can sign in again. Self-block,
self-deletion and self-demotion are prohibited. A transaction-level PostgreSQL
advisory lock serializes administrative changes and protects the last active
administrator, including concurrent actions and initial administrator creation.

Email confirmation, email password recovery, OAuth and recommendation
personalization are outside this version.

### PostgreSQL backup and restore

Keep backups outside Docker volumes. Replace the database/user if customized:

```sh
docker compose --env-file env/.env -f docker/compose.yaml exec -T postgres pg_dump -U movies -d movies -Fc > accounts.dump
# Restore into a separate, empty database created by your PostgreSQL operator:
docker compose --env-file env/.env -f docker/compose.yaml exec -T postgres pg_restore -U movies -d movies_restore --no-owner < accounts.dump
```

`down` preserves account data. `down -v` also deletes `accounts-storage`, including
users, sessions and saved lists. Back it up before removing volumes.

### Account integration tests

Offline unittest discovery skips PostgreSQL tests unless `TEST_DATABASE_URL` is
set. Use a separate, disposable database, apply migrations, then run all tests:

```sh
export TEST_DATABASE_URL='postgresql+psycopg://movies:movies@127.0.0.1:5432/movies_test'
DATABASE_URL="$TEST_DATABASE_URL" python -m alembic -c backend/api/alembic.ini upgrade head
python -m unittest -v
```

Do not point integration tests at the application database. Tests cover account
isolation, session expiry/revocation, state transitions, CSRF, imported snapshots,
pagination and administration. Qdrant and TEI are mocked for these scenarios.

## External search queue

Each account can have one `queued` or `running` external search across tabs,
browsers and backend processes. Guests share a slot within a random HttpOnly
browser cookie; the database stores a hash, never the cookie secret. The saved
catalog/Qdrant lookup runs first, so local movie and description searches remain
available. Submitting the same trimmed query, mode and limit returns the active
`task_id` with 202. A different external request gets 409
`external_search_in_progress` with a link to that task. Logging in uses the
account slot for new tasks and also checks this browser's active guest task.

Notifications appear on every page without automatic navigation. WebSocket
reconnects restore unread completions, deduplicated by task ID. Opening a result
or selecting **Mark as read** acknowledges it. Only terminal status releases the
slot; acknowledgement does not. Browser disconnection and infrastructure outages
do not release it. No automatic cancellation or result deletion is implemented.
Expected failures are stored with localization metadata; unexpected worker errors
are logged with tracebacks and shown as a safe localized message. Completed
failures are not retried automatically.

Owner rows are locked in stable order in a short transaction; a partial unique
index additionally enforces one active task per owner. The same transaction
creates its outbox record. The publisher sends `{version:1,task_id}` keyed by
`task_id` to `movie-search.requests.v1`, and marks publication only after broker
acknowledgement. Delivery is at least once. Worker group
`movie-search-workers-v1` skips completed tasks, uses a fenced 60-second attempt
lease renewed every 15 seconds, and commits the partition offset only after
terminal state is durable. Network operations hold no database transaction.
Expired attempts can be reclaimed; Qdrant's deterministic IDs and atomic
insert-only import make re-execution safe after an interrupted write. Graceful
shutdown cancels work and releases its attempt lease before closing clients,
while keeping the user's slot occupied until completion.

Compose includes a single KRaft broker, Apache Kafka **4.1.2**, pinned by digest,
with persistent `kafka-storage`. `kafka-init` creates three partitions with
replication factor 1 and seven-day retention. Publisher and worker use the shared
Python image and pinned `aiokafka==0.15.0`, verified on Python 3.15.2. Nginx and
Vite forward WebSocket upgrades; the server sends heartbeat messages every 15
seconds. Kafka is published only on `127.0.0.1:19092` by default. For an existing
`env/.env`, merge `KAFKA_PORT=19092` and `KAFKA_BOOTSTRAP_SERVERS=kafka:9092`
without replacing other settings. Changing `KAFKA_PORT` changes both its host port
and advertised external listener; local clients must use the new port.

The normal `docker compose ... up -d --build` command runs migrations, broker
initialization, publisher and worker. For local Python, start Kafka with the
infrastructure command above, wait for `kafka-init` to exit successfully, and run
these in separate terminals with the same database and store settings as FastAPI:

```sh
source .venv/bin/activate
export DATABASE_URL='postgresql+psycopg://movies:movies@127.0.0.1:5432/movies'
export KAFKA_BOOTSTRAP_SERVERS='127.0.0.1:19092'
python -m backend.api.queue.publisher
# In another terminal with the same environment:
python -m backend.api.queue.worker
```

Diagnose pending tasks without deleting volumes or clearing active slots:

```sh
docker compose --env-file env/.env -f docker/compose.yaml ps -a
docker compose --env-file env/.env -f docker/compose.yaml logs --tail=100 kafka kafka-init publisher worker
docker compose --env-file env/.env -f docker/compose.yaml exec kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group movie-search-workers-v1
```

An unpublished outbox row indicates the publisher/broker needs recovery. A
published queued task points to worker availability or consumer lag. A running
task with an expired lease can be resumed by redelivery after worker restart.
PostgreSQL remains the source of truth. Recover infrastructure rather than
manually releasing the user slot. Keep outages shorter than Kafka's seven-day
retention; if records expire, an operator must republish the affected active task
IDs. `down` preserves Kafka data; `down -v` deletes its volume as well.

Queue verification uses disposable PostgreSQL schemas. With a separate test
database and ready Kafka/Qdrant/TEI on their default loopback ports:

```sh
export TEST_DATABASE_URL='postgresql+psycopg://movies:movies@127.0.0.1:5432/movies_test'
python -m unittest -v
QUEUE_INTEGRATION=1 python -m unittest -v backend.api.tests.test_search_queue
```

The optional integration test creates and removes its own Kafka topic and Qdrant
collection. A deterministic Wikidata fixture exercises the real publisher,
consumer, PostgreSQL, TEI and Qdrant without depending on live provider data. It
kills the worker after the Qdrant insert, expires the abandoned lease, starts a
new worker process, and verifies completion, committed offsets and one movie
after duplicate Kafka deliveries. HTTP/database tests cover concurrent owners,
authentication transitions, failures, CSRF and account isolation; WebSocket and
desktop/mobile browser tests cover origin checks, reconnects, both languages and
notifications across navigation and reloads.
