from fastapi import FastAPI

from src.api.config_routes import router as config_router
from src.api.info_routes import router as info_router

app = FastAPI(title="SecurityOnion SOC", version="0.1.0")

app.include_router(info_router, prefix="/api")
app.include_router(config_router, prefix="/api")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
