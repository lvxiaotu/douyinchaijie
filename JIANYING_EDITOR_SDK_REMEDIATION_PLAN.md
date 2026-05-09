# JianYing Editor SDK 修复方案

> 2026-05-09 执行状态：前三批整改已补齐。普通 `/status` 已改为无副作用轻量能力发现；深度诊断拆到显式 `POST /api/tools/jianying-editor-sdk/diagnostics/deep`；能力矩阵已覆盖 `can_create_draft`、`can_validate_draft`、`can_inspect_draft`、`can_asset_search`、`can_cloud_media`、`can_cloud_music`、`can_tts`、`can_web_vfx`、`can_record_screen`、`can_smart_zoom`、`can_movie_commentary`、`can_auto_export`；高阶能力已通过 `sdk_capability_service.py` 暴露；自动导出增加 Windows + `uiautomation` + 剪映 `<= 5.9` 门禁；新增 `tests/test_jianying_editor_sdk.py` 覆盖状态和能力矩阵。

更新时间：2026-05-09

## 目标

1. 让页面宣称的能力、后端状态、实际可运行行为一致。
2. 让 SDK 接入可复现，不依赖本机私有目录和未提交文件。
3. 拆清“剧本生成”和“剪映草稿拼装”两条链路，避免 `sdk` 语义混乱。
4. 给关键链路补上自动校验，降低假阳性和环境漂移风险。

## 总体判断

当前实现已经能完成最基础的 `JyProject` 草稿拼装，但还不能算“全面接入上游 SDK”。主要问题集中在：

- 能力声明大于真实接入范围。
- `sdk` 模式语义混杂，前端和后端存在误导。
- 健康状态判断过于乐观，缺少真实体检。
- SDK 目录治理方式不可复现。
- 部分结果回报存在“看起来成功，实际上没做事”的假阳性。

## 分阶段修复方案

### 阶段一：先止血

目标：先消除最强误导项和假成功项。

#### 1. 下线或重命名误导性的 “SDK 接入生成”

当前 `generation_mode="sdk"` 给人的理解是“通过上游 SDK 生成结构化剧本”，但实际只是走了本地桥接模板逻辑。

建议：

- 前端将“`SDK 接入生成`”临时改名为“`Skill 规则生成`”或“`本地 Skill 合约生成`”。
- 如果短期不准备做真实差异化，直接隐藏该选项。
- 明确区分：
  - `script generation`
  - `draft generation via JyProject`

涉及文件：

- `src/main.jsx`
- `src/workbenchSeed.js`
- `src/services/api.js`
- `integrations/jianying_editor_skill/sdk_script_generator.py`

#### 2. 把 SDK `ready` 改为“主动体检”

当前状态页主要依赖“文件是否存在”和“模块能否导入”，不足以说明 SDK 可用。

建议在状态接口中增加真实检查项：

1. `JyProject` 能否导入。
2. `api_validator.py --json` 能否成功执行。
3. 最小草稿能否创建成功。
4. SDK 关键依赖是否存在。
5. 当前平台是否满足特定能力要求，例如：
   - 自动导出是否仅在 Windows 且剪映 <= 5.9。

返回结构建议从：

```json
{
  "ready": true
}
```

升级为：

```json
{
  "ready": false,
  "checks": {
    "jyproject_import": {"ok": true},
    "api_validator": {"ok": false, "message": "..."},
    "smoke_draft_create": {"ok": true},
    "sdk_requirements": {"ok": false, "missing": ["playwright"]}
  },
  "capabilities": {
    "can_create_draft": true,
    "can_validate_draft": true,
    "can_tts": false,
    "can_web_vfx": false,
    "can_auto_export": false
  },
  "warnings": []
}
```

涉及文件：

- `backend/app/routes/jianying_editor_sdk.py`
- `integrations/jianying_draft/sdk_engine.py`

#### 3. 修复 `applied_edits` 假成功

当前实现里，即使没有真正应用转场、动画、运镜，也可能被记成“已应用”。

建议：

- `applied_edits` 只记录真正执行成功的编辑项。
- 新增 `failed_edits`，用于回传：
  - 原始输入值
  - 映射目标
  - 失败原因
