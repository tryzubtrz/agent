from alter_core.agent_api import router as agent_router
from alter_core.approval_api import router as approval_router
from alter_core.connector_gateway_api import router as connector_gateway_router
from alter_core.conversation_api import router as conversation_router
from alter_core.document_api import router as document_router
from alter_core.memory_admin_api import router as memory_admin_router
from alter_core.model_api import router as model_router
from alter_core.policy_admin_api import router as policy_admin_router
from alter_core.productivity_api import router as productivity_router
from alter_core.system_api import router as system_router
from alter_core.vault_api import router as vault_router
from alter_core.api import app

app.include_router(agent_router)
app.include_router(approval_router)
app.include_router(connector_gateway_router)
app.include_router(conversation_router)
app.include_router(document_router)
app.include_router(memory_admin_router)
app.include_router(model_router)
app.include_router(policy_admin_router)
app.include_router(productivity_router)
app.include_router(system_router)
app.include_router(vault_router)
