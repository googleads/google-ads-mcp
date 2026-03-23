import json
import os
import unittest
from tests.smoke import smoke_utils
import difflib


class SmokeTest(unittest.TestCase):
    def test_tools_list_matches_golden(self):
        """Verifies that the current tools list matches the golden file."""
        current_tools = smoke_utils.get_tools_list()

        # Sort to ensure deterministic comparison
        if "tools" in current_tools:
            current_tools["tools"].sort(
                key=lambda x: x.get("name", "")
            )

        golden_path = os.path.join(
            os.path.dirname(__file__), "golden_tools_list.json"
        )

        if not os.path.exists(golden_path):
            self.fail(
                f"Golden file not found at {golden_path}. "
                "Run tests/smoke/generate_golden.py to create it."
            )

        with open(golden_path, "r") as f:
            golden_tools = json.load(f)

        # Compare tool names and required params only
        # (full schema comparison breaks across pydantic versions)
        current_names = sorted(
            [t["name"] for t in current_tools.get("tools", [])]
        )
        golden_names = sorted(
            [t["name"] for t in golden_tools.get("tools", [])]
        )

        if current_names != golden_names:
            missing = set(golden_names) - set(current_names)
            extra = set(current_names) - set(golden_names)
            msg = "Tool names do not match golden file."
            if missing:
                msg += f"\nMissing: {missing}"
            if extra:
                msg += f"\nExtra: {extra}"
            self.fail(msg)

        # Verify each tool has required params matching
        current_by_name = {
            t["name"]: t for t in current_tools.get("tools", [])
        }
        golden_by_name = {
            t["name"]: t for t in golden_tools.get("tools", [])
        }

        for name in golden_names:
            golden_req = sorted(
                golden_by_name[name]
                .get("inputSchema", {})
                .get("required", [])
            )
            current_req = sorted(
                current_by_name[name]
                .get("inputSchema", {})
                .get("required", [])
            )
            self.assertEqual(
                golden_req,
                current_req,
                f"Required params mismatch for tool '{name}'",
            )


if __name__ == "__main__":
    unittest.main()
