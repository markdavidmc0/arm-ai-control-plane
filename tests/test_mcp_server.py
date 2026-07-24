import pytest
import json
from src.control_plane.mcp_server import mcp


@pytest.mark.asyncio
async def test_fastmcp_tool_registration():
    """Verify that the FastMCP server has registered the target tools."""
    tools = await mcp.list_tools()
    assert len(tools) >= 1

    tool_names = [t.name for t in tools]
    assert "profile_and_optimize_kernel" in tool_names


@pytest.mark.asyncio
async def test_profile_and_optimize_kernel_tool_execution():
    """Verify that execution of profile_and_optimize_kernel returns the performance report."""
    naive_code = "void naive_mul() { C[i] += A[i] * B[i]; }"

    # Execute the FastMCP tool
    report = await mcp.call_tool(
        "profile_and_optimize_kernel", arguments={"source_code": naive_code}
    )

    # Access the text content from the ToolResult object
    report_text = report.content[0].text

    # Assert formatting structure of results
    assert "Arm Silicon Optimization Results" in report_text
    assert "Engine Configuration" in report_text
    assert "Naive Scalar" in report_text
    assert "Arm KleidiAI Mode" in report_text
    assert "Hand-Vectorized Neon Mode" in report_text
    assert "Recommended Patch" in report_text
    assert "vmlaq_f32" in report_text


@pytest.mark.asyncio
async def test_fastmcp_resource_registration():
    """Verify that the FastMCP server has registered the heatmap resource."""
    resources = await mcp.list_resources()
    assert len(resources) >= 1

    uris = [str(r.uri) for r in resources]
    assert "mvcp://heatmap/latest" in uris


@pytest.mark.asyncio
async def test_read_heatmap_resource():
    """Verify that reading the heatmap resource returns color-coded visual Heatmap cells."""
    result = await mcp.read_resource("mvcp://heatmap/latest")

    # Access the raw text string inside the ResourceResult contents
    content_str = result.contents[0].content

    data = json.loads(content_str)
    assert "heatmap" in data
    assert "task_id" in data
    assert len(data["heatmap"]) == 45

    # Assert first-class data elements
    cells = data["heatmap"]
    assert any(cell["line"] == 17 for cell in cells)
