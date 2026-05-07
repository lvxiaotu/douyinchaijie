from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.routes.douyin import read_env_map, write_env_values
from backend.app.task_store import (
    get_jianying_assets_by_ids,
    jianying_asset_counts,
    list_jianying_assets,
    list_jianying_drafts,
    list_jianying_templates,
    save_jianying_draft,
    save_jianying_template,
    upsert_jianying_assets,
)
from integrations.jianying_draft.adapter import JianyingDraftAdapter
from integrations.jianying_draft.composition import normalize_composition
from integrations.jianying_draft.draft_validator import JianyingDraftValidator
from integrations.jianying_draft.template_manager import JianyingTemplateManager

router = APIRouter(prefix="/api/tools/jianying", tags=["jianying"])
logger = logging.getLogger(__name__)


class JianyingConfigPayload(BaseModel):
    draft_root: str = Field(default="")
    asset_library_dir: str = Field(default="./data/runtime/jianying/assets")
    output_dir: str = Field(default="./data/runtime/jianying/drafts")
    cache_dir: str = Field(default="")
    decrypt_mode: str = Field(default="manual", pattern="^(manual|exe|none)$")
    decrypt_tool: str = Field(default="")
    restore_tool: str = Field(default="")


class AssetScanRequest(BaseModel):
    asset_dir: str | None = Field(default=None)


class PlaceholderDraftRequest(BaseModel):
    name: str = Field(default="jianying_draft")


class DraftMediaItem(BaseModel):
    path: str
    type: str | None = Field(default=None)
    role: str | None = Field(default=None)
    track: str | None = Field(default=None)
    start_seconds: float | None = Field(default=None, ge=0)
    duration_seconds: float | None = Field(default=None, ge=0)


class DraftTextItem(BaseModel):
    text: str
    track: str | None = Field(default=None)
    start_seconds: float = Field(default=0, ge=0)
    duration_seconds: float | None = Field(default=None, ge=0)


class DraftCreateRequest(BaseModel):
    name: str = Field(default="jianying_draft")
    aspect_ratio: str = Field(default="9:16")
    default_media_duration_seconds: float = Field(default=3, ge=0.1, le=600)
    media: list[DraftMediaItem] = Field(default_factory=list)
    audio: list[DraftMediaItem] = Field(default_factory=list)
    texts: list[DraftTextItem] = Field(default_factory=list)
    composition: dict[str, Any] | None = Field(default=None)


class DraftFromAssetsRequest(BaseModel):
    name: str = Field(default="asset-draft")
    aspect_ratio: str = Field(default="9:16")
    asset_ids: list[str] = Field(default_factory=list)
    title_text: str = Field(default="")
    default_media_duration_seconds: float = Field(default=3, ge=0.1, le=600)


class DraftValidateRequest(BaseModel):
    draft_path: str
    name: str | None = Field(default=None)


class TemplateInspectRequest(BaseModel):
    template_path: str
    name: str | None = Field(default=None)


class TemplateRenderRequest(BaseModel):
    template_path: str
    output_path: str
    name: str | None = Field(default=None)
    text_replacements: dict[str, str] = Field(default_factory=dict)
    media_replacements: dict[str, str] = Field(default_factory=dict)


class DraftCryptoRequest(BaseModel):
    draft_path: str
    expected_output_path: str | None = Field(default=None)


class DraftCryptoConfirmRequest(BaseModel):
    draft_path: str
    expected_output_path: str | None = Field(default=None)


def adapter() -> JianyingDraftAdapter:
    return JianyingDraftAdapter()


def validator() -> JianyingDraftValidator:
    return JianyingDraftValidator()


def template_manager() -> JianyingTemplateManager:
    return JianyingTemplateManager()


def integration_error(exc: Exception) -> HTTPException:
    logger.exception("Jianying integration failed")
    return HTTPException(
        status_code=500,
        detail={
            "error_type": type(exc).__name__,
            "message": str(exc),
            "hint": "Check Jianying draft config, local paths, and decrypt mode.",
        },
    )


@router.get("/status")
def status() -> dict[str, Any]:
    return adapter().status()


@router.get("/config")
def get_config() -> dict[str, Any]:
    env = read_env_map()
    return {
        "draft_root": env.get("JIANYING_DRAFT_ROOT", ""),
        "asset_library_dir": env.get("JIANYING_ASSET_LIBRARY_DIR", "./data/runtime/jianying/assets"),
        "output_dir": env.get("JIANYING_OUTPUT_DIR", "./data/runtime/jianying/drafts"),
        "cache_dir": env.get("JIANYING_CACHE_DIR", ""),
        "decrypt_mode": env.get("JIANYING_DECRYPT_MODE", "manual"),
        "decrypt_tool": env.get("JIANYING_DECRYPT_TOOL", ""),
        "restore_tool": env.get("JIANYING_RESTORE_TOOL", ""),
    }


