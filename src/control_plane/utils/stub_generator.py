"""Utility for converting FastMCP/JSON-RPC tool definitions into Python function stubs for CodeMode."""

from typing import Any


def generate_python_stub(
    tool_name: str,
    description: str,
    input_schema: dict[str, Any],
) -> str:
    """Generates a Python function stub string for a single tool schema.

    Args:
        tool_name: Name of the tool.
        description: Description of tool capability.
        input_schema: JSON Schema defining parameters.

    Returns:
        Python async function definition string.
    """
    properties = input_schema.get("properties", {})
    required_params = input_schema.get("required", [])

    param_list = []
    for param_name, param_info in properties.items():
        param_type = param_info.get("type", "Any")
        type_hint = (
            "str" if param_type == "string" else ("int" if param_type == "integer" else "Any")
        )
        if param_name not in required_params:
            param_list.append(f"{param_name}: {type_hint} = None")
        else:
            param_list.append(f"{param_name}: {type_hint}")

    params_str = ", ".join(param_list)
    doc_indent = "    "
    return (
        f"async def {tool_name}({params_str}) -> dict[str, Any]:\n"
        f'{doc_indent}"""{description}"""\n'
        f"{doc_indent}pass"
    )


def generate_catalog_stubs(tools: list[dict[str, Any]]) -> str:
    """Generates combined Python function stubs for a catalog of tools.

    Args:
        tools: List of tool definition dictionaries.

    Returns:
        Multiline string of python async function stubs.
    """
    stubs = []
    for tool in tools:
        name = tool.get("name", "")
        desc = tool.get("description", "")
        schema = tool.get("inputSchema") or tool.get("input_schema") or {}  # noqa: N815
        if name:
            stubs.append(generate_python_stub(name, desc, schema))
    return "\n\n".join(stubs)
