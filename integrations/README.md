# integrations

这里用于接入 GitHub 开源项目或本地脚本。建议每个项目一个目录，例如：

```text
integrations/
├─ comfyui/
│  ├─ adapter.py
│  ├─ config.example.json
│  └─ README.md
└─ douyin_favorites/
   ├─ adapter.py
   ├─ config.example.json
   └─ README.md
```

每个适配器只负责包装第三方项目：

- 安装位置或仓库地址
- 配置项
- 输入参数
- 执行入口
- 日志读取
- 结果解析

后端 API 和任务队列不要直接依赖第三方项目内部实现，优先调用适配器暴露的稳定方法。

## 剪映链路职责边界

剪映相关代码拆成三层，避免一个 `sdk` 名称同时承担多个含义：

```text
video_pipeline
  负责剧本生成、自然语言解析后的结构化 `script.json` 保存。

jianying_draft
  负责把 `script.json` 组装成剪映草稿，可选择 `pyJianYingDraft` 或 JyProject。

jianying_editor_skill
  负责上游 JianYing Editor Skill 的能力发现、环境体检、CLI 封装和本项目桥接逻辑。
```

约定：

- 剧本生成侧使用 `generation_mode=skill_contract` 表示 Skill 规则生成。
- 草稿生成侧使用 `engine=sdk` 表示 JyProject 草稿生成。
- 不要从路由层直接 import `sdks/jianying-editor-skill/scripts/*`。
- 不要把本项目桥接脚本写进 `sdks/jianying-editor-skill/`，该目录按上游快照治理。
- `GET /api/tools/jianying-editor-sdk/status` 只做轻量能力发现，不创建诊断草稿。
- 需要主动验收 SDK 最小链路时，显式调用 `POST /api/tools/jianying-editor-sdk/diagnostics/deep`。
- 能力矩阵由后端返回 `capability_matrix`，覆盖草稿创建、诊断、草稿查看、素材搜索、云素材、云音乐、TTS、Web VFX、录屏、智能缩放、电影解说和自动导出。
