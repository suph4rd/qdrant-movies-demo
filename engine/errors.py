from engine.i18n import localize_movie, translate


class DemoError(Exception):
    def __init__(self, key, **params):
        self.key = key
        self.params = params
        super().__init__(key)

    def format(self, lang='en'):
        params = dict(self.params)
        if self.key == 'ambiguous':
            params['titles'] = ', '.join(localize_movie(m, lang)['title'] for m in params.pop('movies'))
        return translate(self.key, lang, **params)

    def __str__(self):
        return self.format()
