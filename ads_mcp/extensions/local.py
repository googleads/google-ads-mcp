"""Explicit local-only entry point for the optional editing profile."""

import importlib.resources
import os


def run():
    if os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_ID") or os.environ.get(
        "GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET"
    ):
        raise RuntimeError(
            "Editing profile supports a single local stdio operator only."
        )
    profile = importlib.resources.files("ads_mcp").joinpath(
        "editing_tools_config.yaml"
    )
    os.environ.setdefault("GOOGLE_ADS_MCP_TOOLS_CONFIG", str(profile))
    from ads_mcp.server import run_server

    run_server()


if __name__ == "__main__":
    run()
