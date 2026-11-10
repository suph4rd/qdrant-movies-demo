import copy
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from backend.engine import errors
from backend.engine import imports
from backend.engine import services
from backend.engine import wikidata


def statement(value, **changes):
    return {'rank': 'normal', 'mainsnak': {'snaktype': 'value', 'datavalue': {'value': value}}, **changes}


def item(qid):
    return statement({'id': qid})


def entity(qid='Q42', **changes):
    return {'id': qid, 'type': 'item',
            'labels': {'en': {'value': 'Solaris'}, 'ru': {'value': 'Солярис'}},
            'descriptions': {'en': {'value': '1972 science fiction film'}, 'ru': {'value': 'Фильм 1972 года'}},
            'aliases': {'en': [{'value': 'Ocean Planet'}]},
            'claims': {'P31': [item('Q11424')], 'P136': [item('Q100')],
                       'P577': [statement({'time': '+1972-00-00T00:00:00Z', 'precision': 9})],
                       'P1476': [statement({'text': 'Солярис', 'language': 'ru'})],
                       'P4947': [statement('593')]}, **changes}


def genre(qid='Q100', parents=None):
    return {'id': qid, 'type': 'item', 'labels': {'en': {'value': 'Science Fiction'},
             'ru': {'value': 'Фантастика'}}, 'claims': {'P279': [item(p) for p in parents or []]}}


class WikidataTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.requests = []
        self.cards = {'Q42': entity(), 'Q43': entity('Q43'), 'Q100': genre()}
        self.pages = {('en', None): {'search': [{'id': 'Q42'}]},
                      ('ru', None): {'search': [{'id': 'Q42'}]}}
        self.failure = None
        def handle(request):
            self.requests.append(request)
            if self.failure is not None:
                if isinstance(self.failure, Exception):
                    raise self.failure
                return self.failure
            params = request.url.params
            if params['action'] == 'query':
                value = {'query': {'pages': {}}}
            elif params['action'] == 'wbsearchentities':
                offset = params.get('continue')
                value = self.pages[(params['language'], int(offset) if offset else None)]
            else:
                value = {'entities': {qid: self.cards[qid] for qid in params['ids'].split('|')}}
            if isinstance(value, httpx.Response):
                return value
            return httpx.Response(200, json=value)
        self.http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        self.addAsyncCleanup(self.http.aclose)
        self.client = wikidata.WikidataClient(client=self.http)

    async def test_alias_unicode_languages_and_no_key(self):
        result = await self.client.search(' OCEAN　Planet (1972) ')
        movie = result['movies'][0]
        self.assertEqual(movie['id'], imports.WIKIDATA_ID_BASE + 42)
        self.assertEqual(movie['wikidata_id'], 'Q42')
        self.assertEqual(movie['tmdb_id'], 593)
        self.assertEqual(movie['description_kind'], 'short')
        self.assertEqual(movie['title'], 'Солярис')
        self.assertEqual(movie['translations']['en']['genres'], ['Science Fiction'])
        for request in self.requests:
            self.assertEqual(str(request.url).split('?')[0], wikidata.API_URL)
            self.assertIn('QdrantMoviesDemo', request.headers['user-agent'])
            self.assertNotIn('authorization', request.headers)
            self.assertNotIn('api_key', request.url.params)
        self.assertTrue(any(r.url.params.get('languages') == 'en|ru|mul' for r in self.requests))

    async def test_namesake_without_release_date_is_not_an_incomplete_movie(self):
        self.cards['Q42']['claims'] = {}
        self.assertEqual(await self.client.search('Solaris (1972)'),
                         {'movies': [], 'messages': []})

    async def test_all_pages_and_year(self):
        self.pages[('en', None)]['search-continue'] = 50
        self.pages[('en', None)]['search'].append({'id': 'Q43'})
        self.cards['Q43']['claims']['P577'] = [statement({'time': '+2002-12-01T00:00:00Z', 'precision': 11})]
        self.assertEqual([m['wikidata_id'] for m in (await self.client.search('Solaris'))['movies']], ['Q42', 'Q43'])
        self.assertEqual([m['wikidata_id'] for m in (await self.client.search('Solaris (1972)'))['movies']], ['Q42'])
        self.assertEqual((await self.client.search('Sola'))['movies'], [])

    async def test_mul_label_russian_fallback_and_original_fallback(self):
        self.cards['Q42']['labels'] = {'mul': {'value': 'Solaris'}}
        self.cards['Q42']['descriptions'].pop('ru')
        self.cards['Q42']['claims'].pop('P1476')
        self.cards['Q100']['labels'].pop('ru')
        movie = (await self.client.search('Solaris'))['movies'][0]
        self.assertEqual(movie['title'], 'Solaris')
        self.assertEqual(movie['original_title'], 'Solaris')
        self.assertEqual(movie['description_language'], 'en')
        self.assertEqual(movie['genres'], ['Science Fiction'])

    async def test_subclasses_not_series_and_adult(self):
        self.cards['Q42']['claims']['P31'] = [item('Q200')]
        self.cards['Q200'] = genre('Q200', ['Q11424'])
        self.assertEqual(len((await self.client.search('Solaris'))['movies']), 1)
        self.cards['Q200']['claims']['P279'].append(item('Q5398426'))
        self.assertEqual((await self.client.search('Solaris'))['movies'], [])
        self.cards['Q42']['claims']['P31'] = [item('Q11424')]
        self.cards['Q100']['claims']['P279'] = [item('Q185529')]
        self.assertEqual((await self.client.search('Solaris'))['movies'], [])
        self.cards['Q42']['claims']['P31'] = []
        self.assertEqual((await self.client.search('Solaris'))['movies'], [])

    async def test_invalid_cards_skipped_and_valid_survives(self):
        self.pages[('en', None)] = {'search': [{'id': 'Q42'}, {'id': 'Q43'}]}
        original = copy.deepcopy(self.cards['Q42'])
        changes = [lambda e: e['descriptions'].pop('en'),
                   lambda e: e['claims'].update(P577=[statement({'time': '+1972-02-31T00:00:00Z', 'precision': 11})]),
                   lambda e: e['claims'].update(P136=[]),
                   lambda e: e['claims'].update(P4947=[statement('true')])]
        for change in changes:
            self.cards['Q42'] = copy.deepcopy(original)
            change(self.cards['Q42'])
            result = await self.client.search('Solaris')
            self.assertEqual([m['wikidata_id'] for m in result['movies']], ['Q43'])
            self.assertIn({'key': 'wikidata_skipped', 'params': {'id': 'Q42'}}, result['messages'])

    async def test_candidates_are_bounded_without_pagination(self):
        self.pages[('en', None)]['search-continue'] = 50
        result = await self.client.search('Solaris')
        self.assertEqual(len(result['movies']), 1)
        self.assertFalse(any('continue' in r.url.params for r in self.requests))

    async def test_http_json_api_errors_and_programming_errors(self):
        for status, key in ((429, 'wikidata_rate_limit'), (503, 'wikidata_unavailable'), (403, 'wikidata_unavailable')):
            self.failure = httpx.Response(status)
            with self.assertRaises(httpx.HTTPStatusError) as caught:
                await self.client.search('Solaris')
            self.assertEqual(caught.exception.response.status_code, status)
            self.assertEqual(caught.exception._localization[0], key)
        failure = httpx.ConnectError('offline')
        self.failure = failure
        with self.assertRaises(httpx.ConnectError) as caught:
            await self.client.search('Solaris')
        self.assertIs(caught.exception, failure)
        self.assertEqual(failure._localization[0], 'wikidata_unavailable')
        self.failure = httpx.Response(200, content='invalid')
        with self.assertRaises(json.JSONDecodeError):
            await self.client.search('Solaris')
        self.failure = httpx.Response(200, json={'error': {'code': 'maxlag'}})
        with self.assertRaises(errors.IndexStateError) as caught:
            await self.client.search('Solaris')
        self.assertEqual(caught.exception._localization[0], 'wikidata_rate_limit')
        self.failure = TypeError('bug')
        with self.assertRaisesRegex(TypeError, 'bug'):
            await self.client.search('Solaris')

    async def test_partial_details_survive_service_failure(self):
        self.pages[('en', None)] = {'search': [{'id': 'Q42'}, {'id': 'Q43'}]}
        self.cards['Q43'] = {'id': 'Q43', 'type': 'item', 'missing': ''}
        result = await self.client.search('Solaris')
        self.assertEqual([m['wikidata_id'] for m in result['movies']], ['Q42'])
        self.assertIn({'key': 'wikidata_invalid', 'params': {}}, result['messages'])

    async def test_classification_cycles_are_bounded(self):
        self.cards['Q42']['claims']['P31'] = [item('Q200')]
        self.cards['Q200'] = genre('Q200', ['Q201'])
        self.cards['Q201'] = genre('Q201', ['Q200'])
        self.assertEqual((await self.client.search('Solaris'))['movies'], [])
        self.assertLess(len(self.requests), 10)

    async def test_title_and_year_filter_before_classification_or_genres(self):
        self.cards['Q42']['labels']['en']['value'] = 'Another movie'
        with patch.object(self.client, 'classification', new_callable=AsyncMock) as classify:
            self.assertEqual(await self.client.search('Solaris'), {'movies': [], 'messages': []})
            classify.assert_not_awaited()
        self.cards['Q42']['labels']['en']['value'] = 'Solaris'
        self.requests.clear()
        with patch.object(self.client, 'classification', new_callable=AsyncMock) as classify:
            self.assertEqual(await self.client.search('Solaris (2002)'), {'movies': [], 'messages': []})
            classify.assert_not_awaited()
        self.assertFalse(any(r.url.params.get('ids') == 'Q100' for r in self.requests))

    async def test_deep_nonfilm_and_unresolved_adult_ancestry_skip_cleanly(self):
        self.cards['Q210'] = genre('Q210')
        for i in range(200, 210):
            self.cards['Q' + str(i)] = genre('Q' + str(i), ['Q' + str(i + 1)])
        self.cards['Q42']['claims']['P31'] = [item('Q200')]
        self.assertEqual(await self.client.search('Solaris'), {'movies': [], 'messages': []})
        self.cards['Q42']['claims']['P31'] = [item('Q11424')]
        self.cards['Q42']['claims']['P136'] = [item('Q200')]
        self.assertEqual(len((await self.client.search('Solaris'))['movies']), 1)
        self.cards['Q42']['claims']['P31'] = [item('Q11424'), item('Q200')]
        self.cards['Q42']['claims']['P136'] = [item('Q100')]
        self.assertEqual(len((await self.client.search('Solaris'))['movies']), 1)

    async def test_detail_network_failure_keeps_earlier_movie(self):
        self.pages[('en', None)] = {'search': [{'id': 'Q42'}, {'id': 'Q43'}]}
        original = self.client.movie
        failure = httpx.ReadTimeout('timeout')
        async def movie(qid, cache):
            if qid == 'Q43':
                errors.annotate_error(failure, 'wikidata_unavailable')
                raise failure
            return await original(qid, cache)
        with patch.object(self.client, 'movie', side_effect=movie):
            result = await self.client.search('Solaris')
        self.assertEqual([m['wikidata_id'] for m in result['movies']], ['Q42'])
        self.assertIn({'key': 'wikidata_unavailable', 'params': {}}, result['messages'])

    def test_year_precision_and_deprecated_claims(self):
        card = entity()
        card['claims']['P577'] = [
            statement({'time': '+1900-01-01T00:00:00Z', 'precision': 11}, rank='deprecated'),
            statement({'time': '+1972-03-00T00:00:00Z', 'precision': 10}),
            statement({'time': '+1973-01-01T00:00:00Z', 'precision': 11})]
        self.assertEqual(self.client.year(card), 1972)

    async def test_entity_batches_deduplicate_and_reuse_only_search_cache(self):
        qids = ['Q' + str(number) for number in range(300, 351)]
        self.cards.update({qid: genre(qid) for qid in qids})
        cache = {}
        result = await self.client.entities(qids + [qids[0]], cache)
        self.assertEqual([card['id'] for card in result], qids + [qids[0]])
        self.assertEqual([len(request.url.params['ids'].split('|'))
                          for request in self.requests], [50, 1])
        await self.client.entities(qids, cache)
        self.assertEqual(len(self.requests), 2)
        self.requests.clear()
        await self.client.search('Solaris')
        first_count = len(self.requests)
        await self.client.search('Solaris')
        self.assertEqual(len(self.requests), first_count * 2)

    async def test_invalid_qids_never_reach_transport(self):
        for qid in ('Q0', 'Q01', 'q42', 'Q1000000000000', None, 42):
            with self.subTest(qid=qid):
                self.assertFalse(wikidata.valid_qid(qid))
                with self.assertRaises(errors.InputValidationError):
                    await self.client.movie(qid)
        self.assertEqual(self.requests, [])

    async def test_classification_node_limit_stops_before_fetching(self):
        roots = ['Q' + str(number) for number in range(300, 813)]
        self.assertIsNone(await self.client.classification(roots, {}))
        self.assertEqual(self.requests, [])

    async def test_mimino_real_genre_graph_and_import(self):
        self.cards = json.loads((Path(__file__).parent / 'fixtures' / 'mimino.json').read_text())
        self.pages = {('en', None): {'search': [{'id': 'Q1519753'}]},
                      ('ru', None): {'search': [{'id': 'Q1519753'}]}}
        result = await self.client.search('Мимино')
        self.assertEqual([m['wikidata_id'] for m in result['movies']], ['Q1519753'])
        self.assertEqual(result['movies'][0]['year'], 1977)
        store = AsyncMock()
        store.find_movies.return_value = []
        movie = result['movies'][0]
        store.import_movie.return_value = {'movie': movie, 'created': True}
        store.recommend.return_value = {'source': movie, 'recommendations': []}
        service = services.MovieSearchService(store, [], self.client)
        imported = await service.search('Мимино', allow_import=True)
        self.assertEqual(imported['groups'][0]['source']['wikidata_id'], 'Q1519753')
        store.import_movie.assert_awaited_once()
        store.find_movies.return_value = [movie]
        await service.search('«МИМИНО»', allow_import=True)
        store.import_movie.assert_awaited_once()

    async def test_wikidata_language_failure_keeps_other_source(self):
        original = self.client.request
        async def request(**params):
            if params.get('action') == 'wbsearchentities' and params.get('language') == 'en':
                failure = httpx.ReadTimeout('offline')
                errors.annotate_error(failure, 'wikidata_unavailable')
                raise failure
            return await original(**params)
        with patch.object(self.client, 'request', side_effect=request):
            result = await self.client.search('Solaris')
        self.assertEqual(len(result['movies']), 1)
        self.assertIn({'key': 'wikidata_unavailable', 'params': {}}, result['messages'])

    async def test_wikipedia_pageprops_transport_and_source_failure(self):
        def handle(request):
            if request.url.host == 'en.wikipedia.org':
                return httpx.Response(503)
            return httpx.Response(200, json={'query': {'pages': {
                '1': {'pageprops': {'wikibase_item': 'Q42'}},
                '2': {'pageprops': {'wikibase_item': 'Q42'}}, '3': {}}}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            client = wikidata.WikidataClient(http)
            qids, failures = await client.wikipedia_candidates('Solaris')
        self.assertEqual(qids, ['Q42'])
        self.assertEqual(failures[0]._localization[0], 'wikidata_unavailable')

    async def test_typo_confidence_and_short_titles(self):
        self.cards['Q42']['labels']['en']['value'] = 'Interstellar'
        result = await self.client.search('Interstelar')
        self.assertEqual([m['wikidata_id'] for m in result['movies']], ['Q42'])
        self.assertEqual(result['messages'][0]['key'], 'wikidata_corrected')
        self.cards['Q43']['labels']['en']['value'] = 'Interstellaa'
        self.pages[('en', None)]['search'].append({'id': 'Q43'})
        self.assertEqual((await self.client.search('Interstellab'))['movies'], [])
        self.assertEqual(imports.similarity('Up', 'Upp'), 0)
        self.assertEqual(imports.select_similar([{'title': 'Interstellar', 'year': 2014}],
                                                'Interstelar', 2000), [])
        self.assertEqual(imports.normalize_title('«Ёлки» — 2!'), 'елки 2')

    async def test_runner_up_below_threshold_still_blocks_correction(self):
        self.cards['Q42']['labels'] = {'en': {'value': 'abcdefghijklmnopqrsxy'}}
        self.cards['Q42']['aliases'] = {}
        self.cards['Q42']['claims'].pop('P1476')
        self.cards['Q43']['labels'] = {'en': {'value': 'abcdefghijklmnopqrxyz'}}
        self.cards['Q43']['aliases'] = {}
        self.cards['Q43']['claims'].pop('P1476')
        self.pages[('en', None)]['search'].append({'id': 'Q43'})
        result = await self.client.search('abcdefghijklmnopqrstu')
        self.assertEqual(result['movies'], [])

    async def test_deep_adult_ancestry_is_rejected(self):
        for number in range(200, 212):
            self.cards['Q' + str(number)] = genre('Q' + str(number), ['Q' + str(number + 1)])
        self.cards['Q212'] = genre('Q212', ['Q185529', 'Q200'])
        self.cards['Q42']['claims']['P136'] = [item('Q200')]
        self.assertEqual((await self.client.search('Solaris'))['movies'], [])

    async def test_wikipedia_fallback_deduplicates_and_validates(self):
        self.pages = {('en', None): {'search': []}, ('ru', None): {'search': []}}
        with patch.object(self.client, 'wikipedia_candidates', new_callable=AsyncMock,
                          return_value=(['Q42', 'Q42'], [])) as fallback:
            result = await self.client.search('Solaris')
            self.assertEqual(len(result['movies']), 1)
            fallback.assert_awaited_once()
        self.pages[('en', None)] = {'search': [{'id': 'Q42'}]}
        with patch.object(self.client, 'wikipedia_candidates', new_callable=AsyncMock) as fallback:
            await self.client.search('Solaris')
            fallback.assert_not_awaited()

    async def test_incomplete_graph_is_reported(self):
        self.cards['Q42']['claims']['P136'] = [item('Q' + str(i)) for i in range(300, 813)]
        result = await self.client.search('Solaris')
        self.assertEqual(result['movies'], [])
        self.assertIn({'key': 'wikidata_incomplete', 'params': {}}, result['messages'])

    async def test_close_ownership(self):
        await self.client.close()
        self.assertFalse(self.http.is_closed)
        owned = AsyncMock()
        with patch('backend.engine.wikidata.httpx.AsyncClient', return_value=owned):
            client = wikidata.WikidataClient()
        await client.close()
        owned.aclose.assert_awaited_once()


class ImportQueryTests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(imports.parse_query('Solaris (1972)'), ('Solaris', 1972))
        self.assertEqual(imports.normalize_title(' ＳＯＬＡＲＩＳ　 '), 'solaris')
        with self.assertRaises(errors.InputValidationError):
            imports.parse_query(' ')