- 前端改为分别展示：
  - 已成功应用
  - 未命中 / 未支持

返回结构建议：

```json
{
  "applied_edits": [
    {"role": "scene_1", "animation": "zoom_in"}
  ],
  "failed_edits": [
    {"role": "scene_2", "transition": "custom_fade", "reason": "enum_not_found"}
  ]
}
```

涉及文件：

- `integrations/jianying_draft/sdk_engine.py`
- `src/main.jsx`

### 阶段二：建立稳定接入骨架

目标：把当前“本地凑起来能跑”的模式，变成可复现、可升级、可维护的正式接入。

#### 4. 规范 SDK 目录治理方式

`sdks/jianying-editor-skill` 当前是独立 Git 仓库，而且业务逻辑依赖其中的本地未跟踪文件，这会导致：

- 换机器失效
- 拉取更新后行为漂移
- 无法准确复盘线上/本地差异

建议二选一：

1. `vendor snapshot` 模式
   - 将当前使用的 SDK 版本固定成只读快照。
   - 项目内桥接逻辑不允许直接写入 SDK 目录。
2. `git submodule` 模式
   - 使用明确 commit 锁定上游版本。
   - 本项目所有补丁都在外层桥接层实现。

如果优先考虑稳定交付，建议先采用 `vendor snapshot`。

#### 5. 把桥接脚本移出 SDK 目录

当前 `script_input_sdk_adapter.py` 放在 SDK 仓库内部，且未被上游管理，风险很高。

建议迁移到本项目，例如：

- `integrations/jianying_editor_skill/sdk_bridge.py`
- `integrations/jianying_editor_skill/script_contract_adapter.py`

原则：

- 上游 SDK 目录只保留第三方内容。
- 业务扩展全部放在本仓库。
- 外部升级 SDK 时，不再覆盖自定义逻辑。

#### 6. 拆分依赖治理

当前顶层 `requirements.txt` 只覆盖了 `pyJianYingDraft`，但实际 SDK 还需要：

- `uiautomation`
- `playwright`
- `pynput`
- `edge-tts`
- `opencv-python`
- `numpy`
- 其他 SDK 自带脚本依赖

建议：

- 新建 `requirements-base.txt`
- 新建 `requirements-sdk.txt`
- 根目录 `README` 和状态接口统一说明“安装到什么程度，可以解锁哪些能力”

能力与依赖之间要明确映射，例如：

- `can_create_draft` 依赖 `pyJianYingDraft`
- `can_web_vfx` 依赖 `playwright`
- `can_auto_export` 依赖 `uiautomation`

#### 7. 彻底拆清三层职责

建议按职责重构：

1. `integrations/video_pipeline/`
   - 负责 LLM 剧本生成
   - 输出标准化 `script.json`

2. `integrations/jianying_draft/`
   - 负责将 `script.json` 转换为剪映草稿
   - 可选择 `pyJianYingDraft` 或 `JyProject` 作为草稿引擎

3. `integrations/jianying_editor_skill/`
   - 负责上游 SDK 能力桥接
   - 提供 CLI 封装、能力发现、环境检测、桥接逻辑

不要再让一个 `sdk` 字段同时承担“剧本生成方式”和“草稿生成引擎”两层含义。

#### 8. 重定义 `generation_mode`

建议统一为三种明确语义：

- `local_llm`
  - 本地项目的普通结构化剧本生成
- `skill_contract`
  - 使用 JianYing Skill 的输入约束/规则进行结构化剧本生成
- `sdk_draft`
  - 用 `JyProject` 生成剪映草稿

如果暂时没有真实差异，就删除剧本侧的 `sdk` 模式，避免误导。

### 阶段三：补齐真正缺失的 SDK 能力

目标：从“只接入了 JyProject 的薄封装”，升级为“按上游能力矩阵选择性接入”。

#### 9. 建立 SDK 能力矩阵

建议把上游能力整理成结构化矩阵：

- `can_create_draft`
- `can_validate_draft`
- `can_inspect_draft`
- `can_asset_search`
- `can_cloud_media`
- `can_cloud_music`
- `can_tts`
- `can_web_vfx`
- `can_record_screen`
- `can_smart_zoom`
- `can_movie_commentary`
- `can_auto_export`

