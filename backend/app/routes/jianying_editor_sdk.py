from __future__ import annotations

import importlib.util
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from integrations.jianying_editor_skill.sdk_capability_service import SdkCapabilityService

router = APIRouter(prefix="/api/tools/jianying-editor-sdk", tags=["jianying-editor-sdk"])

SDK_ROOT = Path(__file__).resolve().parents[3] / "sdks" / "jianying-editor-skill"
SDK_LOCK_FILE = SDK_ROOT.parent / "jianying-editor-skill.lock.json"

KEY_ENTRIES = [
    ("Python SDK", "scripts/jy_wrapper.py", "JyProject 剪映自动化封装入口"),
    ("草稿检查 CLI", "scripts/draft_inspector.py", "列出、摘要和查看剪映草稿"),
    ("环境诊断 CLI", "scripts/api_validator.py", "检查运行依赖和 SDK 可用性"),
    ("自动导出 CLI", "scripts/auto_exporter.py", "调用剪映导出 MP4/SRT"),
    ("素材搜索 CLI", "scripts/asset_search.py", "搜索特效、转场、滤镜和曲库数据"),
    ("网页录屏 CLI", "scripts/web_recorder.py", "将网页动画录制成视频素材"),
    ("云素材管理", "scripts/cloud_manager.py", "解析、缓存和下载云素材/云音乐"),
    ("云音乐库同步", "scripts/build_cloud_music_library.py", "从本地草稿同步云音乐和音效库"),
    ("智能缩放", "scripts/smart_zoomer.py", "根据点击事件为录屏素材添加缩放关键帧"),
    ("电影解说构建", "scripts/movie_commentary_builder.py", "按故事版拼装解说草稿"),
    ("TTS", "scripts/universal_tts.py", "使用剪映/SAMI 或 Edge TTS 生成配音"),
    ("开发者指南", "index.html", "SDK 自带网页文档入口"),
]

REQUIRED_PACKAGES = [
    ("pyJianYingDraft", "pyJianYingDraft", "草稿创建"),
]

OPTIONAL_PACKAGES = [
    ("playwright", "playwright", "Web VFX"),
    ("uiautomation", "uiautomation", "剪映自动导出"),
    ("pynput", "pynput", "录制/键鼠控制"),
    ("edge-tts", "edge_tts", "TTS"),
    ("websockets", "websockets", "剪映/SAMI TTS"),
    ("opencv-python", "cv2", "视觉处理"),
    ("numpy", "numpy", "视觉/音频处理"),
]

CAPABILITY_ORDER = [
    "can_create_draft",
    "can_validate_draft",
    "can_inspect_draft",
    "can_asset_search",
    "can_cloud_media",
    "can_cloud_music",
    "can_tts",
    "can_web_vfx",
    "can_record_screen",
    "can_smart_zoom",
    "can_movie_commentary",
    "can_auto_export",
]


class SdkDraftListRequest(BaseModel):
    root: str = Field(default="")
    limit: int = Field(default=20, ge=0, le=200)


class SdkDraftInspectRequest(BaseModel):
    root: str = Field(default="")
    name: str = Field(default="")
    path: str = Field(default="")
    kind: str = Field(default="content")


class SdkAssetSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    category: str = Field(default="")
    limit: int = Field(default=20, ge=1, le=200)


class SdkAutoExportRequest(BaseModel):
    name: str = Field(min_length=1)
    output_path: str = Field(min_length=1)
    resolution: str = Field(default="")
    framerate: str = Field(default="")


class SdkDeepDiagnosticsRequest(BaseModel):
    project: str = Field(default="")
    video: str = Field(default="")
    strict: bool = Field(default=False)


class SdkWebVfxRequest(BaseModel):
    source: str = Field(min_length=1)
    output_path: str = Field(min_length=1)
    max_duration_seconds: float = Field(default=30, gt=0, le=300)


class SdkTtsRequest(BaseModel):
    text: str = Field(min_length=1)
    output_path: str = Field(min_length=1)
    speaker: str = Field(default="zh_male_huoli")
    backend: str = Field(default="")
    allow_fallback: bool = Field(default=True)
    sami_retries: int = Field(default=2, ge=0, le=5)


