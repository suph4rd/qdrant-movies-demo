# Repository Guidelines

## Project Structure & Module Organization

This is a local movie-recommendation demo using Python 3.15.2, FastAPI for the web interface, AsyncQdrantClient for async REST calls in the engine and loader, and Qdrant’s REST API.

- `engine/parser.py`: localized CLI argument parsing for `--url`, `--data`, and `--lang`.
- `engine/load.py`: loader arguments (`--url`, `--data`, `--lang`) and localized English/Russian console output; no console recommendations.
- `engine/i18n.py`: shared message keys, source-string translation, movie localization, and gettext catalogs without web dependencies.
- `engine/errors/`: domain exceptions in `exceptions.py`, localization metadata on original library exceptions in `metadata.py`, and localized error and structured notification formatting in `formatting.py`; public exports in `__init__.py`.
- `engine/validators.py`: catalog, metadata, ID, and limit validation.
- `engine/catalog.py`: synchronous JSON reading and title/ID resolution; `engine/services.py`: injected `MovieSearchService` search/import orchestration and compatible `search_movies` wrapper.
- `engine/imports/`: constants, normalized titles, external identity rules, and imported-card validation; public compatibility exports in `__init__.py` include shared QID validation and legacy TMDB support.
- `engine/wikidata/`: transport, paginated/batched entities, parsing, validation, classification, movie mapping, and search; `WikidataClient` is the public facade over `EntityClassifier`, `MovieMapper`, and `WikidataSearch`.
- `engine/constants.py`: shared URLs, collection, catalog path, limits, dimensions, and timeout.
- `engine/embeddings/`: client, cache, pinned specification, text preparation, and validation; public exports in `__init__.py`.
- `engine/stores/`: standalone `SemanticMovieStore` and `create_store`; semantic-only runtime, with `movies` reserved.
- `evaluation/config/`, `runners/`, `data/`, `results/`: package-relative settings, executable probes/evaluation, frozen inputs, and historical measurements.
- `web/app.py`: application factory, composition, and a fresh `ApplicationLifespan` per startup; `web/config.py` holds Settings and `web/create_admin.py` remains the administrator CLI.
- `web/http/`: route registration, dependencies, security, response cookies, and request-local language selection; `routes/` contains search, auth, account, and admin handlers.
- `web/application/`: services that own transactions, DTOs, scenario errors, credential validation, movie snapshot cleaning, and search/session constants. Services may depend on infrastructure and SQLAlchemy, but not HTTP or presentation.
- `web/infrastructure/`: database resource management, ORM models, SQL repositories, password and token hashing, bounded snapshot caches, and UTC clock. Repositories use caller-owned sessions and do not commit.
- `web/presentation/`: page contexts, localized search/account/admin/auth views, translation messages, and package-relative template/static paths in `pages.py`; no database access.
- `web/templates/index.html`, `web/static/style.css`: responsive English/Russian interface without JavaScript or a build pipeline.
- `requirements.txt`: pinned FastAPI, Uvicorn, qdrant-client, Jinja2, python-multipart, pydantic-settings, Babel, and HTTPX dependencies.
- `engine/tests/`, `web/tests/`: offline unittest engine, loader, and FastAPI TestClient checks with lifespan and async engine tests.
- `movies.json`: 250 movies with stable IDs, Russian metadata and English translations, and manually assigned 10-dimensional vectors.
- `engine/tests/verify.py`: integration checks and mocked collection-schema checks.
- `docker/compose.yaml`: pinned Qdrant image, loopback ports, and persistent Docker volume.
- `README.md`: English-language setup instructions and feature definitions.

Keep the engine and web packages separate. Define the shared root movies.json path in engine relative to package files; do not modify sys.path. Add __init__.py files for unittest discovery. Templates and CSS use the package-relative templates and static directories; there is no build pipeline.

## Build, Test, and Development Commands

Run commands from the repository root:

