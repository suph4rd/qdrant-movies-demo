from fastapi import APIRouter

from web.http.routes import account
from web.http.routes import admin
from web.http.routes import auth
from web.http.routes import search


router = APIRouter()
router.add_api_route('/', search.index, methods=['GET'], name='index')
router.add_api_route('/search', search.search, methods=['POST'], name='search')
router.include_router(auth.router)
router.include_router(account.router)
router.include_router(admin.router)
