from alter_core.agent_api import router as agent_router
from alter_core.api import app

app.include_router(agent_router)
