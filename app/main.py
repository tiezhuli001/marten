from fastapi import FastAPI

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.infra.observability import LangSmithService

setup_logging()
settings = get_settings()
LangSmithService(settings)
app = FastAPI(title=settings.app_name)
app.include_router(router)
