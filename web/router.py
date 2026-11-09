from fastapi import APIRouter

from web import routes


router = APIRouter()
router.add_api_route('/', routes.index, methods=['GET'], name='index')
router.add_api_route('/search', routes.search, methods=['POST'], name='search')
