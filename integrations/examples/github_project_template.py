from typing import Any

from integrations.base import IntegrationAdapter, IntegrationManifest


class GithubProjectTemplateAdapter(IntegrationAdapter):
    manifest = IntegrationManifest(
        id="github-project-template",
        name="GitHub 项目模板",
        description="复制这个类来包装新的开源项目。",
        tags=["template", "github"],
        config_schema={
            "repo_url": "GitHub 仓库地址",
            "local_path": "本地安装路径",
            "entrypoint": "运行入口，例如 python main.py",
        },
    )

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = []
        for key in ["repo_url", "local_path", "entrypoint"]:
            if not config.get(key):
                errors.append(f"Missing config: {key}")
        return errors

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "not_implemented",
            "message": "复制 integrations/examples/github_project_template.py 后实现真实运行逻辑。",
            "payload": payload,
        }
