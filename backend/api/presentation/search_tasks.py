from backend.engine import errors, i18n as engine_i18n
from backend.api.application import task_snapshots
from backend.api.presentation import api


def summary(task):
    return {'task_id': task.id, 'status': task.status,
            'params': {'q': task.query, 'mode': task.mode, 'limit': task.limit},
            'created_at': task.created_at, 'completed_at': task.completed_at,
            'read': task.read_at is not None}


def detail(task, lang, catalog, cards=None):
    error = None
    if task.error:
        if task.error.get('unexpected'):
            error = engine_i18n.translate_message('External search failed. Please try again.', lang)
        else:
            error = errors.format_error(task_snapshots.thaw(task.error), lang)
    return {**summary(task), 'error': error,
            'result': api.search_result(task_snapshots.thaw(task.result), lang,
                catalog, cards) if task.result else None}