class SdkCloudAssetRequest(BaseModel):
    query: str = Field(min_length=1)
    force: bool = Field(default=False)


class SdkCloudMusicLibraryRequest(BaseModel):
    projects_root: str = Field(default="")
    dry_run: bool = Field(default=False)


class SdkSmartZoomRequest(BaseModel):
    project_name: str = Field(min_length=1)
    video_path: str = Field(min_length=1)
    events_json_path: str = Field(min_length=1)
    zoom_scale: int = Field(default=150, ge=100, le=400)
    hold_seconds: float = Field(default=5, gt=0, le=30)


class SdkMovieCommentaryRequest(BaseModel):
    video_path: str = Field(min_length=1)
    storyboard_path: str = Field(min_length=1)
    project_name: str = Field(default="Movie_Commentary_Project")
    bgm_path: str = Field(default="")
    mask_path: str = Field(default="")


def capability_service() -> SdkCapabilityService:
    return SdkCapabilityService()


def _require_sdk() -> None:
    if not SDK_ROOT.exists():
        raise HTTPException(status_code=404, detail=f"SDK not found: {SDK_ROOT}")


def _version() -> str:
    version_file = SDK_ROOT / "VERSION"
    if not version_file.exists():
        return "unknown"
    return version_file.read_text(encoding="utf-8").strip() or "unknown"


def _lock_info() -> dict[str, Any]:
    if not SDK_LOCK_FILE.exists():
        return {}
    try:
        data = json.loads(SDK_LOCK_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "path": str(SDK_LOCK_FILE)}
    return data if isinstance(data, dict) else {}


def _ok_check(message: str = "", **extra: Any) -> dict[str, Any]:
    return {"ok": True, "message": message, **extra}


def _fail_check(message: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "message": message, **extra}


def _prepare_import_paths() -> None:
    for entry in [SDK_ROOT / "scripts", SDK_ROOT / "scripts" / "vendor"]:
        path = str(entry)
        if path not in sys.path:
            sys.path.insert(0, path)


def _check_jyproject_import() -> dict[str, Any]:
    try:
        _prepare_import_paths()
        from jy_wrapper import JyProject  # type: ignore  # noqa: F401

        return _ok_check("JyProject import succeeded.")
    except Exception as exc:
        return _fail_check(f"{type(exc).__name__}: {exc}")


def _package_status(packages: list[tuple[str, str, str]]) -> dict[str, Any]:
    _prepare_import_paths()
    missing: list[dict[str, str]] = []
    available: list[dict[str, str]] = []
    for package_name, module_name, capability in packages:
        item = {"package": package_name, "module": module_name, "capability": capability}
        if importlib.util.find_spec(module_name):
            available.append(item)
        else:
            missing.append(item)
    return {
        "ok": not missing,
        "available": available,
        "missing": missing,
    }


