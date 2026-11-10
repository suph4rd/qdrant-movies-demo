from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from backend.api.http.transport import i18n


def response(request, data, status=200):
    result = JSONResponse(jsonable_encoder(data), status_code=status)
    result.headers['Cache-Control'] = 'no-store'
    return i18n.remember_language(result, i18n.select_language(request))


