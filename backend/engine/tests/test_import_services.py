import unittest
from unittest.mock import AsyncMock

from backend.engine import errors
from backend.engine import imports
from backend.engine import services


def movie(i, title='Solaris', year=1972):
    return {'id': i, 'title': title, 'year': year,
            'translations': {'en': {'title': title}}}


class ImportSearchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = AsyncMock()
        self.store.find_movies.return_value = []
        self.store.recommend.return_value = {'source': {}, 'recommendations': []}
        self.wikidata = AsyncMock()

    async def test_local_all_versions_excluded_and_no_external_calls(self):
        catalog = [movie(1), movie(2, year=2002)]
        result = await services.search_movies(self.store, '  SOLARIS ', catalog,
                                             wikidata=self.wikidata, allow_import=True)
        self.assertEqual(len(result['groups']), 2)
        for call in self.store.recommend.call_args_list:
            self.assertEqual(call.kwargs['exclude_ids'], [1, 2])
        self.wikidata.search.assert_not_awaited()
        self.store.find_movies.assert_not_awaited()

    async def test_year_unicode_and_stored_match(self):
        self.assertEqual(imports.normalize_title(' Ｓｏｌａｒｉｓ  '), 'solaris')
        result = await services.search_movies(self.store, 'Solaris (2002)',
                                             [movie(1), movie(2, year=2002)])
        self.assertEqual([g['source']['id'] for g in result['groups']], [2])
        self.store.find_movies.return_value = [movie(30)]
        result = await services.search_movies(self.store, 'Solaris', [], wikidata=self.wikidata)
        self.assertEqual(result['groups'][0]['source']['id'], 30)
        self.wikidata.search.assert_not_awaited()

    async def test_saved_typo_does_not_import_again(self):
        saved = movie(30, 'Interstellar', 2014)
        self.store.find_movies.return_value = imports.select_similar([saved], 'Interstelar', 2014)
        result = await services.search_movies(self.store, 'Interstelar (2014)', [],
                                             wikidata=self.wikidata, allow_import=True)
        self.assertEqual(result['groups'][0]['source']['id'], 30)
        self.assertEqual(result['messages'][0]['key'], 'wikidata_corrected')
        self.wikidata.search.assert_not_awaited()
        self.store.import_movie.assert_not_awaited()

    async def test_numeric_is_internal_id(self):
        await services.search_movies(self.store, '1917', [movie(1, '1917')],
                                    wikidata=self.wikidata, allow_import=True)
        self.store.recommend.assert_awaited_once_with(1917, limit=5)
        self.store.find_movies.assert_not_awaited()
        self.wikidata.search.assert_not_awaited()

    async def test_import_partial_failure_preserves_success(self):
        films = [movie(100), movie(101)]
        self.wikidata.search.return_value = {'movies': films, 'messages': []}
        self.store.import_movie.side_effect = [
            {'movie': films[0], 'created': True}, errors.InputValidationError('wikidata_invalid')]
        result = await services.search_movies(self.store, 'Solaris', [], wikidata=self.wikidata, allow_import=True)
        self.assertEqual([g['source']['id'] for g in result['groups']], [100])
        self.assertEqual([m['key'] for m in result['messages']], ['import_added', 'import_failed'])

    async def test_no_import_on_read_and_missing_client(self):
        with self.assertRaises(errors.MovieNotFoundError) as caught:
            await services.search_movies(self.store, 'Absent', [], wikidata=self.wikidata)
        self.assertEqual(caught.exception._localization[0], 'search_saved_only')
        self.wikidata.search.assert_not_awaited()
        with self.assertRaises(errors.MovieNotFoundError) as caught:
            await services.search_movies(self.store, 'Absent', [], allow_import=True)
        self.assertEqual(caught.exception._localization[0], 'wikidata_unavailable')

    async def test_empty_and_unexpected_failure(self):
        self.wikidata.search.return_value = {'movies': [], 'messages': []}
        with self.assertRaises(errors.MovieNotFoundError) as caught:
            await services.search_movies(self.store, 'Absent', [], wikidata=self.wikidata, allow_import=True)
        self.assertEqual(caught.exception._localization[0], 'wikidata_not_found')
        self.wikidata.search.return_value = {'movies': [movie(100)], 'messages': []}
        self.store.import_movie.side_effect = TypeError('bug')
        with self.assertRaises(TypeError):
            await services.search_movies(self.store, 'Absent', [], wikidata=self.wikidata, allow_import=True)

    async def test_service_saved_match_precedes_partial_catalog_and_import(self):
        saved = movie(30, 'Solaris')
        self.store.find_movies.return_value = [saved]
        service = services.MovieSearchService(self.store, [movie(1, 'Solaris restored')], self.wikidata)
        result = await service.search('Solaris', allow_import=True)
        self.assertEqual([g['source']['id'] for g in result['groups']], [30])
        self.wikidata.search.assert_not_awaited()

    async def test_service_partial_catalog_precedes_import(self):
        service = services.MovieSearchService(self.store, [movie(1, 'Solaris restored')], self.wikidata)
        result = await service.search('Solaris', allow_import=True)
        self.assertEqual([g['source']['id'] for g in result['groups']], [1])
        self.wikidata.search.assert_not_awaited()

    async def test_service_deduplicates_sources_and_preserves_recommendation_failure(self):
        films = [movie(30), movie(30), movie(31)]
        self.store.find_movies.return_value = films
        failure = errors.MovieNotFoundError('unknown_id', id=30)
        self.store.recommend.side_effect = [failure, {'source': {}, 'recommendations': []}]
        result = await services.MovieSearchService(self.store, []).search('Solaris')
        self.assertEqual([g['source']['id'] for g in result['groups']], [31])
        self.assertIs(result['messages'][0]['params']['error'], failure)
        for call in self.store.recommend.call_args_list:
            self.assertEqual(call.kwargs['exclude_ids'], [30, 31])

    async def test_service_recommendation_programming_error_escapes(self):
        self.store.find_movies.return_value = [movie(30)]
        failure = TypeError('bug')
        self.store.recommend.side_effect = failure
        with self.assertRaises(TypeError) as caught:
            await services.MovieSearchService(self.store, []).search('Solaris')
        self.assertIs(caught.exception, failure)
