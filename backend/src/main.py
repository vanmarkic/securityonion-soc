from fastapi import FastAPI

from src.api.case_routes import router as case_router
from src.api.config_routes import router as config_router
from src.api.detection_routes import router as detection_router
from src.api.grid_routes import router as grid_router
from src.api.info_routes import router as info_router
from src.api.util_routes import router as util_router

app = FastAPI(title="SecurityOnion SOC", version="0.1.0")

app.include_router(info_router, prefix="/api")
app.include_router(config_router, prefix="/api")
app.include_router(util_router, prefix="/api")
app.include_router(grid_router, prefix="/api")
app.include_router(case_router, prefix="/api")
app.include_router(detection_router, prefix="/api")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
