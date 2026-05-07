from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .registry import get_workbench
from .routes.ai_provider_config import router as ai_provider_router
from .routes.ai_video_analysis import router as ai_video_analysis_router
from .routes.ai_prompt_reverse import router as ai_prompt_reverse_router
from .routes.douyin import router as douyin_router
from .routes.tasks import router as tasks_router
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
