from fastapi import APIRouter

from backend.api.http.routes import account, admin, auth, context, search, search_tasks, spa


router = APIRouter()
for module in (context, search, auth, account, admin, search_tasks, spa):
    router.include_router(module.router)
