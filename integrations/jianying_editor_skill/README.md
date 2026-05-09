# JianYing Editor Skill Bridge

This directory contains project-owned bridge code for the local `jianying-editor-skill` SDK snapshot.

## Ownership

- `sdks/jianying-editor-skill/` is upstream-owned SDK snapshot content.
- `integrations/jianying_editor_skill/` is this project's bridge layer.
- Route handlers should not import SDK scripts directly.
- Business-specific adapters must stay here, not inside the SDK checkout.

## Current Responsibilities

- `script_input_parser.py`
  Parses natural-language edit requests into this project's `ScriptGenerateRequest`.

- `script_contract_adapter.py`
  Generates a `script.json`-compatible structure from the local Skill contract rules.

- `skill_contract_script_generator.py`
  Normalizes the Skill contract output into `VideoScript`.

- `sdk_script_generator.py`
  Compatibility aliases for older imports. New code should import `skill_contract_script_generator.py`.

- `sdk_cli_runner.py`
  Runs upstream SDK CLI scripts with UTF-8 subprocess settings and normalized JSON parsing.

- `sdk_capability_service.py`
  Business wrapper for selected SDK capabilities: draft inspection, asset search, cloud assets,
  TTS, Web VFX, smart zoom, movie commentary, diagnostics, and auto export.

## Exposed Capabilities

Backend route prefix:

```text
/api/tools/jianying-editor-sdk
```

Current endpoints:

```text
GET  /status                         light, no-side-effect capability discovery
POST /diagnostics/deep               explicit api_validator.py --json diagnostic
POST /drafts/list                    wraps scripts/draft_inspector.py list --json
POST /drafts/summary                 wraps scripts/draft_inspector.py summary --json
POST /drafts/show                    wraps scripts/draft_inspector.py show --json
POST /assets/search                  wraps scripts/asset_search.py --json
POST /cloud/assets/resolve           wraps CloudManager find/download
POST /cloud/music-library/sync       wraps build_cloud_music_library.py --json
POST /tts                            wraps universal_tts.generate_voice_with_meta
POST /web-vfx/record                 wraps web_recorder.record_web_animation
POST /smart-zoom/drafts              creates a draft with click-driven zoom keyframes
POST /movie-commentary/drafts        wraps movie_commentary_builder.py
POST /exports                        wraps scripts/auto_exporter.py --json
```

`GET /status` must stay side-effect free. Use `POST /diagnostics/deep` when a caller
explicitly wants the active smoke path; it may create a diagnostic draft.

Auto export controls the local JianYing application through SDK automation. Only call it from an
explicit user action with a known draft name and output path. The route only reports auto export as
available when Windows, `uiautomation`, and JianYing `<= 5.9` are detected. Use
`JY_JIANYING_VERSION=5.9.0` to override version detection on machines where the app path cannot be
discovered automatically.

## Capability Matrix

The backend returns both a boolean `capabilities` map and a structured `capability_matrix`.
The matrix covers:

```text
can_create_draft
can_validate_draft
can_inspect_draft
can_asset_search
can_cloud_media
can_cloud_music
can_tts
can_web_vfx
can_record_screen
can_smart_zoom
can_movie_commentary
can_auto_export
```

Each matrix item includes the script, endpoint, dependencies, supported platforms, invocation path,
acceptance note, and current availability.

## Layer Boundary

`integrations/video_pipeline/`
owns LLM/script generation and stores `script.json`.

`integrations/jianying_draft/`
owns conversion from `script.json` into a JianYing draft and may use `pyJianYingDraft` or `JyProject`.

`integrations/jianying_editor_skill/`
owns SDK capability discovery, CLI wrapping, environment checks, and bridge logic for the upstream Skill SDK snapshot.
