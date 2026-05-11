from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .registry import get_workbench
from .routes.ai_provider_config import router as ai_provider_router
from .routes.ai_video_analysis import router as ai_video_analysis_router
from .routes.ai_prompt_reverse import router as ai_prompt_reverse_router
from .routes.douyin import router as douyin_router
from .routes.jianying import router as jianying_router
from .routes.jianying_editor_sdk import router as jianying_editor_sdk_router
from .routes.runninghub_tts import router as runninghub_tts_router
from .routes.studio import router as studio_router
from .routes.tasks import router as tasks_router
from .routes.text_to_assets import router as text_to_assets_router
from .routes.video_script import router as video_script_router
from .task_store import init_db

app = FastAPI(title="Personal Ops Workbench API")
init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/workbench")
def workbench():
    return get_workbench()


app.include_router(douyin_router)
app.include_router(ai_provider_router)
app.include_router(ai_video_analysis_router)
app.include_router(ai_prompt_reverse_router)
app.include_router(tasks_router)
app.include_router(video_script_router)
app.include_router(text_to_assets_router)
app.include_router(jianying_router)
app.include_router(jianying_editor_sdk_router)
app.include_router(runninghub_tts_router)
app.include_router(studio_router)


DIST_DIR = Path(__file__).resolve().parents[2] / "dist"

if DIST_DIR.exists():
    assets_dir = DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def web_index():
        return FileResponse(DIST_DIR / "index.html")

    @app.get("/{path:path}", include_in_schema=False)
    def web_fallback(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")

        target = (DIST_DIR / path).resolve()
        if target.is_file() and DIST_DIR in target.parents:
            return FileResponse(target)
        return FileResponse(DIST_DIR / "index.html")
