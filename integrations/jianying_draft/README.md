# Jianying Draft Integration

This integration wraps local Jianying/CapCut draft workflows for the personal workbench.

Planned responsibilities:

- Validate local Jianying draft and asset configuration.
- Scan local media assets before draft creation.
- Create simple draft projects through `pyJianYingDraft`.
- Inspect and render templates.
- Coordinate manual or external exe based decrypt/restore workflows.

The integration intentionally keeps third-party draft logic behind an adapter so the
FastAPI app can use stable, local APIs.