def _parse_json_line(text: str) -> dict[str, Any] | None:
    for line in reversed([line.strip() for line in text.splitlines() if line.strip()]):
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _run_api_validator(project: str = "", video: str = "", strict: bool = False) -> dict[str, Any]:
    script_path = SDK_ROOT / "scripts" / "api_validator.py"
    if not script_path.exists():
        return _fail_check("api_validator.py not found.", path=str(script_path))
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    command = [sys.executable, str(script_path), "--json"]
    if project:
        command.extend(["--project", project])
    if video:
        command.extend(["--video", video])
    if strict:
        command.append("--strict")
    try:
        completed = subprocess.run(
            command,
            cwd=str(script_path.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return _fail_check("api_validator.py timed out.", timeout_seconds=25, stdout=exc.stdout or "", stderr=exc.stderr or "")
    except Exception as exc:
        return _fail_check(f"{type(exc).__name__}: {exc}")

    parsed = _parse_json_line(completed.stdout)
    ok = completed.returncode == 0 and bool(parsed and parsed.get("ok"))
    message = ""
    if parsed:
        message = str(parsed.get("reason") or parsed.get("code") or "")
    if not message and completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}"
    return {
        "ok": ok,
        "message": message or ("api_validator.py succeeded." if ok else "api_validator.py failed."),
        "exit_code": completed.returncode,
        "command": command,
        "data": parsed or {},
        "stdout_tail": completed.stdout.strip().splitlines()[-5:],
        "stderr_tail": completed.stderr.strip().splitlines()[-5:],
    }


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = [int(part) for part in re.findall(r"\d+", value)[:4]]
    return tuple(parts)


def _version_at_most(value: str, maximum: tuple[int, ...]) -> bool | None:
    current = _version_tuple(value)
    if not current:
        return None
    padded_current = current[: len(maximum)] + (0,) * max(0, len(maximum) - len(current))
    padded_maximum = maximum
    return padded_current <= padded_maximum


def _read_windows_file_version(exe_path: Path) -> str:
    if platform.system() != "Windows":
        return ""
    try:
        import ctypes
        from ctypes import wintypes

        size = ctypes.windll.version.GetFileVersionInfoSizeW(str(exe_path), None)
        if not size:
            return ""
        buffer = ctypes.create_string_buffer(size)
        ctypes.windll.version.GetFileVersionInfoW(str(exe_path), 0, size, buffer)
        lp_buffer = ctypes.c_void_p()
        length = wintypes.UINT()
        ctypes.windll.version.VerQueryValueW(buffer, "\\", ctypes.byref(lp_buffer), ctypes.byref(length))
        fixed_info = ctypes.cast(lp_buffer, ctypes.POINTER(ctypes.c_uint32 * 13)).contents
        ms = fixed_info[2]
        ls = fixed_info[3]
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception:
        return ""


def _version_from_path(path: Path) -> str:
    for part in reversed(path.parts):
        match = re.search(r"\d+(?:\.\d+){1,3}", part)
        if match:
            return match.group(0)
    return ""


def _detect_jianying_installation() -> dict[str, Any]:
    env_version = (os.getenv("JY_JIANYING_VERSION") or "").strip()
    if env_version:
        return {
            "detected": True,
            "source": "JY_JIANYING_VERSION",
            "version": env_version,
            "path": "",
            "version_ok": _version_at_most(env_version, (5, 9)),
            "max_supported_version": "5.9",
        }

    if platform.system() != "Windows":
        return {
            "detected": False,
            "source": "platform",
            "version": "",
            "path": "",
            "version_ok": False,
            "max_supported_version": "5.9",
        }

    candidates: list[Path] = []
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        jy_root = Path(local_app_data) / "JianyingPro"
        if jy_root.exists():
            candidates.extend(sorted(jy_root.glob("Apps/*/JianyingPro.exe"), reverse=True))
            candidates.extend(sorted(jy_root.glob("**/JianyingPro.exe"), reverse=True)[:10])

    for env_name in ["PROGRAMFILES", "PROGRAMFILES(X86)"]:
        root = os.getenv(env_name)
        if not root:
            continue
        for relative in [
            Path("JianyingPro") / "JianyingPro.exe",
            Path("Jianying") / "JianyingPro.exe",
            Path("CapCut") / "CapCut.exe",
        ]:
            candidate = Path(root) / relative
            if candidate.exists():
                candidates.append(candidate)

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        version = _read_windows_file_version(resolved)
        if not version:
            version = _version_from_path(resolved)
        if version:
            return {
                "detected": True,
                "source": "filesystem",
                "version": version,
                "path": str(resolved),
                "version_ok": _version_at_most(version, (5, 9)),
                "max_supported_version": "5.9",
            }

    return {
        "detected": False,
        "source": "filesystem",
        "version": "",
        "path": "",
        "version_ok": None,
        "max_supported_version": "5.9",
    }


def _platform_check() -> dict[str, Any]:
    system = platform.system()
    jianying = _detect_jianying_installation()
    return {
        "ok": True,
        "system": system,
        "release": platform.release(),
        "python": sys.version.split()[0],
        "auto_export_platform_ok": system == "Windows",
        "jianying": jianying,
        "auto_export_version_ok": jianying["version_ok"] is True,
    }


def _script_exists(name: str) -> bool:
    return (SDK_ROOT / "scripts" / name).exists()


def _module_missing(package_status: dict[str, Any], module_name: str) -> bool:
    return any(item["module"] == module_name for item in package_status.get("missing", []))


def _capability_item(
    key: str,
    label: str,
    *,
    script: str,
    endpoint: str,
    implemented: bool,
    available: bool,
    dependencies: list[str],
    platforms: list[str],
    acceptance: str,
    message: str,
    invocation: str,
    requires_user_action: bool = False,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "script": script,
        "endpoint": endpoint,
        "implemented": implemented,
        "available": bool(implemented and available),
        "dependencies": dependencies,
        "platforms": platforms,
        "acceptance": acceptance,
        "message": message,
        "invocation": invocation,
        "requires_user_action": requires_user_action,
    }


def _build_capability_matrix(checks: dict[str, Any]) -> list[dict[str, Any]]:
    optional_packages = checks["optional_requirements"]
    required_packages = checks["sdk_requirements"]
    jyproject_ok = bool(checks["jyproject_import"]["ok"] and required_packages["ok"])
    create_draft_ok = jyproject_ok
    if "smoke_draft_create" in checks:
        create_draft_ok = bool(jyproject_ok and checks["smoke_draft_create"].get("ok"))
    platform_info = checks["platform"]
    auto_export_version_ok = platform_info.get("auto_export_version_ok") is True
    auto_export_available = bool(
        _script_exists("auto_exporter.py")
        and platform_info["auto_export_platform_ok"]
        and auto_export_version_ok
        and not _module_missing(optional_packages, "uiautomation")
    )
    web_recording_ok = bool(_script_exists("web_recorder.py") and not _module_missing(optional_packages, "playwright"))
    tts_ok = bool(
        _script_exists("universal_tts.py")
        and not _module_missing(optional_packages, "websockets")
        and not _module_missing(optional_packages, "edge_tts")
    )
    items = [
        _capability_item(
            "can_create_draft",
            "创建草稿",
            script="scripts/jy_wrapper.py",
            endpoint="/api/tools/jianying/drafts/create-from-script",
            implemented=True,
            available=create_draft_ok,
            dependencies=["pyJianYingDraft"],
            platforms=["Windows", "macOS", "Linux"],
            invocation="后端 JyProject/pyJianYingDraft 草稿创建链路",
            acceptance="深度诊断可显式创建 Diagnostic_Test 草稿；普通 status 不创建草稿。",
            message=(
                "深度诊断已验证最小草稿链路。"
                if checks.get("smoke_draft_create", {}).get("ok")
                else "JyProject 可导入，必要依赖满足；运行深度诊断可验证真实写草稿。"
                if jyproject_ok
                else "JyProject 或必要依赖不可用。"
            ),
        ),
        _capability_item(
            "can_validate_draft",
            "深度诊断",
            script="scripts/api_validator.py",
            endpoint="/api/tools/jianying-editor-sdk/diagnostics/deep",
            implemented=True,
            available=_script_exists("api_validator.py") and jyproject_ok,
            dependencies=["pyJianYingDraft", "ffprobe 可选"],
            platforms=["Windows", "macOS", "Linux"],
            invocation="POST 后显式运行 api_validator.py --json",
            acceptance="仅在用户触发深度诊断时创建诊断草稿并返回 JSON。",
            message="可运行显式深度诊断。" if _script_exists("api_validator.py") else "api_validator.py 缺失。",
        ),
        _capability_item(
            "can_inspect_draft",
            "查看草稿",
            script="scripts/draft_inspector.py",
            endpoint="/api/tools/jianying-editor-sdk/drafts/*",
            implemented=True,
            available=_script_exists("draft_inspector.py"),
            dependencies=[],
            platforms=["Windows", "macOS", "Linux"],
            invocation="draft_inspector.py list/summary/show --json",
            acceptance="可列出草稿、读取摘要、查看 draft_content/draft_meta_info。",
            message="草稿检查 CLI 已接入。" if _script_exists("draft_inspector.py") else "draft_inspector.py 缺失。",
        ),
        _capability_item(
            "can_asset_search",
            "素材搜索",
            script="scripts/asset_search.py",
            endpoint="/api/tools/jianying-editor-sdk/assets/search",
            implemented=True,
            available=_script_exists("asset_search.py"),
            dependencies=[],
            platforms=["Windows", "macOS", "Linux"],
            invocation="asset_search.py <query> --json",
            acceptance="可按关键词搜索 SDK data/*.csv 中的素材、特效、转场和曲库条目。",
            message="素材搜索 CLI 已接入。" if _script_exists("asset_search.py") else "asset_search.py 缺失。",
        ),
        _capability_item(
            "can_cloud_media",
            "云素材解析",
            script="scripts/cloud_manager.py",
            endpoint="/api/tools/jianying-editor-sdk/cloud/assets/resolve",
            implemented=True,
            available=_script_exists("cloud_manager.py"),
            dependencies=["requests"],
            platforms=["Windows", "macOS", "Linux"],
            invocation="CloudManager.find_asset/download_asset",
            acceptance="可根据云素材 ID 或名称解析本地库并按需下载到缓存。",
            message="云素材管理器已接入。" if _script_exists("cloud_manager.py") else "cloud_manager.py 缺失。",
        ),
        _capability_item(
            "can_cloud_music",
            "云音乐库",
            script="scripts/build_cloud_music_library.py",
            endpoint="/api/tools/jianying-editor-sdk/cloud/music-library/sync",
            implemented=True,
            available=_script_exists("build_cloud_music_library.py"),
            dependencies=[],
            platforms=["Windows"],
            invocation="build_cloud_music_library.py --json",
            acceptance="可从本地剪映草稿扫描云音乐和音效引用，dry-run 可无写入验证。",
            message="云音乐库同步 CLI 已接入。" if _script_exists("build_cloud_music_library.py") else "build_cloud_music_library.py 缺失。",
        ),
        _capability_item(
            "can_tts",
            "TTS",
            script="scripts/universal_tts.py",
            endpoint="/api/tools/jianying-editor-sdk/tts",
            implemented=True,
            available=tts_ok,
            dependencies=["websockets", "edge-tts"],
            platforms=["Windows", "macOS", "Linux"],
            invocation="universal_tts.generate_voice_with_meta",
            acceptance="可按文本生成音频文件，并返回实际使用的 TTS backend。",
            message="TTS 依赖满足。" if tts_ok else "TTS 需要 websockets 和 edge-tts。",
        ),
        _capability_item(
            "can_web_vfx",
            "Web VFX",
            script="scripts/web_recorder.py",
            endpoint="/api/tools/jianying-editor-sdk/web-vfx/record",
            implemented=True,
            available=web_recording_ok,
            dependencies=["playwright", "playwright chromium"],
            platforms=["Windows", "macOS", "Linux"],
            invocation="web_recorder.record_web_animation",
            acceptance="可把 URL 或 HTML 文件录制为 webm/mp4 素材。",
            message="网页录屏依赖满足。" if web_recording_ok else "Web VFX 需要 playwright 和浏览器安装。",
        ),
        _capability_item(
            "can_record_screen",
            "网页录屏",
            script="scripts/web_recorder.py",
            endpoint="/api/tools/jianying-editor-sdk/web-vfx/record",
            implemented=True,
            available=web_recording_ok,
            dependencies=["playwright", "playwright chromium"],
            platforms=["Windows", "macOS", "Linux"],
            invocation="web_recorder.record_web_animation",
            acceptance="可录制网页动画作为后续草稿素材。",
            message="录屏能力可用。" if web_recording_ok else "录屏能力需要 playwright。",
        ),
        _capability_item(
            "can_smart_zoom",
            "智能缩放",
            script="scripts/smart_zoomer.py",
            endpoint="/api/tools/jianying-editor-sdk/smart-zoom/drafts",
            implemented=True,
            available=_script_exists("smart_zoomer.py") and jyproject_ok,
            dependencies=["pyJianYingDraft", "点击事件 JSON"],
            platforms=["Windows", "macOS", "Linux"],
            invocation="项目桥接层读取 events.json 并为视频段写入关键帧",
            acceptance="可用 video + events.json 生成带缩放关键帧的剪映草稿。",
            message="智能缩放桥接已接入。" if _script_exists("smart_zoomer.py") else "smart_zoomer.py 缺失。",
        ),
        _capability_item(
            "can_movie_commentary",
            "电影解说",
            script="scripts/movie_commentary_builder.py",
            endpoint="/api/tools/jianying-editor-sdk/movie-commentary/drafts",
            implemented=True,
            available=_script_exists("movie_commentary_builder.py") and jyproject_ok,
            dependencies=["pyJianYingDraft", "故事版 JSON"],
            platforms=["Windows", "macOS", "Linux"],
            invocation="movie_commentary_builder.py --video --json --name",
            acceptance="可根据故事版切片、字幕和 BGM 生成解说草稿。",
            message="电影解说构建 CLI 已接入。" if _script_exists("movie_commentary_builder.py") else "movie_commentary_builder.py 缺失。",
        ),
        _capability_item(
            "can_auto_export",
            "自动导出",
            script="scripts/auto_exporter.py",
            endpoint="/api/tools/jianying-editor-sdk/exports",
            implemented=True,
            available=auto_export_available,
            dependencies=["uiautomation", "JianYing <= 5.9"],
            platforms=["Windows"],
            invocation="auto_exporter.py <draft> <output> --json",
            acceptance="仅当 Windows、uiautomation、剪映版本 <= 5.9 都满足时才标记可用。",
            message=(
                "自动导出环境满足。"
                if auto_export_available
                else "自动导出需要 Windows、uiautomation，并检测到剪映版本 <= 5.9。"
            ),
            requires_user_action=True,
        ),
    ]
    return sorted(items, key=lambda item: CAPABILITY_ORDER.index(item["key"]))


def _status_payload(deep_checks: dict[str, Any] | None = None) -> dict[str, Any]:
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
    key_entries_ok = all(entry["exists"] for entry in entries)
    required_packages = _package_status(REQUIRED_PACKAGES)
    optional_packages = _package_status(OPTIONAL_PACKAGES)
    checks = {
        "sdk_root": _ok_check("SDK root exists.", path=str(SDK_ROOT.resolve())),
        "key_entries": {
            "ok": key_entries_ok,
            "missing": [entry for entry in entries if not entry["exists"]],
        },
        "jyproject_import": _check_jyproject_import(),
        "sdk_requirements": required_packages,
        "optional_requirements": optional_packages,
        "platform": _platform_check(),
    }
    if deep_checks:
        checks.update(deep_checks)

    capability_matrix = _build_capability_matrix(checks)
    capabilities = {item["key"]: item["available"] for item in capability_matrix}
    warnings = []
    if not key_entries_ok:
        warnings.append("Some SDK entry files are missing.")
    if optional_packages["missing"]:
        missing_names = ", ".join(item["package"] for item in optional_packages["missing"])
        warnings.append(f"Optional SDK capabilities are limited by missing packages: {missing_names}.")
    if not checks["platform"]["auto_export_platform_ok"]:
        warnings.append("Auto export is only reported available on Windows.")
    elif checks["platform"]["jianying"]["version_ok"] is not True:
        warnings.append("Auto export requires a detected JianYing version <= 5.9; set JY_JIANYING_VERSION to override detection.")
    return {
        "id": "jianying-editor-sdk",
        "name": "JianYing Editor Skill SDK",
        "version": _version(),
        "lock": _lock_info(),
        "root": str(SDK_ROOT.resolve()),
        "repo_url": "https://github.com/luoluoluo22/jianying-editor-skill",
        "guide_url": "/api/tools/jianying-editor-sdk/page",
        "entries": entries,
        "checks": checks,
        "status_scope": "deep" if deep_checks else "light",
        "capabilities": capabilities,
        "capability_matrix": capability_matrix,
        "warnings": warnings,
        "ready": capabilities["can_create_draft"],
    }


def _capability_detail(status: dict[str, Any], key: str) -> dict[str, Any]:
    for item in status.get("capability_matrix", []):
        if item.get("key") == key:
            return item
    return {}


@router.get("/status")
def sdk_status() -> dict:
    _require_sdk()
    return _status_payload()


@router.post("/diagnostics/deep")
def run_sdk_deep_diagnostics(payload: SdkDeepDiagnosticsRequest) -> dict[str, Any]:
    _require_sdk()
    api_validator = _run_api_validator(project=payload.project, video=payload.video, strict=payload.strict)
    deep_checks = {
        "api_validator": api_validator,
        "smoke_draft_create": {
            "ok": bool(api_validator["ok"]),
            "message": api_validator["message"],
            "source": "api_validator.py --json",
        },
    }
    return _status_payload(deep_checks=deep_checks)


@router.get("/page", include_in_schema=False)
def sdk_page():
    _require_sdk()
    index_path = SDK_ROOT / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="SDK index.html not found")
    return FileResponse(index_path)


