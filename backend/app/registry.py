from .models import IntegrationDefinition, JobSummary, LibraryItem, Metric, ToolDefinition, WorkbenchSnapshot


def get_workbench() -> WorkbenchSnapshot:
    """Return the current workbench snapshot.

    This is intentionally simple for now. Later, replace these lists with a
    database-backed registry and load tool definitions from integration modules.
    """
    tools = [
        ToolDefinition(
            id="douyin-favorites",
            icon="抖",
            name="抖音收藏分析器",
            desc="接入 Douyin_TikTok_Download_API：用户主页、作品详情、收藏视频下载。",
            status="ready",
            updated="已预留 API",
            tags=["视频", "采集", "分析"],
            integration_id="douyin-download-api",
        ),
        ToolDefinition(
            id="video-analyzer",
            icon="AI",
            name="AI 视频拆解",
            desc="从已采集视频发起拆解任务，预留 Gemini、GPT 和本地多模态模型接入。",
            status="ready",
            updated="已接入任务骨架",
            tags=["AI", "视频", "拆解"],
            integration_id="ai-video-analysis",
        ),
        ToolDefinition(
            id="prompt-reverse",
            icon="PR",
            name="AI 提示词反推",
            desc="从已采集视频反推出可复用的视频生成、图像生成和脚本提示词。",
            status="ready",
            updated="已接入任务骨架",
            tags=["AI", "提示词", "视频"],
            integration_id="ai-prompt-reverse",
        ),
        ToolDefinition(
            id="draft-generator",
            icon="JD",
            name="???????",
            desc="?? AI ????????? draft JSON?????? pyJianYingDraft ???",
            status="ready",
            updated="??? AI JSON ?? + ????",
            tags=["??", "??", "AI", "JSON"],
            integration_id="jianying-draft",
        ),
        ToolDefinition(
            id="jianying-editor-sdk",
            icon="JY",
            name="剪映 Editor Skill SDK",
            desc="接入 luoluoluo22/jianying-editor-skill，先暴露 JyProject、草稿检查、素材搜索、自动导出和网页开发者指南入口。",
            status="ready",
            updated="已克隆到 sdks/jianying-editor-skill",
            tags=["剪映", "SDK", "自动化", "Python"],
            integration_id="jianying-editor-sdk",
        ),
    ]

    return WorkbenchSnapshot(
        metrics=[
            Metric(label="运行中任务", value="2", hint="采集与 AI 任务统一走后台任务中心"),
            Metric(label="已接入工具", value=str(len(tools)), hint="保留抖音采集、AI 视频拆解、AI 提示词反推"),
            Metric(label="归档内容", value="128", hint="AI 拆解与提示词结果可沉淀到素材库"),
            Metric(label="失败提醒", value="1", hint="Cookie 可能需要更新"),
        ],
        tools=tools,
        jobs=[
            JobSummary(
                id="job-sync-douyin",
                name="同步抖音收藏",
                tool="抖音收藏分析器",
                status="running",
                progress=62,
                updated="18:22",
            ),
            JobSummary(
                id="job-video-analyze",
                name="分析本地视频素材",
                tool="AI 视频拆解",
                status="running",
                progress=38,
                updated="18:18",
            ),
            JobSummary(
                id="job-cookie-check",
                name="检查采集 Cookie",
                tool="抖音收藏分析器",
                status="error",
                progress=100,
                updated="17:55",
            ),
        ],
        library=[
            LibraryItem(
                id="lib-analysis-001",
                title="AI 视频拆解归档示例",
                type="拆解归档",
                desc="沉淀爆款结构、钩子、节奏和可复用公式。",
                tags=["AI", "拆解"],
            ),
            LibraryItem(
                id="lib-prompt-001",
                title="AI 提示词反推归档示例",
                type="提示词归档",
                desc="保留 master prompt、镜头提示词和风格关键词，便于复用。",
                tags=["AI", "提示词"],
            ),
        ],
        integrations=[
            IntegrationDefinition(
                id="douyin-download-api",
                name="Douyin_TikTok_Download_API 适配器",
                desc="仅接入用户主页信息、作品详情、收藏列表视频下载。",
                kind="python",
                status="ready",
                repo_url="https://github.com/Evil0ctal/Douyin_TikTok_Download_API",
            ),
            IntegrationDefinition(
                id="ai-video-analysis",
                name="AI 视频拆解适配器",
                desc="从采集视频创建拆解任务，统一输出摘要、时间线、钩子、画面、声音和提示词。",
                kind="python",
                status="ready",
            ),
            IntegrationDefinition(
                id="ai-prompt-reverse",
                name="AI 提示词反推适配器",
                desc="从采集视频创建提示词反推任务，输出 master prompt、negative prompt、分镜提示词和风格关键词。",
                kind="python",
                status="ready",
            ),
            IntegrationDefinition(
                id="jianying-draft",
                name="???????",
                desc="?? pyJianYingDraft ??????? draft JSON ????? script.json ???????",
                kind="python",
                status="ready",
                repo_url="https://github.com/GuanYixuan/pyJianYingDraft",
            ),
            IntegrationDefinition(
                id="jianying-editor-sdk",
                name="剪映 Editor Skill SDK",
                desc="本地 SDK 位于 sdks/jianying-editor-skill，提供 JyProject Python API、CLI 脚本和官方网页指南。",
                kind="python",
                status="ready",
                repo_url="https://github.com/luoluoluo22/jianying-editor-skill",
            ),
        ],
    )
