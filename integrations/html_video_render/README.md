# HTML Video Render Integration

This integration is the future rendering layer inspired by Hyperframes.

The first version is intentionally small:

- Store HTML composition files.
- Return render metadata.
- Prepare a stable adapter API for browser/ffmpeg rendering later.

Later phases will use Playwright or a Hyperframes-compatible runner to render
HTML/CSS/JS into video assets that can be imported into Jianying drafts.

