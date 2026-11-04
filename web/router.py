from fastapi import APIRouter
from web.routes import index, search

router = APIRouter()
router.add_api_route('/', index, methods=['GET'], name='index')
router.add_api_route('/search', search, methods=['POST'], name='search')