```sh
python3.15 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt # Install engine, loader, and web dependencies
python3 -m unittest -v                 # Run offline tests
python3 -m uvicorn web.app:create_app --factory --host 127.0.0.1 --port 18000
cp env/.env.example env/.env           # Create local Docker settings once
docker compose --env-file env/.env -f docker/compose.yaml config                  # Validate Compose configuration
docker compose --env-file env/.env -f docker/compose.yaml up -d --build                   # Build and start the Docker stack
curl --fail http://127.0.0.1:6333/readyz # Check readiness
curl --fail http://127.0.0.1:18080/health # Check TEI readiness
python -m engine.load                 # Validate and upsert the dataset
python -m engine.tests.verify          # Verify local Qdrant and TEI
python -m evaluation.runners.probe     # Run sequentially
python -m evaluation.runners.run
```

Docker build files and health scripts live in `docker/`; the build context is the repository root. `env/.env.example` documents host ports and the shared Docker `QDRANT_URL`; local `env/.env` is ignored and excluded from builds. Docker uses `http://qdrant:6333`, while local Python uses the published loopback endpoint.

Wait for readiness before loading or verifying. Install requirements in a virtual environment for the engine, loader, web interface, and all checks. The engine and loader use the official async SDK over REST; the web uses FastAPI. Use `python -m engine.load --url http://127.0.0.1:6333 --data movies.json` to specify the endpoint explicitly.

## Language Policy

Documentation, code, and comments must be in English. Communicate with the user in Russian. User-facing text must support English and Russian localizations. Existing user-facing text and all 250 catalog entries support both languages. Preserve both versions when making changes.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` functions and variables, and `PascalCase` exception classes. Follow the existing single-quoted string style where practical. Use AsyncQdrantClient over REST with a 15-second timeout. Keep validation and in-memory title resolution synchronous; await network operations. Close owned clients in finally or lifespan. Provide English and Russian translations for all new user-facing text. Annotate expected library failures with `errors.annotate_error()` and re-raise the original exception; preserve types, diagnostic attributes, and exception causes. Use domain exceptions with ValueError, LookupError, or RuntimeError categories. At CLI/web boundaries, check `errors.is_expected_error()` and translate with `errors.format_error()`. Use module imports for internal dependencies and qualify members; direct imports are allowed for public re-exports in `__init__.py`. Do not convert unexpected programming errors into service failures. Do not add initial comments or module docstrings that describe a source file's purpose. Preserve shebangs, required service headers, and comments explaining logic. No formatter or linter is configured.

## Testing Guidelines

`engine/tests/verify.py` uses plain assertions and `unittest.mock.patch`; no coverage threshold is configured. It runs only through explicit module invocation, outside offline unittest discovery. Run it without Python’s `-O` flag, which disables assertions. Extend it for changed behavior, including ranking accuracy, source-ID exclusion, unknown IDs, and schema rejection before writes. Verify repeated loads retain exactly 250 records.

## Commit & Pull Request Guidelines

Git history is unavailable in this checkout, so no existing commit convention can be established. Use concise, imperative subjects such as `Validate movie vector dimensions`. Pull requests should explain the behavior change, list verification commands and results, and update the README when usage changes.

## Data & Configuration Safety

Preserve stable movie IDs and the documented feature order. Vectors must contain 10 finite values in `[0, 1]` and be nonzero. Keep Qdrant ports bound to loopback. `docker compose --env-file env/.env -f docker/compose.yaml down` preserves data; `docker compose --env-file env/.env -f docker/compose.yaml down -v` deletes the storage volume.

The factory performs no catalog reads or network operations. Read and validate JSON once in lifespan, keep the catalog per application, and restart after catalog changes. Use request-local gettext translators. Use IsolatedAsyncioTestCase and AsyncMock for SDK checks. Use Python 3.15.2.

Web listens on 18000 and TEI on 18080 inside and outside Docker by default. Merge these host ports and `EMBEDDING_URL=http://tei:18080` into existing local env files without overwriting them. Preserve existing collections and historical evaluation measurements. The runtime uses only the semantic store; manual 10-dimensional vectors remain validated catalog data.
