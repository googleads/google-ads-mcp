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
import sys
from tests.smoke import smoke_utils
from google.genai import types

try:
    from tests.smoke import llm_sender
except ImportError:
    llm_sender = None


def main():
    try:
        print("Fetching tools list from server...")
        tools_list = smoke_utils.get_tools_list()

        # Sort tools by name to ensure deterministic output
        if "tools" in tools_list:
            tools_list["tools"].sort(key=lambda x: x.get("name", ""))

        output_path = os.path.join(
            os.path.dirname(__file__), "golden_tools_list.json"
        )

        print(f"Writing golden file to {output_path}...")
        with open(output_path, "w") as f:
            json.dump(tools_list, f, indent=2, sort_keys=True)
            f.write("\n")  # Add trailing newline

        print("Done updating golden tools list.")

        # Resources
        print("Fetching resources list from server...")
        resources_list = smoke_utils.get_resources_list()

        # Sort resources by URI to ensure deterministic output
        if "resources" in resources_list:
            resources_list["resources"].sort(key=lambda x: x.get("uri", ""))

        resources_output_path = os.path.join(
            os.path.dirname(__file__), "golden_resources_list.json"
        )

        print(f"Writing golden resources file to {resources_output_path}...")
        with open(resources_output_path, "w") as f:
            json.dump(resources_list, f, indent=2, sort_keys=True)
            f.write("\n")

        print("Done updating golden resources list.")

        # Update LLM cases with token usage baselines
        if not os.environ.get("GEMINI_API_KEY"):
            print(
                "GEMINI_API_KEY not set, skipping LLM baselines.",
                file=sys.stderr,
            )
            return

        if llm_sender is None:
            print(
                "llm_sender not available, skipping LLM baselines.",
                file=sys.stderr,
            )
            return

        cases_path = os.path.join(os.path.dirname(__file__), "llm_cases.json")
        if not os.path.exists(cases_path):
            print(f"LLM cases file not found at {cases_path}")
            return

        print(f"Updating LLM baselines in {cases_path}...")
        with open(cases_path, "r") as f:
            cases = json.load(f)

        tools = tools_list.get("tools", [])
        for case in cases:
            prompt = case["prompt"]
            print(f"  Processing prompt: '{prompt}'")
            try:
                result = llm_sender.get_llm_response(
                    prompt, tools, include_usage=True
                )
                if result and "usage" in result:
                    case["prompt_tokens"] = result["usage"][
                        "prompt_token_count"
                    ]
                    case["output_tokens"] = result["usage"][
                        "candidates_token_count"
                    ]
                    case["thought_tokens"] = result["usage"][
                        "thought_token_count"
                    ]
                    case["model"] = result["model"]
                    # Clean up old keys if present
                    case.pop("cached_tokens", None)
                    case.pop("thoughts_tokens", None)

                    tool_name = result.get("tool_name")
                    tool_args = result.get("tool_args")
                    if tool_name:
                        print(
                            f"    Executing tool '{tool_name}' for baseline...",
                            file=sys.stderr,
                        )
                        try:
                            tool_result = smoke_utils.call_tool(
                                tool_name, tool_args
                            )
                            resp_part = types.Part.from_function_response(
                                name=tool_name, response=tool_result
                            )
                            tool_content = types.Content(
                                role="tool", parts=[resp_part]
                            )
                            tool_tokens = llm_sender.count_tokens(tool_content)
                            case["tool_tokens"] = tool_tokens
                            print(
                                f"    Tool tokens recorded: {tool_tokens}",
                                file=sys.stderr,
                            )
                        except Exception as e:
                            print(
                                f"    Error recording tool tokens: {e}",
                                file=sys.stderr,
                            )
                            case["tool_tokens"] = 0
                    else:
                        case.pop("tool_tokens", None)
            except Exception as e:
                print(
                    f"  Error processing prompt '{prompt}': {e}",
                    file=sys.stderr,
                )

        with open(cases_path, "w") as f:
            json.dump(cases, f, indent=2)
            f.write("\n")

        print("LLM baselines updated.")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
