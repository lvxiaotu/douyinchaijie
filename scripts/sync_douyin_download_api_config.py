from pathlib import Path

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
UPSTREAM_CONFIG = (
    ROOT
    / "integrations"
    / "douyin_download_api"
    / "vendor"
    / "Douyin_TikTok_Download_API"
    / "crawlers"
    / "douyin"
    / "web"
    / "config.yaml"
)


def main() -> None:
    env = dotenv_values(ENV_PATH)
    cookie = env.get("DY_COOKIES")
    if not cookie:
        raise SystemExit("DY_COOKIES is empty in .env")
    if not UPSTREAM_CONFIG.exists():
        raise SystemExit(f"Upstream config not found: {UPSTREAM_CONFIG}")

    lines = UPSTREAM_CONFIG.read_text(encoding="utf-8").splitlines()
    updated = []
    changed = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("Cookie:"):
            indent = line[: len(line) - len(stripped)]
            updated.append(f"{indent}Cookie: {cookie}")
            changed = True
        else:
            updated.append(line)

    if not changed:
        raise SystemExit("Cookie field not found in upstream config.yaml")

    UPSTREAM_CONFIG.write_text("\n".join(updated) + "\n", encoding="utf-8")
    print(f"Updated Cookie in {UPSTREAM_CONFIG}")


if __name__ == "__main__":
    main()
