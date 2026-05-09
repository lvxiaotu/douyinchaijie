import unittest
from pathlib import Path

from backend.app.routes import jianying_editor_sdk
from integrations.jianying_editor_skill.sdk_capability_service import SdkCapabilityService
from integrations.jianying_editor_skill.sdk_cli_runner import SdkCliRunner


class JianyingEditorSdkStatusTests(unittest.TestCase):
    def test_light_status_has_complete_matrix_without_deep_side_effect_checks(self):
        status = jianying_editor_sdk._status_payload()

        self.assertEqual(status["status_scope"], "light")
        self.assertNotIn("api_validator", status["checks"])
        self.assertNotIn("smoke_draft_create", status["checks"])
        self.assertEqual(
            sorted(status["capabilities"].keys()),
            sorted(jianying_editor_sdk.CAPABILITY_ORDER),
        )
        self.assertEqual(len(status["capability_matrix"]), len(jianying_editor_sdk.CAPABILITY_ORDER))

    def test_auto_export_requires_known_supported_jianying_version(self):
        checks = {
            "jyproject_import": {"ok": True},
            "sdk_requirements": {"ok": True},
            "optional_requirements": {"missing": [], "available": []},
            "platform": {
                "auto_export_platform_ok": True,
                "auto_export_version_ok": False,
                "jianying": {"version_ok": None},
            },
        }

        matrix = jianying_editor_sdk._build_capability_matrix(checks)
        auto_export = next(item for item in matrix if item["key"] == "can_auto_export")
        self.assertFalse(auto_export["available"])

    def test_version_comparison_handles_multi_part_versions(self):
        self.assertTrue(jianying_editor_sdk._version_at_most("5.9.0.11632", (5, 9)))
        self.assertFalse(jianying_editor_sdk._version_at_most("6.0.0", (5, 9)))
        self.assertIsNone(jianying_editor_sdk._version_at_most("unknown", (5, 9)))

    def test_version_from_path_ignores_unrelated_digits(self):
        path = Path(r"C:\Program Files (x86)\JianyingPro\Apps\5.9.0.11632\JianyingPro.exe")
        self.assertEqual(jianying_editor_sdk._version_from_path(path), "5.9.0.11632")


class JianyingEditorSdkRunnerTests(unittest.TestCase):
    def test_runner_parses_last_json_line(self):
        runner = SdkCliRunner()
        parsed = runner._parse_json("log line\n{\"ok\": true, \"data\": {\"count\": 2}}\n")
        self.assertEqual(parsed["data"]["count"], 2)

    def test_service_invalid_inputs_are_normalized(self):
        service = SdkCapabilityService()
        result = service.generate_tts(text="", output_path="")
        self.assertFalse(result["ok"])
        self.assertEqual(result["data"]["code"], "invalid_input")


if __name__ == "__main__":
    unittest.main()
