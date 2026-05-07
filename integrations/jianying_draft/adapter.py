from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from integrations.base import IntegrationAdapter, IntegrationManifest
from integrations.jianying_draft.asset_manager import JianyingAssetManager
from integrations.jianying_draft.decrypt_adapter import JianyingDecryptAdapter
from integrations.jianying_draft.draft_engine import JianyingDraftEngine


DEFAULT_ASSET_LIBRARY_DIR = Path("data/runtime/jianying/assets")
DEFAULT_OUTPUT_DIR = Path("data/runtime/jianying/drafts")


class JianyingDraftAdapter(IntegrationAdapter):
    manifest = IntegrationManifest(
        id="jianying-draft",
        name="剪映草稿工具链",
        description="管理剪映草稿、素材库、模板和外部解密/还原流程。",
        repo_url="https://github.com/GuanYixuan/pyJianYingDraft",
        tags=["jianying", "video", "draft", "assets"],
        config_schema={
            "draft_root": "剪映草稿根目录，可为空",
            "asset_library_dir": "本地素材库目录",
            "output_dir": "生成草稿输出目录",
            "decrypt_mode": "manual | exe | none",
            "decrypt_tool": "外部解密 exe 路径",
            "restore_tool": "外部还原 exe 路径",
        },
    )

    def __init__(self, config: dict[str, Any] | None = None):
        load_dotenv()
        self.config = config or {}
        self.draft_root = self._value("draft_root", "JIANYING_DRAFT_ROOT", "")
        self.asset_library_dir = Path(
            self._value("asset_library_dir", "JIANYING_ASSET_LIBRARY_DIR", str(DEFAULT_ASSET_LIBRARY_DIR))
        )
        self.output_dir = Path(self._value("output_dir", "JIANYING_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR)))
        self.decrypt_mode = self._value("decrypt_mode", "JIANYING_DECRYPT_MODE", "manual")
        self.decrypt_tool = self._value("decrypt_tool", "JIANYING_DECRYPT_TOOL", "")
        self.restore_tool = self._value("restore_tool", "JIANYING_RESTORE_TOOL", "")
        self.cache_dir = self._value("cache_dir", "JIANYING_CACHE_DIR", "")

        self.assets = JianyingAssetManager()
        self.drafts = JianyingDraftEngine(str(self.output_dir), draft_root=self.draft_root)
        self.decrypt = JianyingDecryptAdapter(
            mode=self.decrypt_mode,
            decrypt_tool=self.decrypt_tool,
            restore_tool=self.restore_tool,
        )

    def _value(self, config_key: str, env_key: str, default: str) -> str:
        return str(self.config.get(config_key) or os.getenv(env_key) or default)

    def validate_config(self, config: dict[str, Any] | None = None) -> list[str]:
        cfg = {**self.config, **(config or {})}
        errors: list[str] = []
        draft_root = str(cfg.get("draft_root") or self.draft_root or "")
        asset_library_dir = Path(str(cfg.get("asset_library_dir") or self.asset_library_dir))
        output_dir = Path(str(cfg.get("output_dir") or self.output_dir))
        decrypt_mode = str(cfg.get("decrypt_mode") or self.decrypt_mode or "manual")

        if draft_root and not Path(draft_root).exists():
            errors.append("JIANYING_DRAFT_ROOT does not exist")
        if decrypt_mode not in {"manual", "exe", "none"}:
            errors.append("JIANYING_DECRYPT_MODE must be one of manual, exe, none")
        if asset_library_dir.exists() and not asset_library_dir.is_dir():
            errors.append("JIANYING_ASSET_LIBRARY_DIR is not a directory")
        if output_dir.exists() and not output_dir.is_dir():
            errors.append("JIANYING_OUTPUT_DIR is not a directory")
        errors.extend(self.decrypt.validate_config())
        return errors

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = payload.get("action")
        if action == "scan_assets":
            return self.scan_assets(str(payload.get("asset_dir") or self.asset_library_dir))
        if action == "create_placeholder_draft":
            return self.create_placeholder_draft(str(payload.get("name") or "jianying_draft"))
        if action == "create_draft":
            return self.create_draft(payload)
        raise ValueError(f"Unsupported Jianying draft action: {action}")

    def status(self) -> dict[str, Any]:
        errors = self.validate_config()
        return {
            "id": self.manifest.id,
            "name": self.manifest.name,
            "repo_url": self.manifest.repo_url,
            "ready": not errors,
            "errors": errors,
            "draft_root": self.draft_root,
            "asset_library_dir": str(self.asset_library_dir),
            "output_dir": str(self.output_dir),
            "cache_dir": self.cache_dir,
            "decrypt_mode": self.decrypt_mode,
            "has_decrypt_tool": bool(self.decrypt_tool),
            "has_restore_tool": bool(self.restore_tool),
            "dependencies": self.drafts.dependency_status(),
        }

    def config_snapshot(self) -> dict[str, Any]:
        return {
            "draft_root": self.draft_root,
            "asset_library_dir": str(self.asset_library_dir),
            "output_dir": str(self.output_dir),
            "cache_dir": self.cache_dir,
            "decrypt_mode": self.decrypt_mode,
            "decrypt_tool": self.decrypt_tool,
            "restore_tool": self.restore_tool,
        }

    def scan_assets(self, asset_dir: str | None = None) -> dict[str, Any]:
        return self.assets.scan_directory(asset_dir or str(self.asset_library_dir))

    def create_placeholder_draft(self, name: str) -> dict[str, Any]:
        return self.drafts.create_placeholder_draft(name)

    def create_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.drafts.create_draft(payload)
