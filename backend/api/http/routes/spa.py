from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from backend.api.http.transport import i18n


CLIENT_PATH = Path(__file__).resolve().parents[4] / 'frontend' / 'dist'
router = APIRouter()


@router.api_route('/api', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD'])
@router.api_route('/api/{path:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD'])
async def missing_api():
    raise HTTPException(404, 'Not Found')

@router.get('/{path:path}', include_in_schema=False)
async def client(request: Request, path: str):
    if path == 'api' or path.startswith('api/'):
        raise HTTPException(404, 'Not Found')
    root = CLIENT_PATH.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise HTTPException(404, 'Not Found')
    if path and target.is_file():
        return FileResponse(target, headers={'Cache-Control': 'public, max-age=31536000, immutable'}
                            if path.startswith('assets/') else {'Cache-Control': 'no-cache'})
    if path in ('assets', 'static') or path.startswith(('assets/', 'static/')) or Path(path).suffix:
        raise HTTPException(404, 'Not Found')
    index = root / 'index.html'
    if not index.is_file():
        lang = i18n.select_language(request)
        message = ('Client build is missing. Run npm ci and npm run build in frontend/.' if lang == 'en'
                   else 'Сборка клиента отсутствует. Выполните npm ci и npm run build в frontend/.')
        return i18n.remember_language(JSONResponse({'error': message}, status_code=503), lang)
    return FileResponse(index, headers={'Cache-Control': 'no-cache'})
