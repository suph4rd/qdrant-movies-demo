# Repository Guidelines

## Project Structure & Module Organization

This is a local movie-recommendation demo using Python 3.9+, Flask 3.1 for the web interface, requests for HTTP calls in the engine and loader, and Qdrant’s REST API.

- `engine/load.py`: loader arguments (`--url`, `--data`) and Russian console output; no console recommendations.
- `engine/services.py`: dataset validation, title/ID resolution, collection loading, and similarity queries; no stdout or Flask dependency.
- `web/app.py`: Flask application factory and GET/POST routes.
- `web/templates/index.html`, `web/static/style.css`: responsive Russian interface without JavaScript or a build pipeline.
- `requirements.txt`: Flask and requests dependencies.
- `engine/tests/`, `web/tests/`: offline unittest engine, loader, and Flask client checks.
- `movies.json`: 30 movies with stable IDs, Russian metadata, and manually assigned 10-dimensional vectors.
- `engine/tests/verify.py`: integration checks and mocked collection-schema checks.
- `compose.yaml`: pinned Qdrant image, loopback ports, and persistent Docker volume.
- `README.md`: Russian-language setup instructions and feature definitions.

Keep the engine and web packages separate. Define the shared root movies.json path in engine relative to package files; do not modify sys.path. Add __init__.py files for unittest discovery. Templates and CSS use the standard Flask directories; there is no build pipeline.

## Build, Test, and Development Commands

Run commands from the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt # Install engine, loader, and web dependencies
python3 -m unittest -v                 # Run offline tests
python3 -m flask --app web.app:create_app run --host 127.0.0.1 --port 5000
docker compose config                  # Validate Compose configuration
docker compose up -d                   # Start Qdrant
curl --fail http://localhost:6333/readyz # Check readiness
python -m engine.load                 # Validate and upsert the dataset
python -m engine.tests.verify          # Run verification against local Qdrant
```

Wait for readiness before loading or verifying. Install requirements in a virtual environment for the engine, loader, web interface, and all checks. The engine and loader require requests; the web interface also requires Flask. Use `python -m engine.load --url http://127.0.0.1:6333 --data movies.json` to specify the endpoint explicitly.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` functions and variables, and `PascalCase` exception classes. Follow the existing single-quoted string style where practical. Use requests for HTTP calls instead of urllib. The engine and loader depend on requests; Flask is the web dependency. Preserve Russian loader messages. Report expected failures through `DemoError`. No formatter or linter is configured.

## Testing Guidelines

`engine/tests/verify.py` uses plain assertions and `unittest.mock.patch`; no coverage threshold is configured. It runs only through explicit module invocation, outside offline unittest discovery. Run it without Python’s `-O` flag, which disables assertions. Extend it for changed behavior, including ranking accuracy, source-ID exclusion, unknown IDs, and schema rejection before writes. Verify repeated loads retain exactly 30 records.

## Commit & Pull Request Guidelines

Git history is unavailable in this checkout, so no existing commit convention can be established. Use concise, imperative subjects such as `Validate movie vector dimensions`. Pull requests should explain the behavior change, list verification commands and results, and update the README when usage changes.

## Data & Configuration Safety

Preserve stable movie IDs and the documented feature order. Vectors must contain 10 finite values in `[0, 1]` and be nonzero. Keep Qdrant ports bound to loopback. `docker compose down` preserves data; `docker compose down -v` deletes the storage volume.
