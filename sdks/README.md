# Local SDK Snapshots

`sdks/` stores local upstream snapshots that are used by this project but not owned by it.

## JianYing Editor Skill

Current lock file:

```text
sdks/jianying-editor-skill.lock.json
```

Governance rules:

- Treat `sdks/jianying-editor-skill/` as upstream-owned snapshot content.
- Do not put project business logic, adapters, or patches inside the SDK tree.
- Project-owned bridge logic lives in `integrations/jianying_editor_skill/`.
- When replacing or updating the SDK snapshot, update the lock file with the new version and commit.
- If the SDK directory is a nested Git checkout, local untracked files inside it must not be required by this project.

The current integration follows `vendor snapshot` mode rather than a Git submodule so the app can stabilize first. A future switch to submodule is possible after the bridge surface is smaller and better tested.
