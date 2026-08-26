from alter_core.agent_api import router as agent_router
from alter_core.approval_api import router as approval_router
from alter_core.conversation_api import router as conversation_router
from alter_core.model_api import router as model_router
from alter_core.system_api import router as system_router
from alter_core.vault_api import router as vault_router
from alter_core.api import app

app.include_router(agent_router)
app.include_router(approval_router)
app.include_router(conversation_router)
app.include_router(model_router)
app.include_router(system_router)
app.include_router(vault_router)