每项能力都应有：

- 依赖
- 平台限制
- 调用入口
- 验收方式

#### 10. 增加 CLI Runner 与 Capability Service

建议新增：

- `integrations/jianying_editor_skill/sdk_cli_runner.py`
- `integrations/jianying_editor_skill/sdk_capability_service.py`

职责如下：

`sdk_cli_runner.py`

- 统一运行：
  - `api_validator.py`
  - `asset_search.py`
  - `draft_inspector.py`
  - `auto_exporter.py`
- 统一处理：
  - 编码
  - 超时
  - 输出格式
  - exit code

`sdk_capability_service.py`

- 对外提供稳定接口
- 将 CLI 和 Python API 封装成业务可调用能力
- 不让路由层直接碰第三方脚本细节

#### 11. 按优先级接入缺失能力

建议顺序：

1. `draft_inspector`
2. `asset_search`
3. `auto_exporter`
4. `web_vfx`
5. `recording + smart_zoom`
6. `movie_commentary_builder`

原因：

- 前三项更稳定，且能快速提升可见能力。
- 后三项依赖更多、平台限制更强，适合后置。

## 编码与平台兼容修复

### 12. 修复 Windows 编码问题

已观察到 SDK 自检脚本可能因 Windows `gbk/cp936` 输出编码失败而报错。

建议分两层修：

#### 运行层

所有通过子进程执行 SDK CLI 的地方，统一注入：

- `PYTHONUTF8=1`
- `PYTHONIOENCODING=utf-8`

#### 输出层

- 机器可读输出不要依赖 emoji。
- CLI 成功/失败判断以：
  - exit code
  - JSON 结构
  - `ok/code/reason`
  为准。

#### 接口层

- 把“可导入”与“可运行”分开汇报。
- 不要让编码问题把真实功能错误掩盖掉。

## 测试与验收方案

### 13. 单元测试

建议补齐：

- SDK 状态体检测试
- `script_input` / contract 桥接测试
- 编辑映射测试
- `applied_edits` / `failed_edits` 测试
- 依赖缺失分支测试
- 编码兼容测试

### 14. 集成测试

建议增加：

1. 最小素材 -> `JyProject` 草稿生成
2. `create-from-script`
3. `api_validator.py --json`
4. `draft_inspector.py`
5. 字幕/音频是否落到正确轨道

### 15. Windows 手工验收链路

建议固定一条人工验收链路：

1. 生成 `script.json`
2. 生成 SDK 草稿
3. 在剪映中可见
4. 能读取 `draft_content.json`
5. 若开启自动导出，能完成导出

### 16. 验收标准

修复完成后至少满足以下四条：

1. `status` 不再出现假阳性。
2. 环境安装过程可复现。
3. `sdk` 相关模式语义清晰。
4. 最小链路稳定可跑。

## 推荐实施顺序

### 第一批

- 下线或重命名误导性 `sdk` 剧本模式
- 修复 `applied_edits`
- 增强状态页体检

### 第二批

- 固化 SDK 版本治理
- 将桥接脚本移出 SDK 目录
- 拆分依赖清单
- 明确三层职责边界

### 第三批

- 接入 `draft_inspector`
- 接入 `asset_search`
- 接入 `auto_exporter`
- 按需接入 `web_vfx`、`recording`、`movie_commentary`

## 建议的交付节奏

### 1 天内

- 完成阶段一
- 消除误导项与假成功

### 2-3 天内

- 完成阶段二骨架
- 建立稳定桥接与依赖治理

### 后续迭代

- 按能力矩阵逐项接入上游 SDK 高阶能力

## 结论

当前项目最需要的不是继续堆更多“SDK 入口”，而是先把现有接入做实：

- 状态必须可信
- 行为必须可复现
- 模式命名必须准确
- 第三方依赖必须可治理

在此基础上，再继续补全上游 SDK 的高阶能力，才能把这套剪映工作流真正做成稳定产品能力，而不是“本机能跑的半接入状态”。
