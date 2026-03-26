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

import contextlib
import json
import subprocess
import sys
import threading
import os
from typing import Any, Dict, List, Optional


def start_server_process() -> subprocess.Popen:
    """Starts the MCP server as a subprocess."""
    return subprocess.Popen(
        [sys.executable, "-m", "ads_mcp.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
        bufsize=0,  # Unbuffered
    )


def send_request(
    process: subprocess.Popen,
    method: str,
    params: Optional[Dict[str, Any]] = None,
    req_id: Optional[int] = 1,
) -> None:
    """Sends a JSON-RPC request or notification to the server."""
    request = {
        "jsonrpc": "2.0",
        "method": method,
    }
    if req_id is not None:
        request["id"] = req_id

    if params:
        request["params"] = params

    json_req = json.dumps(request)
    process.stdin.write(json_req + "\n")
    process.stdin.flush()


def read_response(process: subprocess.Popen) -> Dict[str, Any]:
    """Reads a JSON-RPC response from the server."""
    for line in process.stdout:
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    raise RuntimeError("Server closed connection without response")


@contextlib.contextmanager
def initialized_server():
    """Context manager that starts, initializes, and cleans up an MCP server process."""
    process = start_server_process()
    try:
        # Initialize
        send_request(
            process,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "smoke-test", "version": "1.0"},
            },
            req_id=1,
        )

        # Read initialize response
        response = read_response(process)
        if "error" in response:
            raise RuntimeError(f"Initialize failed: {response['error']}")

        # Send initialized notification
        send_request(process, "notifications/initialized", req_id=None)

        yield process
    finally:
        if process.stdin:
            process.stdin.close()
        if process.stdout:
            process.stdout.close()
        process.terminate()
        process.wait()


def get_tools_list() -> Dict[str, Any]:
    """Runs the server and retrieves the list of tools."""
    with initialized_server() as process:
        send_request(process, "tools/list", req_id=2)
        response = read_response(process)

        if "error" in response:
            raise RuntimeError(f"tools/list failed: {response['error']}")

        return response["result"]


def get_resources_list() -> Dict[str, Any]:
    """Runs the server and retrieves the list of resources."""
    with initialized_server() as process:
        send_request(process, "resources/list", req_id=2)
        response = read_response(process)

        if "error" in response:
            raise RuntimeError(f"resources/list failed: {response['error']}")

        return response["result"]


def inject_customer_id(prompt: str) -> str:
    """Replaces {customer_id} placeholder with GOOGLE_ADS_CUSTOMER_ID env var."""
    customer_id = os.environ.get("GOOGLE_ADS_CUSTOMER_ID", "1234567890")
    return prompt.replace("{customer_id}", customer_id)


def call_tool(name: str, arguments: dict) -> Dict[str, Any]:
    """Runs the server and calls a specific tool."""
    with initialized_server() as process:
        send_request(
            process,
            "tools/call",
            {"name": name, "arguments": arguments},
            req_id=2,
        )
        response = read_response(process)

        if "error" in response:
            raise RuntimeError(f"tools/call failed: {response['error']}")

        return response["result"]
