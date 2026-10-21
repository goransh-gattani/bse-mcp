"""The MCP layer: tools are listed with schemas, run over the protocol, and errors keep their message."""
import asyncio

import pytest

from bse_mcp import server as S

EXPECTED = ["search_scrips", "get_quote", "get_market_depth", "get_peers", "get_financials",
            "get_announcements", "download_announcement_pdf", "list_scrips", "call_bse_api",
            "analyze_fundamentals", "analyze_prices"]


def run(coro):
    return asyncio.run(coro)


def text_of(result):
    content = getattr(result, "content", None) or (result[0] if isinstance(result, tuple) else result)
    return "".join(getattr(c, "text", "") for c in content)


def test_tools_listed_with_schemas():
    tools = run(S.server.list_tools())
    assert [t.name for t in tools] == EXPECTED
    quote = next(t for t in tools if t.name == "get_quote")
    schema = getattr(quote, "inputSchema", None) or quote.input_schema
    assert schema["required"] == ["scripcode"] and "Live price" in quote.description


def test_call_tool_returns_content(fake):
    assert "500002" in text_of(run(S.server.call_tool("search_scrips", {"query": "abb"})))
    assert "Q1 FY27" in text_of(run(S.server.call_tool("get_financials", {"scripcode": "500002", "quarters": 2})))


@pytest.mark.parametrize("args, needle, refuse", [
    ({"scripcode": "xyz"}, "search_scrips", None),
    ({"scripcode": "500002"}, "HTTP 403", "getScripHeaderData"),
])
def test_error_messages_reach_the_model(fake, args, needle, refuse):
    if refuse:
        fake.refuse.add(refuse)
    with pytest.raises(Exception) as info:
        run(S.server.call_tool("get_quote", args))
    assert needle in str(info.value)
    assert type(info.value).__name__ != "UnexpectedToolError", "would reach the model as a bare 'Error executing tool'"
