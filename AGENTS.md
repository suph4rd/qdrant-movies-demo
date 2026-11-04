# Repository Guidelines

## Project Structure & Module Organization

This is a local movie-recommendation demo using Python 3.15.2, FastAPI for the web interface, AsyncQdrantClient for async REST calls in the engine and loader, and Qdrant’s REST API.

- `engine/parser.py`: localized CLI argument parsing for `--url`, `--data`, and `--lang`.
- `engine/load.py`: loader arguments (`--url`, `--data`, `--lang`) and localized English/Russian console output; no console recommendations.
- `engine/i18n.py`: shared message keys and gettext catalogs without web dependencies.
- `engine/errors.py`: localized `DemoError`; `engine/validators.py`: catalog, metadata, ID, and limit validation.
- `engine/catalog.py`: synchronous JSON reading and title/ID resolution; `engine/services.py`: the async search scenario.
- `engine/store.py`: `QdrantMovieStore` for async REST SDK calls, schema checks, loading, recommendations, and client ownership.
- `web/app.py`: FastAPI application factory, Settings, and lifespan; web/router.py defines APIRouter routes.
- `web/i18n.py`: request language selection and response cookies/headers; `web/services.py`: request-scoped `IndexService` preparation, localization, context, and rendering.
- `web/routes.py`: thin GET and POST handlers; `web/router.py`: route registration.
- `web/templates/index.html`, `web/static/style.css`: responsive English/Russian interface without JavaScript or a build pipeline.
- `requirements.txt`: pinned FastAPI, Uvicorn, qdrant-client, Jinja2, python-multipart, pydantic-settings, Babel, and HTTPX dependencies.
- `engine/tests/`, `web/tests/`: offline unittest engine, loader, and FastAPI TestClient checks with lifespan and async engine tests.
- `movies.json`: 250 movies with stable IDs, Russian metadata and English translations, and manually assigned 10-dimensional vectors.
- `engine/tests/verify.py`: integration checks and mocked collection-schema checks.
- `compose.yaml`: pinned Qdrant image, loopback ports, and persistent Docker volume.
- `README.md`: English-language setup instructions and feature definitions.

Keep the engine and web packages separate. Define the shared root movies.json path in engine relative to package files; do not modify sys.path. Add __init__.py files for unittest discovery. Templates and CSS use the package-relative templates and static directories; there is no build pipeline.

## Build, Test, and Development Commands

Run commands from the repository root:

```sh
python3.15 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt # Install engine, loader, and web dependencies
python3 -m unittest -v                 # Run offline tests
python3 -m uvicorn web.app:create_app --factory --host 127.0.0.1 --port 5000
docker compose config                  # Validate Compose configuration
docker compose up -d                   # Start Qdrant
curl --fail http://localhost:6333/readyz # Check readiness
python -m engine.load                 # Validate and upsert the dataset
python -m engine.tests.verify          # Run verification against local Qdrant
```

Wait for readiness before loading or verifying. Install requirements in a virtual environment for the engine, loader, web interface, and all checks. The engine and loader use the official async SDK over REST; the web uses FastAPI. Use `python -m engine.load --url http://127.0.0.1:6333 --data movies.json` to specify the endpoint explicitly.

## Language Policy

Documentation, code, and comments must be in English. Communicate with the user in Russian. User-facing text must support English and Russian localizations. Existing user-facing text and all 250 catalog entries support both languages. Preserve both versions when making changes.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` functions and variables, and `PascalCase` exception classes. Follow the existing single-quoted string style where practical. Use AsyncQdrantClient over REST with a 15-second timeout. Keep validation and in-memory title resolution synchronous; await network operations. Close owned clients in finally or lifespan. Provide English and Russian translations for all new user-facing text. Report expected failures through `DemoError`. No formatter or linter is configured.

## Testing Guidelines

`engine/tests/verify.py` uses plain assertions and `unittest.mock.patch`; no coverage threshold is configured. It runs only through explicit module invocation, outside offline unittest discovery. Run it without Python’s `-O` flag, which disables assertions. Extend it for changed behavior, including ranking accuracy, source-ID exclusion, unknown IDs, and schema rejection before writes. Verify repeated loads retain exactly 250 records.

## Commit & Pull Request Guidelines

Git history is unavailable in this checkout, so no existing commit convention can be established. Use concise, imperative subjects such as `Validate movie vector dimensions`. Pull requests should explain the behavior change, list verification commands and results, and update the README when usage changes.

## Data & Configuration Safety

Preserve stable movie IDs and the documented feature order. Vectors must contain 10 finite values in `[0, 1]` and be nonzero. Keep Qdrant ports bound to loopback. `docker compose down` preserves data; `docker compose down -v` deletes the storage volume.

The factory performs no catalog reads or network operations. Read and validate JSON once in lifespan, keep the catalog per application, and restart after catalog changes. Use request-local gettext translators. Use IsolatedAsyncioTestCase and AsyncMock for SDK checks. Use Python 3.15.2.
