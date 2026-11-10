import httpx

from backend.engine.wikidata.client import WikidataClient
from backend.engine.wikidata.classification import EntityClassifier
from backend.engine.wikidata.constants import API_URL, USER_AGENT, FILM, ADULT_TYPES, TELEVISION_SERIES
from backend.engine.wikidata.movies import MovieMapper
from backend.engine.wikidata.parsing import values, item_values, localized, year
from backend.engine.wikidata.search import WikidataSearch
from backend.engine.wikidata.validators import valid_qid, invalid
