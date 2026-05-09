from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = ROOT / "sdks" / "jianying-editor-skill"
SDK_SCRIPTS_DIR = SDK_ROOT / "scripts"


@dataclass
class SdkCliResult:
    ok: bool
    exit_code: int | None
    command: list[str]
    parsed: dict[str, Any]
    stdout: str
    stderr: str
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "exit_code": self.exit_code,
            "command": self.command,
            "data": self.parsed,
            "stdout_tail": self.stdout.strip().splitlines()[-20:],
            "stderr_tail": self.stderr.strip().splitlines()[-20:],
            "error": self.error,
        }


class SdkCliRunner:
    """Run jianying-editor-skill CLI scripts through one encoded subprocess path."""

    def __init__(self, sdk_root: str | Path = SDK_ROOT):
        self.sdk_root = Path(sdk_root)
        self.scripts_dir = self.sdk_root / "scripts"

    def run(self, script_name: str, args: list[str], *, timeout_seconds: int = 30) -> SdkCliResult:
        script_path = self.scripts_dir / script_name
        command = [sys.executable, str(script_path), *args]
        if not script_path.exists():
            return SdkCliResult(
                ok=False,
                exit_code=None,
                command=command,
                parsed={},
                stdout="",
                stderr="",
                error=f"SDK CLI not found: {script_path}",
            )

        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            completed = subprocess.run(
                command,
                cwd=str(self.scripts_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            return SdkCliResult(
                ok=False,
                exit_code=None,
                command=command,
                parsed={},
                stdout=stdout,
                stderr=stderr,
                error=f"Timed out after {timeout_seconds}s",
            )
        except Exception as exc:
            return SdkCliResult(
                ok=False,
                exit_code=None,
                command=command,
                parsed={},
                stdout="",
                stderr="",
                error=f"{type(exc).__name__}: {exc}",
            )

        parsed = self._parse_json(completed.stdout)
        parsed_ok = bool(parsed.get("ok")) if parsed else completed.returncode == 0
        return SdkCliResult(
            ok=completed.returncode == 0 and parsed_ok,
            exit_code=completed.returncode,
            command=command,
            parsed=parsed,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def _parse_json(self, text: str) -> dict[str, Any]:
        stripped = text.strip()
        if not stripped:
            return {}
        try:
            data = json.loads(stripped)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            pass

        for line in reversed([line.strip() for line in stripped.splitlines() if line.strip()]):
            if not line.startswith("{"):
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            return data if isinstance(data, dict) else {}

        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(stripped[start : end + 1])
            except json.JSONDecodeError:
                return {}
            return data if isinstance(data, dict) else {}
        return {}
