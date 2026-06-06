from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import export, jobs, podcast, settings as settings_api
from app.config import get_settings
from app.database import init_db
from app.utils.logging import configure_logging


def create_app() -> FastAPI:
    """Create and configure the VoiceScribe FastAPI application."""
    settings = get_settings()
    configure_logging()
    init_db()

    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
    app.include_router(export.router, prefix="/api/jobs", tags=["export"])
    app.include_router(podcast.router, prefix="/api/podcast", tags=["podcast"])
    app.include_router(settings_api.router, prefix="/api/settings", tags=["settings"])

    @app.get("/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
