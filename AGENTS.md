# Repository Guidelines

## Project Structure & Module Organization

This is a local movie-recommendation demo using Python 3.9+, the standard library, and Qdrant’s REST API.

- `movies.py`: CLI, dataset validation, collection loading, and similarity queries.
- `movies.json`: 30 movies with stable IDs, Russian metadata, and manually assigned 10-dimensional vectors.
- `verify.py`: integration checks and mocked collection-schema checks.
- `compose.yaml`: pinned Qdrant image, loopback ports, and persistent Docker volume.
- `README.md`: Russian-language setup instructions and feature definitions.

Keep this small, flat structure unless additional modules have a clear purpose. There is no separate asset directory or build pipeline.

## Build, Test, and Development Commands

Run commands from the repository root:

```sh
docker compose config                  # Validate Compose configuration
docker compose up -d                   # Start Qdrant
curl --fail http://localhost:6333/readyz # Check readiness
python3 movies.py load                 # Validate and upsert the dataset
python3 movies.py recommend 1          # Show five similar movies
python3 verify.py                      # Run verification against local Qdrant
```

Wait for readiness before loading or verifying. No Python package installation is required. Use `python3 movies.py --url http://127.0.0.1:6333 recommend 16` to specify the endpoint explicitly.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` functions and variables, and `PascalCase` exception classes. Follow the existing single-quoted string style where practical. Keep dependencies within the standard library and preserve Russian CLI messages. Report expected failures through `DemoError`. No formatter or linter is configured.

## Testing Guidelines

`verify.py` uses plain assertions and `unittest.mock.patch`; no coverage threshold is configured. Run it without Python’s `-O` flag, which disables assertions. Extend it for changed behavior, including ranking accuracy, source-ID exclusion, unknown IDs, and schema rejection before writes. Verify repeated loads retain exactly 30 records.

## Commit & Pull Request Guidelines

Git history is unavailable in this checkout, so no existing commit convention can be established. Use concise, imperative subjects such as `Validate movie vector dimensions`. Pull requests should explain the behavior change, list verification commands and results, and update the README when usage changes.

## Data & Configuration Safety

Preserve stable movie IDs and the documented feature order. Vectors must contain 10 finite values in `[0, 1]` and be nonzero. Keep Qdrant ports bound to loopback. `docker compose down` preserves data; `docker compose down -v` deletes the storage volume.
