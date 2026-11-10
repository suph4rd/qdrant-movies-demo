from collections import OrderedDict
import secrets

from backend.engine import imports
from backend.api.application import movie_snapshots


class SnapshotCache(OrderedDict):
    def __init__(self, capacity):
        super().__init__()
        self.capacity = capacity

    def put(self, value):
        token = secrets.token_urlsafe(24)
        self[token] = value
        while len(self) > self.capacity:
            self.popitem(last=False)
        return token


class SearchResults(SnapshotCache):
    def __init__(self):
        super().__init__(128)

    def matching(self, token, params):
        snapshot = self.get(token)
        return snapshot if snapshot and snapshot['params'] == params else None


class MovieCards(SnapshotCache):
    def __init__(self):
        super().__init__(1024)

    def reference(self, catalog, movie):
        original = next((item for item in catalog if item['id'] == movie.get('id')), None)
        if original is None:
            imports.validate_movie(movie)
            original = movie
        return self.put(movie_snapshots.clean_snapshot(original))
