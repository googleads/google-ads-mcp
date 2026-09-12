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

import os
import json
import sys
import time
from google.genai import types
from google.genai import Client
from google.genai import errors
from tests.smoke import smoke_utils

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")


def _strip_additional_properties(schema: dict) -> dict:
    """Recursively removes 'additionalProperties' and 'additional_properties' from the schema."""
    if not isinstance(schema, dict):
        return schema
    for key, value in list(schema.items()):
        if key in ("additionalProperties", "additional_properties"):
            del schema[key]
        elif isinstance(value, dict):
            _strip_additional_properties(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _strip_additional_properties(item)
    return schema


def get_llm_response(
    prompt: str | list,
    tools: list,
    include_usage: bool = False,
    model: str | None = None,
) -> str | dict:
    """Sends a prompt to the LLM with the given tools and returns the tool usage."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable not set.")

    model_name = model or DEFAULT_MODEL

    # Inject customer ID if placeholder is present (only for string prompts)
    if isinstance(prompt, str):
        prompt = smoke_utils.inject_customer_id(prompt)

    client = Client(api_key=api_key)

    # Convert MCP tools to Gemini tools format if necessary, or pass as is if supported.
    # The google-genai SDK supports function calling. We need to map MCP tools to it.
    # For simplicity, we'll try to pass the tool definitions directly if they match,
    # or we might need to adapt them. MCP tools are JSON Schema.
    # Gemini expects: tool = types.Tool(function_declarations=[...])

    function_declarations = []
    for tool in tools:
        # MCP tool: {name, description, inputSchema}
        # Gemini FunctionDeclaration: {name, description, parameters}
        # Truncate description to avoid hitting token limits with massive tool docs
        description = tool.get("description", "")
        if tool["name"] == "search":
            description = "Search for Google Ads resources such as campaigns, ad groups, keywords, and metrics using Google Ads Query Language (GAQL). Use this tool to find objects by name or status."
        elif len(description) > 1024:
            description = description[:1024] + "..."

        parameters = _strip_additional_properties(
            dict(tool.get("inputSchema", {}))
        )

        fd = types.FunctionDeclaration(
            name=tool["name"],
            description=description,
            parameters=parameters,
        )
        function_declarations.append(fd)

    llm_tools = [types.Tool(function_declarations=function_declarations)]
    tool_config = types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(mode="ANY")
    )

    max_retries = 5
    base_delay = 2

    # Sleep to respect rate limits
    time.sleep(2)

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=llm_tools,
                    tool_config=tool_config,
                    temperature=0.0,
                ),
            )

            if not response.candidates:
                if include_usage:
                    return {
                        "tool_name": None,
                        "usage": {
                            "prompt_token_count": response.usage_metadata.prompt_token_count,
                            "candidates_token_count": response.usage_metadata.candidates_token_count,
                            "total_token_count": response.usage_metadata.total_token_count,
                            "thought_token_count": getattr(
                                response.usage_metadata,
                                "thought_token_count",
                                0,
                            )
                            or getattr(
                                response.usage_metadata,
                                "thoughts_token_count",
                                0,
                            ),
                        },
                        "model": model_name,
                    }
                return None

            candidate = response.candidates[0]
            selected_tool = None
            tool_args = None
            # Check for function calls
            for part in candidate.content.parts:
                if part.function_call:
                    selected_tool = part.function_call.name
                    # args is a structure, we can convert to dict or leave as is
                    # types.FunctionCall.args is usually a dict or dict-like
                    tool_args = (
                        dict(part.function_call.args)
                        if part.function_call.args
                        else {}
                    )
                    break

            if include_usage:
                # usage_metadata is a pydantic-like model, we might want to convert it to dict
                usage = {
                    "prompt_token_count": response.usage_metadata.prompt_token_count,
                    "candidates_token_count": response.usage_metadata.candidates_token_count,
                    "total_token_count": response.usage_metadata.total_token_count,
                    "thought_token_count": getattr(
                        response.usage_metadata, "thought_token_count", 0
                    )
                    or getattr(
                        response.usage_metadata, "thoughts_token_count", 0
                    ),
                }
                return {
                    "tool_name": selected_tool,
                    "tool_args": tool_args,
                    "usage": usage,
                    "model": model_name,
                }

            return selected_tool

        except (errors.ClientError, errors.ServerError) as e:
            code = getattr(e, "code", None)
            if code in (429, 503) or "high demand" in str(e).lower():
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)
                    print(
                        f"Temporary API error ({code}). Retrying in {delay} seconds...",
                        file=sys.stderr,
                    )
                    time.sleep(delay)
                    continue
            raise e


def count_tokens(contents, model: str | None = None) -> int:
    """Counts the number of tokens in the given content using the LLM backend."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable not set.")

    model_name = model or DEFAULT_MODEL
    client = Client(api_key=api_key)
    response = client.models.count_tokens(
        model=model_name,
        contents=contents,
    )
    return response.total_tokens
