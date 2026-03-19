from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.infra.scheduler import WorkerSchedulerService
from app.services.observability import LangSmithService

setup_logging()
settings = get_settings()
LangSmithService(settings)
scheduler = WorkerSchedulerService(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler.start()
    try:
        yield
    finally:
        scheduler.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(router)
