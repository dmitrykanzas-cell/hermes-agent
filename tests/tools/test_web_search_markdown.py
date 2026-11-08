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
        assert char_limit is None  # budget is applied after cleaning, not by web_extract
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


def _patch_search(monkeypatch, web_tools, data, served_by=None):
    payload = {"success": True, "data": {"web": data}}
    if served_by:
        payload["data"]["served_by"] = served_by
    monkeypatch.setattr(web_tools, "web_search_tool", lambda query, limit=5: json.dumps(payload))


@pytest.mark.asyncio
async def test_search_provider_falls_back_to_configured_backend(monkeypatch):
    from tools import web_tools

    _patch_search(monkeypatch, web_tools, [{"position": 1, "url": "https://a.test", "title": "A"}])
    monkeypatch.setattr(web_tools, "_get_search_backend", lambda: "tavily")

    async def fake_extract(urls, format=None, char_limit=None):
        return json.dumps({"results": [{"url": "https://a.test", "content": "# A\n\nbody"}]})

    monkeypatch.setattr(web_tools, "web_extract_tool", fake_extract)

    result = json.loads(await web_tools.web_search_markdown_tool("q", extract_limit=1))
    assert result["search_provider"] == "tavily"


@pytest.mark.asyncio
async def test_served_by_overrides_configured_backend(monkeypatch):
    from tools import web_tools

    _patch_search(monkeypatch, web_tools, [], served_by="ddgs")
    monkeypatch.setattr(web_tools, "_get_search_backend", lambda: "tavily")

    result = json.loads(await web_tools.web_search_markdown_tool("q"))
    assert result["search_provider"] == "ddgs"
    assert result["results"] == []


@pytest.mark.asyncio
async def test_chrome_and_footer_removed_and_budget_applies_to_clean_text(monkeypatch):
    from tools import web_tools

    page = (
        "[Sign in](https://accounts.example)\n\n[Help Center](/)\n\n"
        "# Real title\n\n" + ("Useful sentence. " * 400) + "\n\n"
        "## Was this helpful?\n\nHow can we improve it?\n"
    )
    _patch_search(monkeypatch, web_tools, [{"position": 1, "url": "https://a.test", "title": "A"}], served_by="ddgs")

    async def fake_extract(urls, format=None, char_limit=None):
        return json.dumps({"results": [{"url": "https://a.test", "content": page}]})

    monkeypatch.setattr(web_tools, "web_extract_tool", fake_extract)

    result = json.loads(await web_tools.web_search_markdown_tool("q", extract_limit=1, char_limit=2500))
    item = result["results"][0]
    assert item["content_markdown"].startswith("# Real title")
    assert "Sign in" not in item["content_markdown"]
    assert "Was this helpful" not in item["content_markdown"]
    assert item["truncated"] is True
    assert len(item["content_markdown"]) < 2500 + 100


@pytest.mark.asyncio
async def test_batch_extract_failure_keeps_search_hits(monkeypatch):
    from tools import web_tools

    _patch_search(
        monkeypatch, web_tools,
        [{"position": 1, "url": "https://a.test", "title": "A", "description": "snip"}],
        served_by="ddgs",
    )

    async def boom(urls, format=None, char_limit=None):
        raise RuntimeError("provider down")

    monkeypatch.setattr(web_tools, "web_extract_tool", boom)

    result = json.loads(await web_tools.web_search_markdown_tool("q", extract_limit=1))
    assert result["success"] is True
    assert result["results"][0]["status"] == "error"
    assert "provider down" in result["results"][0]["error"]
    assert result["results"][0]["snippet"] == "snip"


def test_clean_markdown_without_h1_keeps_content():
    from tools.web_tools import _clean_markdown

    text, truncated = _clean_markdown("plain page without heading")
    assert text == "plain page without heading"
    assert truncated is False


def test_tool_is_registered_and_in_toolsets():
    import toolsets
    from tools import web_tools  # registers the tool
    from tools.registry import registry

    assert "web_search_markdown" in registry.get_tool_names_for_toolset("web")
    assert "web_search_markdown" in toolsets.TOOLSETS["web"]["tools"]
    assert "web_search_markdown" in toolsets._HERMES_CORE_TOOLS
    entry = registry.get_entry("web_search_markdown")
    assert entry is not None and entry.is_async
