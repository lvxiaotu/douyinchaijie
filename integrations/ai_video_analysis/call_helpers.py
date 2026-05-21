from __future__ import annotations

from inspect import Parameter, signature
from typing import Any, Callable


def call_generate_text_hook(
    hook: Callable[..., str],
    prompt: str,
    *,
    action: str,
    image_paths: list[str] | None = None,
    route: Any | None = None,
) -> str:
    try:
        sig = signature(hook)
    except (TypeError, ValueError):
        sig = None
    if sig is not None:
        params = sig.parameters
        if "route" in params or any(param.kind == Parameter.VAR_KEYWORD for param in params.values()):
            return hook(prompt, action=action, image_paths=image_paths, route=route)
    return hook(prompt, action=action, image_paths=image_paths)
