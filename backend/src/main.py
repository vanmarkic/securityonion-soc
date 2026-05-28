from fastapi import FastAPI

from src.api.case_routes import router as case_router
from src.api.clients_routes import router as clients_router
from src.api.config_routes import router as config_router
from src.api.detection_routes import router as detection_router
from src.api.events_routes import router as events_router
from src.api.job_routes import router as job_router
from src.api.jobs_routes import router as jobs_router
from src.api.grid_routes import router as grid_router
from src.api.gridmembers_routes import router as gridmembers_router
from src.api.info_routes import router as info_router
from src.api.node_routes import router as node_router
from src.api.packet_routes import router as packet_router
from src.api.playbook_routes import router as playbook_router
from src.api.query_routes import router as query_router
from src.api.roles_routes import router as roles_router
from src.api.stream_routes import router as stream_router
from src.api.users_routes import router as users_router
from src.api.util_routes import router as util_router

app = FastAPI(title="SecurityOnion SOC", version="0.1.0")

app.include_router(info_router, prefix="/api")
app.include_router(config_router, prefix="/api")
app.include_router(util_router, prefix="/api")
app.include_router(grid_router, prefix="/api")
app.include_router(gridmembers_router, prefix="/api")
app.include_router(case_router, prefix="/api")
app.include_router(detection_router, prefix="/api")
app.include_router(events_router, prefix="/api")
app.include_router(job_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(node_router, prefix="/api")
app.include_router(packet_router, prefix="/api")
app.include_router(query_router, prefix="/api")
app.include_router(playbook_router, prefix="/api")
app.include_router(stream_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(roles_router, prefix="/api")
app.include_router(clients_router, prefix="/api")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
