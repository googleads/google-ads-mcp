"""Regression: update_references must import cleanly (the console-script
entry point loads it). A bare `import utils` broke it with ModuleNotFoundError."""


def test_update_references_imports_and_exposes_entry_point():
    import ads_mcp.update_references as mod

    assert callable(mod.update_gaql_resource_file)
