from web.http import security


def post(client, path, data=None, **kwargs):
    if not client.cookies.get(security.CSRF_COOKIE):
        client.get('/')
    return client.post(path, data={**(data or {}),
                       'csrf_token': client.cookies[security.CSRF_COOKIE]}, **kwargs)
