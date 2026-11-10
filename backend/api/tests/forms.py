from backend.api.http import security


def post(client, path, data=None, **kwargs):
    if not client.cookies.get(security.CSRF_COOKIE):
        client.cookies.set(security.CSRF_COOKIE, 'test-csrf')
    return client.post('/api' + path, json=data or {},
                       headers={'X-CSRF-Token': client.cookies[security.CSRF_COOKIE]}, **kwargs)
