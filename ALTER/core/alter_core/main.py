"""Canonical ALTER FastAPI application.

Vercel and local runners must import this module, not the bare base app, so every
feature router is mounted exactly once in every environment.
"""

from .api import app
from .access_api import router as access_router
from .agent_api import router as agent_router
from .approval_api import router as approval_router
from .automation_tick_api import router as automation_tick_router
from .connector_gateway_api import router as connector_gateway_router
from .conversation_api import router as conversation_router
from .document_api import router as document_router
from .market_api import router as market_router
from .media_api import router as media_router
from .memory_admin_api import router as memory_admin_router
from .memory_v2_api import router as memory_v2_router
from .model_api import router as model_router
from .productivity_api import router as productivity_router
from .rag_api import router as rag_router
from .scheduler_api import router as scheduler_router
from .system_api import router as system_router
from .vault_api import router as vault_router

for router in (
    access_router,
    agent_router,
    approval_router,
    automation_tick_router,
    connector_gateway_router,
    conversation_router,
    document_router,
    market_router,
    media_router,
    memory_admin_router,
    memory_v2_router,
    model_router,
    productivity_router,
    rag_router,
    scheduler_router,
    system_router,
    vault_router,
):
    app.include_router(router)
