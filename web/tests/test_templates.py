from types import SimpleNamespace
import unittest

from starlette.requests import Request

from web import app
from web.presentation import pages


class TemplatePresentationTests(unittest.TestCase):
    def setUp(self):
        self.app = app.create_app()
        self.user = SimpleNamespace(role='admin', email='admin@example.com')

    def render(self, template, route_name='account', lang='en', **values):
        route = SimpleNamespace(name=route_name)
        request = Request({'type': 'http', 'method': 'GET', 'scheme': 'http',
                           'server': ('test', 80), 'path': '/', 'root_path': '',
                           'query_string': b'', 'headers': [], 'app': self.app,
                           'router': self.app.router, 'route': route})
        context = {'request': request, 'user': self.user, 'lang': lang,
                   'csrf_token': 'csrf', 'switches': {'en': '/?lang=en', 'ru': '/?lang=ru'},
                   '_': lambda message, **params: pages.translate(message, lang, **params)}
        return pages.templates.get_template(template).render(**{**context, **values})

    def test_current_navigation_and_logout_order_in_both_languages(self):
        for lang in ('en', 'ru'):
            for route, path in (('index', '/'), ('search', '/'), ('account', '/account'),
                                ('login', '/login'), ('register', '/register'),
                                ('admin_users', '/admin/users'), ('admin_user', '/admin/users')):
                with self.subTest(lang=lang, route=route):
                    html = self.render('navigation.html', route, lang,
                                       user=None if route in ('login', 'register') else self.user)
                    self.assertEqual(html.count('aria-current="page"'), 1)
                    self.assertIn(f'{path}?lang={lang}" aria-current="page"', html)
                    self.assertIn('class="language-switcher"', html)
                    if route not in ('login', 'register'):
                        self.assertIn('class="button-danger"', html)
                        self.assertGreater(html.index('class="logout"'),
                                           html.index('class="language-switcher"'))

    def test_account_pagination_visibility_in_both_languages(self):
        for lang in ('en', 'ru'):
            for total, page, has_next in ((0, 1, False), (0, 2, False), (1, 1, False),
                                           (20, 1, False), (20, 2, False),
                                           (21, 1, True), (21, 2, False)):
                with self.subTest(lang=lang, total=total, page=page):
                    listing = {'flag': 'watched', 'label': 'Watched', 'total': total,
                               'movies': [], 'page': page, 'has_next': has_next,
                               'has_multiple_pages': total > 20,
                               'previous_url': '/account?page=1', 'next_url': '/account?page=2'}
                    html = self.render('account.html', lang=lang, lists=[listing])
                    self.assertEqual('class="pagination"' in html, total > 20)
                    if total > 20:
                        self.assertIn(pages.translate('Page %(page)s', lang, page=page), html)
                        self.assertEqual('/account?page=1' in html, page > 1)
                        self.assertEqual('/account?page=2' in html, has_next)
                    else:
                        self.assertNotIn(pages.translate('Page %(page)s', lang, page=page), html)

    def test_empty_admin_pagination_is_hidden_in_both_languages(self):
        for lang in ('en', 'ru'):
            for previous_url, next_url in ((None, None), (None, '/admin/users?page=2'),
                                           ('/admin/users?page=1', None)):
                with self.subTest(lang=lang, previous=previous_url, next=next_url):
                    html = self.render('admin_users.html', route_name='admin_users', lang=lang,
                                       users=[], q='', role_filter='', state_filter='',
                                       previous_url=previous_url, next_url=next_url)
                    self.assertEqual(html.count('<nav '), 2 if previous_url or next_url else 1)

    def test_search_has_no_global_wikidata_notice_in_both_languages(self):
        for lang in ('en', 'ru'):
            html = self.render('index.html', route_name='index', lang=lang,
                               mode='movie', search_modes=('movie', 'description'), query='',
                               limit=5, limit_options=(5,), catalog=[], error=None, result=None)
            self.assertNotIn('Wikidata', html)
