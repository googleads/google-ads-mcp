"""Offline stdio handshake against the separately installed editing entry."""

import asyncio
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    executable = Path(sys.executable).with_name("google-ads-mcp-editing.exe")
    if sys.platform != "win32":
        executable = Path(sys.executable).with_name("google-ads-mcp-editing")
    async with stdio_client(
        StdioServerParameters(command=str(executable))
    ) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            response = await session.list_tools()
            names = {tool.name for tool in response.tools}
            assert {
                "customers_list_accessible_customers",
                "search_search",
                "metadata_get_resource_metadata",
                "editing_apply_proposal",
                "editing_prepare_negative_list",
                "intelligence_audit_search_terms",
                "intelligence_prepare_mined_negatives",
                "intelligence_analyze_impression_share",
                "intelligence_audit_devices_and_geos",
                "intelligence_audit_budget_pacing",
                "intelligence_check_account_health",
            } <= names
            assert len(names) == 21, names
            print(f"LOCAL_STDIO_CATALOG_OK: {len(names)} tools; no API calls")


if __name__ == "__main__":
    asyncio.run(main())
