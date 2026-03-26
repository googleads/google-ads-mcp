# Copyright 2026 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
            current_tools["tools"].sort(key=lambda x: x.get("name", ""))

        golden_path = os.path.join(
            os.path.dirname(__file__), "golden_tools_list.json"
        )

        if not os.path.exists(golden_path):
            self.fail(
                f"Golden file not found at {golden_path}. Run tests/smoke/generate_golden.py to create it."
            )

        with open(golden_path, "r") as f:
            golden_tools = json.load(f)

        # Convert to string for diffing
        current_str = json.dumps(current_tools, indent=2, sort_keys=True)
        golden_str = json.dumps(golden_tools, indent=2, sort_keys=True)

        if current_str != golden_str:
            diff = list(
                difflib.unified_diff(
                    golden_str.splitlines(),
                    current_str.splitlines(),
                    fromfile="golden_tools_list.json",
                    tofile="current_tools_list.json",
                    lineterm="",
                )
            )
            diff_msg = "\n".join(diff)
            self.fail(f"Tools list does not match golden file:\n{diff_msg}")

    def test_resources_list_matches_golden(self):
        """Verifies that the current resources list matches the golden file."""
        current_resources = smoke_utils.get_resources_list()

        # Sort to ensure deterministic comparison
        if "resources" in current_resources:
            current_resources["resources"].sort(key=lambda x: x.get("uri", ""))

        golden_path = os.path.join(
            os.path.dirname(__file__), "golden_resources_list.json"
        )

        if not os.path.exists(golden_path):
            self.fail(
                f"Golden resources file not found at {golden_path}. Run tests/smoke/generate_golden.py to create it."
            )

        with open(golden_path, "r") as f:
            golden_resources = json.load(f)

        # Convert to string for diffing
        current_str = json.dumps(current_resources, indent=2, sort_keys=True)
        golden_str = json.dumps(golden_resources, indent=2, sort_keys=True)

        if current_str != golden_str:
            diff = list(
                difflib.unified_diff(
                    golden_str.splitlines(),
                    current_str.splitlines(),
                    fromfile="golden_resources_list.json",
                    tofile="current_resources_list.json",
                    lineterm="",
                )
            )
            diff_msg = "\n".join(diff)
            self.fail(f"Resources list does not match golden file:\n{diff_msg}")


if __name__ == "__main__":
    unittest.main()
