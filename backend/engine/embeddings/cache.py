import hashlib
import json
from pathlib import Path
import tempfile

from backend.engine import errors
from backend.engine.embeddings import constants as embedding_constants
from backend.engine.embeddings import spec as embedding_spec
from backend.engine.embeddings import validators as embedding_validators


class EmbeddingCache:
    def __init__(self, directory=embedding_constants.DEFAULT_CACHE_PATH, spec=embedding_spec.SPEC):
        self.directory = Path(directory)
        self.spec = spec

    def key(self, text):
        value = json.dumps({'text': text, 'embedding': self.spec.metadata()},
                           ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(value.encode('utf-8')).hexdigest()

    def get(self, text):
        key = self.key(text)
        try:
            value = json.loads((self.directory / (key + '.json')).read_text(encoding='utf-8'))
            if not isinstance(value, dict) or value.get('key') != key:
                return None
            return embedding_validators.validate_vectors([value.get('vector')], 1, self.spec.dimensions)[0]
        except (OSError, json.JSONDecodeError, UnicodeDecodeError, errors.EmbeddingResponseError):
            # Missing, unreadable, or corrupt entries are regenerated.
            return None

    def put(self, text, vector):
        embedding_validators.validate_vectors([vector], 1, self.spec.dimensions)
        key = self.key(text)
        temporary = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.directory,
                                             suffix='.tmp', delete=False) as output:
                temporary = Path(output.name)
                json.dump({'key': key, 'vector': vector}, output, allow_nan=False)
            temporary.replace(self.directory / (key + '.json'))
        except OSError as exc:
            errors.annotate_error(exc, 'embedding_cache', path=str(self.directory))
            raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
