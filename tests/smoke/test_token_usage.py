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
import time
from tests.smoke import smoke_utils
from google.genai import types

try:
    from tests.smoke import llm_sender
except ImportError:
    llm_sender = None


def compare_usage(current, baseline, label, threshold=0.05):
    """Compares current usage vs baseline and reports if it increases significantly."""
    # Handle None values by treating them as 0
    current = current if current is not None else 0
    baseline = baseline if baseline is not None else 0

    if baseline == 0:
        if current == 0:
            return True
        print(
            f"  [WARNING] {label} usage increased: baseline was 0, now {current}"
        )
        return False

    if current <= baseline:
        return True

    diff = (current - baseline) / baseline
    if diff > threshold:
        print(
            f"  [WARNING] {label} usage increased by {diff:.1%}: {baseline} -> {current}"
        )
        return False
    return True


def main():
    if not os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY environment variable not set.")
        sys.exit(1)

    if llm_sender is None:
        print("llm_sender is not available.")
        sys.exit(1)

    cases_path = os.path.join(os.path.dirname(__file__), "llm_cases.json")
    if not os.path.exists(cases_path):
        print(f"LLM cases file not found at {cases_path}")
        sys.exit(1)

    with open(cases_path, "r") as f:
        cases = json.load(f)

    print("Fetching tools list from server...")
    try:
        tools_response = smoke_utils.get_tools_list()
        tools = tools_response.get("tools", [])
    except Exception as e:
        print(f"Failed to get tools from server: {e}")
        sys.exit(1)

    failures = 0
    total_cases = len(cases)

    print(
        f"Starting token usage comparison for {total_cases} cases...",
        file=sys.stderr,
    )

    for i, case in enumerate(cases, 1):
        prompt = case["prompt"]
        baseline_prompt = case.get("prompt_tokens")
        baseline_output = case.get("output_tokens")
        baseline_thought = case.get("thought_tokens", 0)
        baseline_tool_tokens = case.get("tool_tokens")
        baseline_model = case.get("model", "unknown")

        if baseline_prompt is None or baseline_output is None:
            print(
                f"[{i}/{total_cases}] Skipping '{prompt}': no baseline found."
            )
            continue

        print(f"[{i}/{total_cases}] Testing prompt: '{prompt}'")
        try:
            # Note: llm_sender.get_llm_response already has a sleep(5) internally.
            result = llm_sender.get_llm_response(
                prompt, tools, include_usage=True
            )
            if result and "usage" in result:
                current_prompt = result["usage"]["prompt_token_count"]
                current_output = result["usage"]["candidates_token_count"]
                current_thought = result["usage"]["thought_token_count"]
                current_model = result["model"]

                if current_model != baseline_model:
                    print(
                        f"  [INFO] Model changed: {baseline_model} -> {current_model}"
                    )

                p_ok = compare_usage(current_prompt, baseline_prompt, "Prompt")
                o_ok = compare_usage(current_output, baseline_output, "Output")
                t_ok = compare_usage(
                    current_thought, baseline_thought, "Thought", threshold=0.15
                )

                tool_name = result.get("tool_name")
                tool_args = result.get("tool_args")
                tool_ok = True
                current_tool_tokens = 0

                if tool_name:
                    print(f"  [INFO] Tool call: {tool_name}")
                    try:
                        # Execute tool call
                        tool_result = smoke_utils.call_tool(
                            tool_name, tool_args
                        )

                        # Measure token count of response
                        resp_part = types.Part.from_function_response(
                            name=tool_name, response=tool_result
                        )
                        tool_content = types.Content(
                            role="tool", parts=[resp_part]
                        )
                        current_tool_tokens = llm_sender.count_tokens(
                            tool_content
                        )
                        print(
                            f"  [INFO] Tool Response Tokens: {current_tool_tokens}"
                        )

                        if baseline_tool_tokens is not None:
                            tool_ok = compare_usage(
                                current_tool_tokens,
                                baseline_tool_tokens,
                                "Tool Response",
                            )
                        else:
                            print(
                                f"  [INFO] No tool token baseline found for comparison."
                            )

                    except Exception as e:
                        print(f"  [ERROR] Tool execution failed: {e}")
                        tool_ok = False

                if not (p_ok and o_ok and t_ok and tool_ok):
                    failures += 1
                else:
                    tool_msg = (
                        f", Tool: {current_tool_tokens}" if tool_name else ""
                    )
                    print(
                        f"  [OK] Prompt: {current_prompt}, Output: {current_output}, Thought: {current_thought}{tool_msg}"
                    )

            # Sleep to avoid rate limits (in addition to internal sleep)
            time.sleep(5)
        except Exception as e:
            print(f"  [ERROR] {e}")
            failures += 1

    if failures > 0:
        print(
            f"\n[FAIL] Found {failures} cases with significant token usage increases."
        )
        sys.exit(1)
    else:
        print("\n[SUCCESS] All cases within token usage thresholds.")


if __name__ == "__main__":
    main()
