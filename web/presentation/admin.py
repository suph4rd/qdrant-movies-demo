from urllib.parse import urlencode

from engine import i18n as engine_i18n
from web.application.services import account


def page_url(request, page, **params):
    return str(request.url.replace(query=urlencode({**dict(request.query_params), **params, 'page': page})))


def state_name(user):
    return 'Deleted' if user.deleted_at is not None else 'Blocked' if user.blocked else 'Active'


def user_detail(request, detail, page, lang):
    lists = [{'title': account.LABELS[group.flag],
              'movies': [engine_i18n.localize_movie(movie, lang) for movie, mark in group.movies],
              'has_next': group.page * account.PAGE_SIZE < group.total} for group in detail.lists]
    return {'target': detail.user, 'state_name': state_name, 'lists': lists,
            'previous_url': page_url(request, page - 1) if page > 1 else None,
            'next_url': page_url(request, page + 1) if any(group['has_next'] for group in lists) else None}
