from web.routes import index, search


def register_routes(app):
    app.add_url_rule('/', view_func=index, methods=['GET'])
    app.add_url_rule('/search', view_func=search, methods=['POST'])
