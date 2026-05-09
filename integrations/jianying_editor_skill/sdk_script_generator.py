from __future__ import annotations

from integrations.jianying_editor_skill.skill_contract_script_generator import (
    JianyingSkillContractScriptGenerator,
    SkillContractGeneratedScript,
)


# Compatibility aliases for older imports. The script-side "sdk" mode now means
# project-owned Skill contract generation; SDK/JyProject is reserved for draft creation.
JianyingEditorSdkScriptGenerator = JianyingSkillContractScriptGenerator
SdkGeneratedScript = SkillContractGeneratedScript
