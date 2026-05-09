# 精简网页工具启动

现在可以只启动一个后端服务来使用整个网页工具。前端会先构建到 `dist/`，再由 FastAPI 直接托管。

## 一键启动

在项目根目录运行：

```powershell
.\scripts\start-web.ps1
```

启动后打开：

```text
http://127.0.0.1:8010
```

## 常用参数

```powershell
.\scripts\start-web.ps1 -Port 8020
.\scripts\start-web.ps1 -InstallDeps
.\scripts\start-web.ps1 -StartDouyin
.\scripts\start-web.ps1 -NoBuild
.\scripts\start-web.ps1 -NoOpen
```

脚本会按当前端口重新构建前端，所以改端口时不需要手动改 `.env`。

如果要使用抖音采集/下载相关功能，可以加 `-StartDouyin`，脚本会尝试一起启动 `integrations/douyin_download_api/vendor/Douyin_TikTok_Download_API`。

## 开发模式

如果需要前后端热更新，仍然可以分开启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8010
npm run dev
```

开发模式下 Vite 会把 `/api` 自动代理到 `http://127.0.0.1:8010`。
