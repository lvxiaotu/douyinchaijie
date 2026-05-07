from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class DecryptPlan:
    mode: str
    state: str
    source_path: str
    expected_output_path: str
    instructions: list[str]
    can_launch_exe: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "state": self.state,
            "source_path": self.source_path,
            "expected_output_path": self.expected_output_path,
            "instructions": self.instructions,
            "can_launch_exe": self.can_launch_exe,
        }


class JianyingDecryptAdapter:
    """Coordinate decrypt/restore steps that may require a manual external exe."""

    def __init__(
        self,
        *,
        mode: str = "manual",
        decrypt_tool: str = "",
        restore_tool: str = "",
    ):
        self.mode = (mode or "manual").lower()
        self.decrypt_tool = decrypt_tool
        self.restore_tool = restore_tool

    def validate_config(self) -> list[str]:
        errors: list[str] = []
        if self.mode not in {"manual", "exe", "none"}:
            errors.append("JIANYING_DECRYPT_MODE must be one of manual, exe, none")
        if self.mode == "exe" and self.decrypt_tool and not Path(self.decrypt_tool).exists():
            errors.append("JIANYING_DECRYPT_TOOL does not exist")
        if self.mode == "exe" and self.restore_tool and not Path(self.restore_tool).exists():
            errors.append("JIANYING_RESTORE_TOOL does not exist")
        return errors

    def prepare_decrypt(self, draft_path: str, expected_output_path: str | None = None) -> DecryptPlan:
        output_path = expected_output_path or draft_path
        return DecryptPlan(
            mode=self.mode,
            state="waiting_for_decrypt" if self.mode != "none" else "decrypted_ready",
            source_path=draft_path,
            expected_output_path=output_path,
            instructions=[
                "Use the external Jianying decrypt exe to process the draft if required.",
                "Confirm in the workbench after the decrypted draft_content.json is readable.",
            ],
            can_launch_exe=bool(self.mode == "exe" and self.decrypt_tool),
        )

    def prepare_restore(self, draft_path: str, expected_output_path: str | None = None) -> DecryptPlan:
        output_path = expected_output_path or draft_path
        return DecryptPlan(
            mode=self.mode,
            state="waiting_for_restore" if self.mode != "none" else "restored_ready",
            source_path=draft_path,
            expected_output_path=output_path,
            instructions=[
                "Use the external Jianying restore exe to rebuild the draft if required.",
                "Confirm in the workbench after Jianying can read the restored draft.",
            ],
            can_launch_exe=bool(self.mode == "exe" and self.restore_tool),
        )

