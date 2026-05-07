# 架构预留说明

这个项目按“个人工具工作台 + Python 适配层”的方式组织。

## 前端

前端使用 Vite + React。原因是：

- 页面和组件拆分简单，适合你后续自己改。
- 不绑定复杂全栈框架，后端可以完全交给 Python。
- 以后增加工具页面时，只需要新增组件和路由状态。

当前前端先用一个轻量单页工作台：

```text
src/
├─ main.jsx              # 主界面
├─ services/api.js       # 后端 API 调用
├─ workbenchSeed.js      # 后端未启动时的示例数据
└─ styles.css            # 全局样式
```

## 后端

后端使用 FastAPI。建议后续逐步加入：

- 工具注册表：记录每个工具的名称、配置项、输入、输出和所属适配器。
- 任务队列：运行下载、分析、ComfyUI 等耗时任务。
- 本地数据库：先用 SQLite，后续有需要再迁移 PostgreSQL。
- 配置管理：敏感信息走 `.env` 或本地加密文件。

当前结构：

```text
backend/app/
├─ main.py       # API 入口
├─ models.py     # 前后端共享的数据形状
└─ registry.py   # 临时工具注册表，后续可换成数据库
```

## GitHub 开源项目接入

每接入一个开源项目，都建议放进 `integrations/项目名/`，不要直接把第三方逻辑写进 API。

推荐结构：

```text
integrations/some_project/
├─ adapter.py              # 统一适配器
├─ config.example.json     # 配置示例
├─ README.md               # 接入说明
└─ vendor/                 # 可选：外部项目源码或子模块位置
```

适配器要负责：

- 校验配置
- 包装第三方项目的命令或 Python API
- 把结果转换成工作台统一格式
- 暴露日志和错误信息

主后端只调用适配器，不关心第三方项目内部怎么实现。这样以后某个开源项目坏了、换了、升级了，不会拖垮整个工作台。
