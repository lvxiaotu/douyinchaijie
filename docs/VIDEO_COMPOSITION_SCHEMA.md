# Video Composition JSON

`video composition` 是当前项目的视频中间描述格式。它不绑定剪映，也不绑定 HTML 渲染器。

目标：

- AI、前端表单、模板系统都先生成同一种 JSON。
- `html_video_render` 可以把它转成 HTML 动效素材。
- `jianying_draft` 可以把它转成剪映草稿。
- 后续批量生产时只需要替换 composition 里的变量和素材。

## 最小结构

```json
{
  "name": "demo-video",
  "canvas": {
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "duration_seconds": 12
  },
  "tracks": [
    {
      "id": "main-video",
      "type": "video",
      "items": [
        {
          "id": "clip-1",
          "path": "G:/media/a.mp4",
          "start_seconds": 0,
          "duration_seconds": 6
        }
      ]
    },
    {
      "id": "captions",
      "type": "text",
      "items": [
        {
          "id": "text-1",
          "text": "第一句字幕",
          "start_seconds": 0,
          "duration_seconds": 3
        }
      ]
    }
  ]
}
```

## 字段说明

### 根字段

- `name`：工程名，也会作为默认剪映草稿名。
- `canvas.width`：画布宽度。
- `canvas.height`：画布高度。
- `canvas.fps`：帧率，默认 30。
- `canvas.duration_seconds`：总时长，可选。
- `tracks`：轨道数组。

### track

```json
{
  "id": "track-id",
  "type": "video",
  "items": []
}
```

`type` 支持：

- `video`
- `image`
- `audio`
- `text`
- `overlay`
- `rendered`

剪映输出时：

- `video`、`image`、`overlay`、`rendered` 会进入视频轨。
- `audio` 会进入音频轨。
- `text` 会进入文本轨。

HTML 输出时：

- 所有可视轨道都可以生成 DOM 元素。
- `audio` 轨道可以交给后续 ffmpeg 或浏览器音频层处理。

### item

媒体 item：

```json
{
  "id": "clip-1",
  "path": "G:/media/a.mp4",
  "start_seconds": 0,
  "duration_seconds": 5,
  "role": "main"
}
```

文本 item：

```json
{
  "id": "text-1",
  "text": "画面文字",
  "start_seconds": 0,
  "duration_seconds": 3,
  "style": {
    "font_size": 48,
    "color": "#ffffff",
    "position": "bottom"
  }
}
```

## 设计原则

- 时间单位统一使用秒。
- 路径统一保留用户本机路径，不提前复制。
- 素材是否存在由 `asset_manager` 检查。
- 剪映特有字段放进 `jianying` 子对象，不污染通用字段。
- HTML 特有字段放进 `html` 子对象，不污染通用字段。

示例：

```json
{
  "id": "title-card",
  "type": "rendered",
  "path": "data/runtime/html_video_render/title-card.mp4",
  "start_seconds": 0,
  "duration_seconds": 3,
  "jianying": {
    "track": "overlay"
  },
  "html": {
    "class_name": "title-card"
  }
}
```

