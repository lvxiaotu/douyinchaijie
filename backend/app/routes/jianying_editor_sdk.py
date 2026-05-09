from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

router = APIRouter(prefix="/api/tools/jianying-editor-sdk", tags=["jianying-editor-sdk"])

SDK_ROOT = Path(__file__).resolve().parents[3] / "sdks" / "jianying-editor-skill"

KEY_ENTRIES = [
    ("Python SDK", "scripts/jy_wrapper.py", "JyProject 剪映自动化封装入口"),
    ("草稿检查 CLI", "scripts/draft_inspector.py", "列出、摘要和查看剪映草稿"),
    ("环境诊断 CLI", "scripts/api_validator.py", "检查运行依赖和 SDK 可用性"),
    ("自动导出 CLI", "scripts/auto_exporter.py", "调用剪映导出 MP4/SRT"),
    ("素材搜索 CLI", "scripts/asset_search.py", "搜索特效、转场、滤镜和曲库数据"),
    ("开发者指南", "index.html", "SDK 自带网页文档入口"),
]


def _require_sdk() -> None:
    if not SDK_ROOT.exists():
        raise HTTPException(status_code=404, detail=f"SDK not found: {SDK_ROOT}")


def _version() -> str:
    version_file = SDK_ROOT / "VERSION"
    if not version_file.exists():
        return "unknown"
    return version_file.read_text(encoding="utf-8").strip() or "unknown"


@router.get("/status")
def sdk_status() -> dict:
    _require_sdk()
    entries = [
        {
            "name": name,
            "path": str((SDK_ROOT / relative_path).resolve()),
            "relative_path": relative_path,
            "description": description,
            "exists": (SDK_ROOT / relative_path).exists(),
        }
        for name, relative_path, description in KEY_ENTRIES
    ]
    return {
        "id": "jianying-editor-sdk",
        "name": "JianYing Editor Skill SDK",
        "version": _version(),
        "root": str(SDK_ROOT.resolve()),
        "repo_url": "https://github.com/luoluoluo22/jianying-editor-skill",
        "guide_url": "/api/tools/jianying-editor-sdk/page",
        "entries": entries,
        "ready": all(entry["exists"] for entry in entries),
    }


@router.get("/page", include_in_schema=False)
def sdk_page():
    _require_sdk()
    index_path = SDK_ROOT / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="SDK index.html not found")
    return FileResponse(index_path)


if (SDK_ROOT / "assets").exists():
    router.mount("/assets", StaticFiles(directory=SDK_ROOT / "assets"), name="jianying_editor_sdk_assets")
