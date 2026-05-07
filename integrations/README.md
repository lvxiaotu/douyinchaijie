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