@router.post("/drafts/list")
def list_sdk_drafts(payload: SdkDraftListRequest) -> dict[str, Any]:
    _require_sdk()
    return capability_service().list_drafts(root=payload.root, limit=payload.limit)


@router.post("/drafts/summary")
def summarize_sdk_draft(payload: SdkDraftInspectRequest) -> dict[str, Any]:
    _require_sdk()
    return capability_service().summarize_draft(root=payload.root, name=payload.name, path=payload.path)


@router.post("/drafts/show")
def show_sdk_draft(payload: SdkDraftInspectRequest) -> dict[str, Any]:
    _require_sdk()
    return capability_service().show_draft(root=payload.root, name=payload.name, path=payload.path, kind=payload.kind)


@router.post("/assets/search")
def search_sdk_assets(payload: SdkAssetSearchRequest) -> dict[str, Any]:
    _require_sdk()
    return capability_service().search_assets(query=payload.query, category=payload.category, limit=payload.limit)


@router.post("/exports")
def export_sdk_draft(payload: SdkAutoExportRequest) -> dict[str, Any]:
    _require_sdk()
    status = _status_payload()
    auto_export = _capability_detail(status, "can_auto_export")
    if not auto_export.get("available"):
        raise HTTPException(
            status_code=409,
            detail={
                "message": auto_export.get("message") or "Auto export is not available in the current environment.",
                "capability": auto_export,
                "platform": status["checks"]["platform"],
            },
        )
    return capability_service().export_draft(
        name=payload.name,
        output_path=payload.output_path,
        resolution=payload.resolution,
        framerate=payload.framerate,
    )


