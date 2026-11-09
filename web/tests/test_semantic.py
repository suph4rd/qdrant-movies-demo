from html import escape
from urllib.parse import parse_qs, urlsplit
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from engine import errors
from engine import i18n as engine_i18n
from engine import services
from engine.tests import helpers
from web import app as web_app
from web.tests import test_i18n


class DescriptionWebTests(unittest.TestCase):
    def setUp(self):
        self.app = web_app.create_app()
        self.client = self.enterContext(TestClient(self.app,follow_redirects=False))

    def test_modes_languages_counts_and_navigation(self):
        for lang in ('en','ru'):
            for limit in ('5','10','20','50'):
                query='Космонавт & <test>' if lang == 'ru' else 'Astronaut & <test>'
                result={'source':None,'recommendations':[{'id':4,'score':.9,'payload':{}}]}
                with patch.object(services,'semantic_search',return_value=result) as search, patch.object(services,'search') as movie_search:
                    redirect=self.client.post('/search',data={'mode':'description','query':query,'limit':limit,'lang':lang})
                    self.assertEqual(redirect.status_code,303)
                    search.assert_not_called()
                    params=parse_qs(urlsplit(redirect.headers['location']).query)
                    self.assertEqual(params,{'mode':['description'],'q':[query],'limit':[limit],'lang':[lang]})
                    response=self.client.get(redirect.headers['location'])
                    search.assert_called_once_with(self.app.state.movie_store,query,limit=int(limit))
                    movie_search.assert_not_called()
                html=response.text
                self.assertEqual(response.headers['content-language'],lang)
                self.assertIn(engine_i18n.translate('description_results',lang),html)
                self.assertNotIn(engine_i18n.translate('similar',lang,title=''),html)
                self.assertIn(escape(query),html)
                self.assertIn('<option value="description" selected>',html)
                self.assertIn(f'<option value="{limit}" selected>',html)
                self.assertEqual(html.count('<article>'),1)
                for target,link in test_i18n.LanguageLinks(html).links.items():
                    params=parse_qs(urlsplit(link).query)
                    self.assertEqual(params['mode'],['description'])
                    self.assertEqual(params['q'],[query])
                    self.assertEqual(params['limit'],[limit])
                    self.assertEqual(params['lang'],[target])

    def test_validation_and_model_failure(self):
        for lang in ('en','ru'):
            with patch.object(self.app.state.movie_store.embeddings,'encode_query') as encode:
                for query in ('','  '):
                    html=self.client.get('/',params={'mode':'description','q':query,'lang':lang}).text
                    self.assertIn(engine_i18n.translate('semantic_empty',lang),html)
                encode.assert_not_called()
            with patch.object(services,'semantic_search',side_effect=errors.IndexStateError('embedding_unavailable',url='http://tei')):
                html=self.client.get('/',params={'mode':'description','q':'space','lang':lang}).text
                self.assertIn(engine_i18n.translate('embedding_unavailable',lang,url='http://tei'),html)
        for mode in ('bad','<script>'):
            with patch.object(services,'semantic_search') as search:
                html=self.client.get('/',params={'mode':mode,'q':'space','lang':'en'}).text
                self.assertIn(engine_i18n.translate('search_mode'),html)
                self.assertNotIn('<script>',html)
                search.assert_not_called()

    def test_reserved_collection_is_rejected(self):
        with helpers.expected_error(self) as error:
            with TestClient(web_app.create_app({'movies_collection': 'movies'})):
                pass
        self.assertEqual(error.exception._localization[0], 'semantic_schema')

    def test_old_url_uses_movie_mode(self):
        with patch.object(services,'search',return_value={'source':{},'recommendations':[]}) as search:
            html=self.client.get('/?q=1').text
            search.assert_called_once()
            self.assertIn('<option value="movie" selected>',html)
