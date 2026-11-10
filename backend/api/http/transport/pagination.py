from backend.api.application import errors


def page_number(request):
    raw = request.query_params.get('page', '1')
    if not raw.isascii() or not raw.isdecimal() or len(raw) > 7 or not 1 <= int(raw) <= 1000000:
        raise errors.ScenarioError('Invalid page number.')
    return int(raw)