@router.post("/web-vfx/record")
def record_sdk_web_vfx(payload: SdkWebVfxRequest) -> dict[str, Any]:
    _require_sdk()
    return capability_service().record_web_vfx(
        source=payload.source,
        output_path=payload.output_path,
        max_duration_seconds=payload.max_duration_seconds,
    )


@router.post("/tts")
def generate_sdk_tts(payload: SdkTtsRequest) -> dict[str, Any]:
    _require_sdk()
    return capability_service().generate_tts(
        text=payload.text,
        output_path=payload.output_path,
        speaker=payload.speaker,
        backend=payload.backend,
        allow_fallback=payload.allow_fallback,
        sami_retries=payload.sami_retries,
    )


@router.post("/cloud/assets/resolve")
def resolve_sdk_cloud_asset(payload: SdkCloudAssetRequest) -> dict[str, Any]:
    _require_sdk()
    return capability_service().resolve_cloud_asset(query=payload.query, force=payload.force)


@router.post("/cloud/music-library/sync")
def sync_sdk_cloud_music_library(payload: SdkCloudMusicLibraryRequest) -> dict[str, Any]:
    _require_sdk()
    return capability_service().sync_cloud_music_library(projects_root=payload.projects_root, dry_run=payload.dry_run)


@router.post("/smart-zoom/drafts")
def create_sdk_smart_zoom_draft(payload: SdkSmartZoomRequest) -> dict[str, Any]:
    _require_sdk()
    return capability_service().create_smart_zoom_draft(
        project_name=payload.project_name,
        video_path=payload.video_path,
        events_json_path=payload.events_json_path,
        zoom_scale=payload.zoom_scale,
        hold_seconds=payload.hold_seconds,
    )


@router.post("/movie-commentary/drafts")
def create_sdk_movie_commentary_draft(payload: SdkMovieCommentaryRequest) -> dict[str, Any]:
    _require_sdk()
    return capability_service().create_movie_commentary_draft(
        video_path=payload.video_path,
        storyboard_path=payload.storyboard_path,
        project_name=payload.project_name,
        bgm_path=payload.bgm_path,
        mask_path=payload.mask_path,
    )


if (SDK_ROOT / "assets").exists():
    router.mount("/assets", StaticFiles(directory=SDK_ROOT / "assets"), name="jianying_editor_sdk_assets")
