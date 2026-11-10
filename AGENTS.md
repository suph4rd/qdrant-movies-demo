# Repository Guidelines

## Project Structure & Module Organization

This is a local movie-recommendation demo using Python 3.15.2, FastAPI for the JSON API and Vue 3/TypeScript for the web interface, AsyncQdrantClient for async REST calls in the engine and loader, and Qdrant’s REST API.

- `backend/engine/parser.py`: localized CLI argument parsing for `--url`, `--data`, and `--lang`.
- `backend/engine/load.py`: loader arguments (`--url`, `--data`, `--lang`) and localized English/Russian console output; no console recommendations.
- `backend/engine/i18n.py`: shared message keys, source-string translation, movie localization, and gettext catalogs without web dependencies.
- `backend/engine/errors/`: domain exceptions in `exceptions.py`, localization metadata on original library exceptions in `metadata.py`, and localized error and structured notification formatting in `formatting.py`; public exports in `__init__.py`.
- `backend/engine/validators.py`: catalog, metadata, ID, and limit validation.
- `backend/engine/catalog.py`: synchronous JSON reading and title/ID resolution; `backend/engine/services.py`: injected `MovieSearchService` search/import orchestration and compatible `search_movies` wrapper.
- `backend/engine/imports/`: constants, normalized titles, external identity rules, and imported-card validation; public compatibility exports in `__init__.py` include shared QID validation and legacy TMDB support.
- `backend/engine/wikidata/`: transport, paginated/batched entities, parsing, validation, classification, movie mapping, and search; `WikidataClient` is the public facade over `EntityClassifier`, `MovieMapper`, and `WikidataSearch`.
- `backend/engine/constants.py`: shared URLs, collection, catalog path, limits, dimensions, and timeout.
- `backend/engine/embeddings/`: client, cache, pinned specification, text preparation, and validation; public exports in `__init__.py`.
- `backend/engine/stores/`: standalone `SemanticMovieStore` and `create_store`; semantic-only runtime, with `movies` reserved.
- `backend/evaluation/config/`, `runners/`, `data/`, `results/`: package-relative settings, executable probes/evaluation, frozen inputs, and historical measurements.
- `backend/api/app.py`: application factory, composition, and a fresh `ApplicationLifespan` per startup; `backend/api/config.py` holds Settings and `backend/api/create_admin.py` remains the administrator CLI.
- `backend/api/http/`: route registration, dependencies, security, response cookies, and request-local language selection; `api.py` contains JSON search, auth, account, and admin handlers; `spa.py` serves the built client.
- `backend/api/application/`: services that own transactions, DTOs, scenario errors, credential validation, movie snapshot cleaning, and search/session constants. Services may depend on infrastructure and SQLAlchemy, but not HTTP or presentation.
- `backend/api/infrastructure/`: database resource management, ORM models, SQL repositories, password and token hashing, bounded snapshot caches, and UTC clock. Repositories use caller-owned sessions and do not commit.
- `backend/api/presentation/api.py`: localized JSON movie/search/list serialization; no database access.
- `frontend/`: Vue 3, TypeScript, Vite, Vue Router, typed JSON client, session state, EN/RU dictionaries and responsive CSS; `API.md` defines contracts.
- `frontend/src/tests/`, `frontend/e2e/`: component/session tests and mocked-API desktop/mobile browser flows.
- `frontend/dist/`: generated client build, served by FastAPI; ignored in Git.
- `backend/api/requirements.txt`: pinned FastAPI, Uvicorn, qdrant-client, pydantic-settings, Babel, and HTTPX dependencies.
- `backend/engine/tests/`, `backend/api/tests/`: offline unittest engine, loader, and FastAPI TestClient checks with lifespan and async engine tests.
- `backend/api/movies.json`: 250 movies with stable IDs, Russian metadata and English translations, and manually assigned 10-dimensional vectors.
- `backend/engine/tests/verify.py`: integration checks and mocked collection-schema checks.
- `backend/api/migrations/`, `backend/api/alembic.ini`: explicit database migrations; run `python -m alembic -c backend/api/alembic.ini upgrade head` from the repository root.
- `backend/api/Dockerfile`, `frontend/Dockerfile`: separate Python and Node/Nginx builds.
- `docker/compose.yaml`: pinned Qdrant image, loopback ports, and persistent Docker volume.
- `README.md`: English-language setup instructions and feature definitions.

Keep the engine and API packages separate. Define the shared backend/api/movies.json path in engine relative to package files; do not modify sys.path. Add __init__.py files for unittest discovery. Client assets resolve from the package-relative `frontend/dist` directory. Build with Node 24 and npm; Python production does not require Node. Keep movie IDs as strings across JSON and TypeScript, and preserve verified imported-card references.

## Build, Test, and Development Commands

Run commands from the repository root:

