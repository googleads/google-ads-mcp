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

"""Tests for tool schema correctness and type safety."""

import unittest
from ads_mcp.coordinator import mcp

# Import server to ensure all tools are registered on the mcp object
from ads_mcp import server  # noqa: F401


class TestToolSchemas(unittest.IsolatedAsyncioTestCase):
    """Verifies that tool schemas are properly defined and prevent Zod errors."""

    async def test_optional_parameters_allow_null(self):
        """Verifies that any tool parameter with a default of None allows 'null' in its schema.

        This prevents 'Expected array, received string' or similar client-side Zod validation
        failures caused by schema type contradictions (e.g. type 'array' but default is 'null').
        """
        tools = await mcp.list_tools()
        self.assertGreater(
            len(tools), 0, "No tools are registered on the server"
        )

        for tool in tools:
            input_schema = tool.parameters
            properties = input_schema.get("properties", {})
            for param_name, param_schema in properties.items():
                # If a parameter has a default value of None (JSON null), the schema must permit null
                if (
                    "default" in param_schema
                    and param_schema["default"] is None
                ):
                    has_null_type = False

                    # Case 1: Schema uses anyOf (standard for Pydantic unions)
                    if "anyOf" in param_schema:
                        for option in param_schema["anyOf"]:
                            if option.get("type") == "null":
                                has_null_type = True
                                break

                    # Case 2: Schema uses oneOf
                    elif "oneOf" in param_schema:
                        for option in param_schema["oneOf"]:
                            if option.get("type") == "null":
                                has_null_type = True
                                break

                    # Case 3: Schema has list-based types or direct type 'null'
                    elif "type" in param_schema:
                        t = param_schema["type"]
                        if t == "null":
                            has_null_type = True
                        elif isinstance(t, list) and "null" in t:
                            has_null_type = True

                    self.assertTrue(
                        has_null_type,
                        f"Tool '{tool.name}' parameter '{param_name}' has default=None, "
                        f"but its JSON schema does not permit 'null'. Schema: {param_schema}",
                    )

    async def test_search_tool_array_parameters(self):
        """Verifies that search tool's array parameters are correctly typed with top-level 'array'."""
        tools = await mcp.list_tools()
        search_tool = next(
            (t for t in tools if t.name == "search_search"), None
        )
        self.assertIsNotNone(search_tool, "search tool not found")

        properties = search_tool.parameters.get("properties", {})

        for param in ["conditions", "orderings"]:
            schema = properties.get(param)
            self.assertIsNotNone(
                schema, f"Parameter '{param}' not found in search tool schema"
            )
            self.assertEqual(
                schema.get("type"),
                "array",
                f"Parameter '{param}' must have type 'array'",
            )
            self.assertEqual(
                schema.get("default"),
                [],
                f"Parameter '{param}' default must be an empty list",
            )

    async def test_all_tools_define_read_only_hint_annotation(self):
        """Verifies every tool sets ToolAnnotations.readOnlyHint and mutate tools expose validate_only/checksum."""
        tools = await mcp.list_tools()
        self.assertGreater(
            len(tools), 0, "No tools are registered on the server"
        )

        for tool in tools:
            self.assertIsNotNone(
                tool.annotations,
                f"Tool '{tool.name}' must define ToolAnnotations.",
            )
            self.assertIsInstance(
                tool.annotations.read_only_hint,
                bool,
                f"Tool '{tool.name}' must explicitly set ToolAnnotations.read_only_hint to True or False.",
            )
            properties = tool.parameters.get("properties", {})
            if tool.annotations.read_only_hint is False:
                self.assertIn(
                    "validate_only",
                    properties,
                    f"Mutate tool '{tool.name}' (read_only_hint=False) must accept 'validate_only'.",
                )
                self.assertEqual(
                    properties["validate_only"].get("default"),
                    True,
                    f"Mutate tool '{tool.name}' must default 'validate_only' to True.",
                )
                self.assertIn(
                    "checksum",
                    properties,
                    f"Mutate tool '{tool.name}' (read_only_hint=False) must accept 'checksum'.",
                )
            else:
                self.assertNotIn(
                    "validate_only",
                    properties,
                    f"Read-only tool '{tool.name}' (read_only_hint=True) should not define 'validate_only'.",
                )
