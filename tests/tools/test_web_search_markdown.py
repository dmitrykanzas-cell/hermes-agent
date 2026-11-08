"""Tests for the search -> Markdown composition tool."""

import json

import pytest


@pytest.mark.asyncio
async def test_search_markdown_extracts_selected_results(monkeypatch):
    from tools import web_tools

    monkeypatch.setattr(
        web_tools,
        "web_search_tool",
        lambda query, limit=5: json.dumps({
            "success": True,
            "data": {
                "web": [
                    {"position": 1, "title": "First", "url": "https://first.test", "description": "one"},
                    {"position": 2, "title": "Second", "url": "https://second.test", "description": "two"},
                ],
                "served_by": "ddgs",
            },
        }),
    )

    async def fake_extract(urls, format=None, char_limit=None):
        assert urls == ["https://first.test"]
        assert format == "markdown"
        assert char_limit == 2500
        return json.dumps({"results": [{
            "url": "https://first.test",
            "title": "First page",
            "content": "# First page\n\nClean content.",
        }]})

    monkeypatch.setattr(web_tools, "web_extract_tool", fake_extract)

    result = json.loads(await web_tools.web_search_markdown_tool(
        "example query", search_limit=2, extract_limit=1, char_limit=2500
    ))

    assert result["success"] is True
    assert result["search_provider"] == "ddgs"
    assert len(result["results"]) == 1
    assert result["results"][0]["status"] == "ok"
    assert result["results"][0]["content_markdown"].startswith("# First page")


@pytest.mark.asyncio
async def test_search_markdown_preserves_page_failure(monkeypatch):
    from tools import web_tools

    monkeypatch.setattr(
        web_tools,
        "web_search_tool",
        lambda query, limit=5: json.dumps({
            "success": True,
            "data": {"web": [{"position": 1, "url": "https://blocked.test", "title": "Blocked"}]},
        }),
    )

    async def fake_extract(urls, format=None, char_limit=None):
        return json.dumps({"results": [{
            "url": "https://blocked.test",
            "error": "Content was inaccessible or not found",
        }]})

    monkeypatch.setattr(web_tools, "web_extract_tool", fake_extract)

    result = json.loads(await web_tools.web_search_markdown_tool("query", extract_limit=1))

    assert result["results"][0]["status"] == "error"
    assert "inaccessible" in result["results"][0]["error"]


@pytest.mark.asyncio
async def test_search_markdown_rejects_empty_query():
    from tools import web_tools

    result = json.loads(await web_tools.web_search_markdown_tool("  "))

    assert result["success"] is False
    assert "non-empty" in result["error"]