```sh
python3.15 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r backend/api/requirements.txt # Install engine, loader, and web dependencies
npm --prefix frontend ci
npm --prefix frontend run build       # TypeScript and production assets
npm --prefix frontend test            # Component and session tests
(cd frontend && npx playwright install chromium && npm run test:e2e)
python3 -m unittest -v                 # Run offline tests
python3 -m uvicorn backend.api.app:create_app --factory --host 127.0.0.1 --port 18000
cp env/.env.example env/.env           # Create local Docker settings once
docker compose --env-file env/.env -f docker/compose.yaml config                  # Validate Compose configuration
docker compose --env-file env/.env -f docker/compose.yaml up -d --build                   # Build and start the Docker stack
curl --fail http://127.0.0.1:6333/readyz # Check readiness
curl --fail http://127.0.0.1:18080/health # Check TEI readiness
python -m backend.engine.load                 # Validate and upsert the dataset
python -m backend.engine.tests.verify          # Verify local Qdrant and TEI
python -m backend.evaluation.runners.probe     # Run sequentially
python -m backend.evaluation.runners.run
```

Docker build files are `backend/api/Dockerfile` and `frontend/Dockerfile`; both use the repository root as build context. Python startup and health scripts live in `backend/scripts/`; the TEI script remains in `docker/scripts/`. Compose backend, loader and migrate share the Python image. Nginx serves the frontend and proxies `/api` to backend with the original URI, Host, Origin and cookies. `env/.env.example` documents host ports and the shared Docker `QDRANT_URL`; local `env/.env` is ignored and excluded from builds. Docker uses `http://qdrant:6333`, while local Python uses the published loopback endpoint.

Wait for readiness before loading or verifying. Install requirements in a virtual environment for the engine, loader, web interface, and all checks. The engine and loader use the official async SDK over REST; the web uses FastAPI. Use `python -m backend.engine.load --url http://127.0.0.1:6333 --data backend/api/movies.json` to specify the endpoint explicitly.

## Language Policy

Documentation, code, and comments must be in English. Communicate with the user in Russian. User-facing text must support English and Russian localizations. Existing user-facing text and all 250 catalog entries support both languages. Preserve both versions when making changes.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` functions and variables, and `PascalCase` exception classes. Follow the existing single-quoted string style where practical. Use AsyncQdrantClient over REST with a 15-second timeout. Keep validation and in-memory title resolution synchronous; await network operations. Close owned clients in finally or lifespan. Provide English and Russian translations for all new user-facing text. Annotate expected library failures with `errors.annotate_error()` and re-raise the original exception; preserve types, diagnostic attributes, and exception causes. Use domain exceptions with ValueError, LookupError, or RuntimeError categories. All API mutations require the `X-CSRF-Token` header and same-origin Origin checks; rotate CSRF after authentication changes. GET search never imports. At CLI/web boundaries, check `errors.is_expected_error()` and translate with `errors.format_error()`. Use module imports for internal dependencies and qualify members; direct imports are allowed for public re-exports in `__init__.py`. Do not convert unexpected programming errors into service failures. Do not add initial comments or module docstrings that describe a source file's purpose. Preserve shebangs, required service headers, and comments explaining logic. No formatter or linter is configured.

## Testing Guidelines

`backend/engine/tests/verify.py` uses plain assertions and `unittest.mock.patch`; no coverage threshold is configured. It runs only through explicit module invocation, outside offline unittest discovery. Run it without Python’s `-O` flag, which disables assertions. Extend it for changed behavior, including ranking accuracy, source-ID exclusion, unknown IDs, and schema rejection before writes. Verify repeated loads retain exactly 250 records.

## Commit & Pull Request Guidelines

Git history is unavailable in this checkout, so no existing commit convention can be established. Use concise, imperative subjects such as `Validate movie vector dimensions`. Pull requests should explain the behavior change, list verification commands and results, and update the README when usage changes.

## Data & Configuration Safety

Preserve stable movie IDs and the documented feature order. Vectors must contain 10 finite values in `[0, 1]` and be nonzero. Keep Qdrant ports bound to loopback. `docker compose --env-file env/.env -f docker/compose.yaml down` preserves data; `docker compose --env-file env/.env -f docker/compose.yaml down -v` deletes the storage volume.

The factory performs no catalog reads or network operations. Read and validate JSON once in lifespan, keep the catalog per application, and restart after catalog changes. Use request-local gettext translators. Use IsolatedAsyncioTestCase and AsyncMock for SDK checks. Use Python 3.15.2.

The frontend publishes loopback port 18000; the backend listens on 18000 only inside the Docker network. Local FastAPI listens on 18000. TEI uses 18080 inside and outside Docker by default. Merge these host ports and `EMBEDDING_URL=http://tei:18080` into existing local env files without overwriting them. Preserve existing collections and historical evaluation measurements. The runtime uses only the semantic store; manual 10-dimensional vectors remain validated catalog data.
