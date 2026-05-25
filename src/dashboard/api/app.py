from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from dashboard.api.routes import router as api_router

FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(title="MSpec Dashboard", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    if FRONTEND_DIST.exists():
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(request: Request, full_path: str):
            if full_path.startswith("api/") or full_path == "health":
                return FileResponse(FRONTEND_DIST / "index.html")
            if full_path and FRONTEND_DIST / full_path != FRONTEND_DIST / "index.html":
                file_path = FRONTEND_DIST / full_path
                if file_path.exists():
                    return FileResponse(str(file_path))
            return FileResponse(str(FRONTEND_DIST / "index.html"))

    return app
