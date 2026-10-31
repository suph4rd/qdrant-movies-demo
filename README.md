# Movie recommendations with Qdrant

A local learning demo with 250 movies, manually assigned vectors, a REST API, an engine, a loader, and a Flask web interface. Requires Docker with Compose and Python 3.9+. The engine and loader use requests (>=2.32,<3) for Qdrant HTTP requests; the web interface also requires Flask 3.1. Install requirements.txt in a virtual environment before running the loader, checks, or web interface.

## Getting started

```sh
cd /path/to/project
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
docker compose config
docker compose up -d
curl --fail http://localhost:6333/readyz
python -m engine.load
```

If `readyz` does not respond yet, retry after a few seconds. Dashboard: http://localhost:6333/dashboard. REST: `127.0.0.1:6333`, gRPC: `127.0.0.1:6334`. Ports are published on loopback only.

The Qdrant v1.20.0 image is pinned by digest in `compose.yaml`. Container: `qdrant-movies`, restart policy: `unless-stopped`. Data lives in the separate Docker volume `qdrant-movies-demo_movies-storage`, mounted at `/qdrant/storage`.

## Web interface

After checking Qdrant readiness and loading the data, run:

```sh
source .venv/bin/activate
python -m flask --app web.app:create_app run --host 127.0.0.1 --port 5000
```

Open http://127.0.0.1:5000. Enter an ID such as `1`, a title such as “The Matrix”, or a unique title fragment. Matching ignores case and leading/trailing whitespace. Multiple matches require a more specific title. Choose 5, 10, 20, or 50 similar movies (default: 5). Recommendations appear below the form with year, genres, description, and cosine similarity. Errors appear below the form. The query and count remain in the URL (`q` and `limit`), including after errors. Form submission redirects to GET, so refreshing only repeats a read.

Set the Qdrant URL with `QDRANT_URL` (default: `http://127.0.0.1:6333`):

```sh
QDRANT_URL=http://127.0.0.1:6333 python -m flask --app web.app:create_app run --host 127.0.0.1 --port 5000
```

Creating the application does not load data: use `python -m engine.load`. The catalog path is relative to the project files, regardless of the working directory.

Structure:

- `engine/i18n.py`: shared English/Russian messages, parameter formatting, and localized movie metadata without Flask.
- `engine/services.py`: validation, title resolution, and `QdrantMovieStore(base_url)` for HTTP requests, collection loading, and recommendations.
- `engine/load.py`: command-line loader with `--url`, `--data`, and `--lang` options.
- `engine/__init__.py`: shared path to the root `movies.json`, resolved relative to package files.
- `web/app.py`: Flask factory, configuration, and store creation in `app.extensions['movie_store']` without network requests; `web/routes.py`: handlers; `web/router.py`: route registration through `register_routes(app)`; `web/templates/` and `web/static/`: interface without JavaScript or a build step.
- `engine/tests/`: engine and loader tests; `web/tests/`: Flask tests.

Console recommendations have been removed; recommendation search is available through the web interface.

## Languages

The web interface supports English and Russian. Language selection uses a supported `lang=en|ru` URL parameter first, then the saved `lang` cookie, then `Accept-Language`, and finally English. The EN/RU links preserve the query and result count. Forms and POST redirects preserve the selected language. Search accepts titles in either language regardless of the interface language; exact matches take precedence over substring matches. Ambiguous matches display titles in the selected language.

The loader defaults to English. Use `python -m engine.load --lang ru` for Russian output, or `python -m engine.load --lang ru --help` for Russian help and argument errors. `--lang en` explicitly selects English.

Both catalog versions are validated before any Qdrant request. Reload normally to add translations to existing payloads; no collection deletion is needed. The web interface displays metadata from the local catalog by result ID, so collections loaded before translations were added also work. IDs, years, vectors, feature order, and ranking are unchanged.

## Data and features

`movies.json` contains stable numeric IDs 1–250, titles, years, genres, Russian descriptions, English metadata in `translations.en`, and vectors. The original 30 movies and their data are preserved; additional movies have IDs 31–250. This is a selection of familiar movies across genres, not a popularity ranking. IDs remain stable across reloads. The 10 features, in order:

1. Science fiction.
2. Action.
3. Drama.
4. Comedy.
5. Romance.
6. Suspense / thriller.
7. Fantasy / magic.
8. Animation.
9. Darkness.
10. Optimism.

Each value ranges from 0 to 1 and represents a subjective feature strength. Vectors are nonzero. These are educational annotations, not model output: descriptions and titles are not converted to embeddings and do not directly participate in similarity search.

`QdrantMovieStore.load(path)` validates all data before calling the API, creates the `movies` collection with one unnamed 10-dimensional vector and the Cosine metric, then upserts with `wait=true`. Reloading updates the same IDs: two loads leave 250 records. An existing 30-movie catalog is expanded by running the loader normally. An incompatible collection causes an error before writes and is never deleted automatically. Unrelated IDs are preserved too; if they increase the count above 250, the command reports this and exits with code 1.

## Recommendations and checks

```sh
python -m engine.load --url http://127.0.0.1:6333 --data movies.json
python -m unittest -v
python -m engine.tests.verify
```

The web interface requests the selected number of nearest movies through the Query Points API with a filter excluding the source ID. Cosine similarity measures vector similarity, not the probability that a user will like a movie. Qdrant normalizes vectors for Cosine; JSON retains the original values.

The engine supports `services.search(store, query, catalog, limit=5)` and `store.recommend(movie_id, limit=5)`, where `store` is a `QdrantMovieStore` instance and `limit` is an integer from 1 to 249. Invalid counts raise `DemoError` before contacting Qdrant. The web interface accepts only the four listed counts; links without `limit` return five recommendations.

`engine/tests/verify.py` checks 250 records, 5/10/20/50 results for three movies, source-ID exclusion, and agreement with independently calculated cosine scores from JSON. It loads the catalog twice and checks that exactly 250 records remain, verifies translated payloads and legacy payload display in both languages, checks unknown IDs through the API, and tests incompatible schemas through mocked responses without changing the collection.

Persistence check:

```sh
docker compose restart
curl --fail http://localhost:6333/readyz
python -m engine.tests.verify
```

Wait for readiness before verification if necessary.

Stop: `docker compose stop`. Remove the container while keeping data: `docker compose down`. `docker compose down -v` also deletes the volume and all data.

Official documentation: [Docker installation](https://qdrant.tech/documentation/installation/), [Query Points API](https://api.qdrant.tech/api-reference/search/query-points).

Offline tests (`python -m unittest -v`) cover the engine, loader, and Flask test client with mocks, without a running Qdrant. Integration verification is excluded from offline test discovery. For an explicit loader check, run `python -m engine.load` twice, then `python -m engine.tests.verify`: the collection must contain exactly 250 records.

### Maintaining translations

The web uses Flask-Babel; the engine and loader use Python gettext without
depending on Flask. Both read the shared catalog in engine/translations.
English source messages are the fallback; Russian translations live in
ru/LC_MESSAGES/messages.po. Compiled messages.mo files are committed so normal
startup needs no translation build step.

Run these commands in the virtual environment after changing messages:

```sh
pybabel extract -F babel.cfg -k N_ -o engine/translations/messages.pot engine web
pybabel update -i engine/translations/messages.pot -d engine/translations
# Review translations and remove fuzzy flags only after checking them.
pybabel compile -d engine/translations
python -m unittest -v
```

For a new language, use pybabel init instead of update and add the language to
the supported languages. Movie metadata translations remain in movies.json.
