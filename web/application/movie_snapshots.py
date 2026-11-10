import copy


SNAPSHOT_FIELDS = ('id', 'title', 'year', 'genres', 'description', 'translations',
                   'source', 'wikidata_id', 'tmdb_id', 'original_title',
                   'description_language', 'alternative_titles')


def clean_snapshot(movie):
    return copy.deepcopy({key: movie[key] for key in SNAPSHOT_FIELDS if key in movie})