@router.post("/config")
def save_config(payload: JianyingConfigPayload) -> dict[str, Any]:
    try:
        write_env_values(
            {
                "JIANYING_DRAFT_ROOT": payload.draft_root,
                "JIANYING_ASSET_LIBRARY_DIR": payload.asset_library_dir,
                "JIANYING_OUTPUT_DIR": payload.output_dir,
                "JIANYING_CACHE_DIR": payload.cache_dir,
                "JIANYING_DECRYPT_MODE": payload.decrypt_mode,
                "JIANYING_DECRYPT_TOOL": payload.decrypt_tool,
                "JIANYING_RESTORE_TOOL": payload.restore_tool,
            }
        )
        return {"status": "ok", "config": get_config(), "tool_status": status()}
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/assets/scan")
def scan_assets(payload: AssetScanRequest) -> dict[str, Any]:
    try:
        scan = adapter().scan_assets(payload.asset_dir)
        saved = upsert_jianying_assets(scan.get("assets") or [], source="local")
        return {
            **scan,
            "saved_count": len(saved),
            "counts": jianying_asset_counts(),
        }
    except Exception as exc:
        raise integration_error(exc) from exc


@router.get("/assets")
def assets(
    asset_type: str | None = None,
    source: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    try:
        bounded_limit = max(1, min(limit, 500))
        return {
            "assets": list_jianying_assets(
                asset_type=asset_type,
                source=source,
                status=status,
                limit=bounded_limit,
            ),
            "counts": jianying_asset_counts(),
        }
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/drafts/create-placeholder")
def create_placeholder_draft(payload: PlaceholderDraftRequest) -> dict[str, Any]:
    try:
        result = adapter().create_placeholder_draft(payload.name)
        return save_jianying_draft(
            draft_id=result["name"],
            name=result["name"],
            draft_path=result["draft_path"],
            source="created",
            status=result["status"],
            meta={"placeholder": True},
        )
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/drafts/create")
def create_draft(payload: DraftCreateRequest) -> dict[str, Any]:
    try:
        request_payload = payload.model_dump()
        if payload.composition:
            request_payload = {
                **normalize_composition(payload.composition),
                "default_media_duration_seconds": payload.default_media_duration_seconds,
                "raw_composition": payload.composition,
            }
        result = adapter().create_draft(request_payload)
        saved = save_jianying_draft(
            draft_id=result["name"],
            name=result["name"],
            draft_path=result["draft_path"],
            source="created",
            status=result["status"],
            asset_report=result.get("asset_report") or {},
            meta={
                "dependency": result.get("dependency") or {},
                "canvas": result.get("canvas") or {},
                "request": request_payload,
            },
        )
        if result.get("status") == "dependency_missing":
            saved["note"] = "pyJianYingDraft is not installed yet; created a placeholder draft directory."
        return saved
    except Exception as exc:
        raise integration_error(exc) from exc


@router.get("/drafts")
def drafts(status: str | None = None, limit: int = 100) -> dict[str, Any]:
    try:
        bounded_limit = max(1, min(limit, 500))
        return {"drafts": list_jianying_drafts(status=status, limit=bounded_limit)}
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/drafts/create-from-assets")
def create_draft_from_assets(payload: DraftFromAssetsRequest) -> dict[str, Any]:
    try:
        assets = get_jianying_assets_by_ids(payload.asset_ids)
        media = []
        for asset in assets:
            asset_type = asset.get("type") or ""
            if asset_type not in {"video", "image", "rendered"}:
                continue
            media.append(
                {
                    "path": asset.get("path") or "",
                    "type": "video" if asset_type == "rendered" else asset_type,
                    "role": asset.get("source") or "",
                    "track": "video",
                    "duration_seconds": payload.default_media_duration_seconds,
                }
            )
        texts = []
        if payload.title_text:
            texts.append(
                {
                    "text": payload.title_text,
                    "track": "text",
                    "start_seconds": 0,
                    "duration_seconds": payload.default_media_duration_seconds,
                }
            )
        request_payload = {
            "name": payload.name,
            "aspect_ratio": payload.aspect_ratio,
            "default_media_duration_seconds": payload.default_media_duration_seconds,
            "media": media,
            "audio": [],
            "texts": texts,
        }
        result = adapter().create_draft(request_payload)
        saved = save_jianying_draft(
            draft_id=result["name"],
            name=result["name"],
            draft_path=result["draft_path"],
            source="created",
            status=result["status"],
            asset_report=result.get("asset_report") or {},
            meta={
                "dependency": result.get("dependency") or {},
                "canvas": result.get("canvas") or {},
                "request": request_payload,
                "assets": assets,
            },
        )
        if result.get("status") == "dependency_missing":
            saved["note"] = "pyJianYingDraft is not installed yet; created a placeholder draft directory."
        return saved
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/drafts/validate")
def validate_draft(payload: DraftValidateRequest) -> dict[str, Any]:
    try:
        report = validator().validate(payload.draft_path)
        draft_name = payload.name or report.get("draft_path", "").rstrip("/\\").split("\\")[-1].split("/")[-1] or "jianying_draft"
        status = "validated"
        if report.get("needs_decrypt"):
            status = "needs_decrypt"
        elif report.get("assets", {}).get("missing"):
            status = "has_missing_assets"
        saved = save_jianying_draft(
            draft_id=draft_name,
            name=draft_name,
            draft_path=payload.draft_path,
            source="imported",
            status=status,
            asset_report=report.get("assets") or {},
            meta={"validation": report},
        )
        return {"status": status, "report": report, "draft": saved}
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/templates/inspect")
def inspect_template(payload: TemplateInspectRequest) -> dict[str, Any]:
    try:
        report = template_manager().inspect(payload.template_path)
        template_name = payload.name or payload.template_path.rstrip("/\\").split("\\")[-1].split("/")[-1] or "jianying_template"
        saved = save_jianying_template(
            template_id=template_name,
            name=template_name,
            template_path=payload.template_path,
            text_slots=report.get("text_slots") or [],
            media_slots=report.get("media_slots") or [],
            audio_slots=report.get("audio_slots") or [],
            required_assets=report.get("required_assets") or {},
            status=report.get("status") or "unknown",
            meta={"inspect": report},
        )
        return {"status": report.get("status"), "report": report, "template": saved}
    except Exception as exc:
        raise integration_error(exc) from exc


@router.get("/templates")
def templates(status: str | None = None, limit: int = 100) -> dict[str, Any]:
    try:
        bounded_limit = max(1, min(limit, 500))
        return {"templates": list_jianying_templates(status=status, limit=bounded_limit)}
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/templates/render")
def render_template(payload: TemplateRenderRequest) -> dict[str, Any]:
    try:
        report = template_manager().render(
            template_path=payload.template_path,
            output_path=payload.output_path,
            text_replacements=payload.text_replacements,
            media_replacements=payload.media_replacements,
        )
        draft_name = payload.name or payload.output_path.rstrip("/\\").split("\\")[-1].split("/")[-1] or "rendered_template"
        saved = save_jianying_draft(
            draft_id=draft_name,
            name=draft_name,
            draft_path=payload.output_path,
            source="template_render",
            status=report.get("status") or "unknown",
            asset_report=(report.get("validation") or {}).get("assets") or {},
            meta={
                "template_render": report,
                "template_path": payload.template_path,
                "text_replacements": payload.text_replacements,
                "media_replacements": payload.media_replacements,
            },
        )
        return {"status": report.get("status"), "report": report, "draft": saved}
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/decrypt/prepare")
def prepare_decrypt(payload: DraftCryptoRequest) -> dict[str, Any]:
    try:
        plan = adapter().decrypt.prepare_decrypt(payload.draft_path, payload.expected_output_path)
        return {"status": plan.state, "manual_action": plan.to_dict()}
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/decrypt/check")
def check_decrypt(payload: DraftCryptoRequest) -> dict[str, Any]:
    try:
        report = validator().validate(payload.expected_output_path or payload.draft_path)
        status = "decrypted_ready" if report.get("readable_json") else "waiting_for_decrypt"
        return {"status": status, "report": report}
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/decrypt/confirm")
def confirm_decrypt(payload: DraftCryptoConfirmRequest) -> dict[str, Any]:
    try:
        report = validator().validate(payload.expected_output_path or payload.draft_path)
        status = "decrypted_ready" if report.get("readable_json") else "waiting_for_decrypt"
        return {"status": status, "confirmed": status == "decrypted_ready", "report": report}
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/restore/prepare")
def prepare_restore(payload: DraftCryptoRequest) -> dict[str, Any]:
    try:
        plan = adapter().decrypt.prepare_restore(payload.draft_path, payload.expected_output_path)
        return {"status": plan.state, "manual_action": plan.to_dict()}
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/restore/check")
def check_restore(payload: DraftCryptoRequest) -> dict[str, Any]:
    try:
        report = validator().validate(payload.expected_output_path or payload.draft_path)
        status = "restored_ready" if report.get("exists") else "waiting_for_restore"
        return {"status": status, "report": report}
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/restore/confirm")
def confirm_restore(payload: DraftCryptoConfirmRequest) -> dict[str, Any]:
    try:
        report = validator().validate(payload.expected_output_path or payload.draft_path)
        status = "restored_ready" if report.get("exists") else "waiting_for_restore"
        return {"status": status, "confirmed": status == "restored_ready", "report": report}
    except Exception as exc:
        raise integration_error(exc) from exc
