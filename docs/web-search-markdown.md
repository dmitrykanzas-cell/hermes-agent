# `web_search_markdown` MVP

Status: experimental MVP in `feat/web-search-markdown`.

## Why this exists

Hermes has two separate web capabilities:

```text
web_search       query -> ranked URLs and snippets
web_extract      URL   -> cleaned page content
```

For research tasks, the agent often needs both. Previously the model had to
call them manually and then join the results itself. This change adds a small
native composition tool:

```text
web_search_markdown
    query
      |
      v
  web_search
      |
      v
  top URLs
      |
      v
  web_extract
      |
      v
  Markdown + provenance
```

The tool deliberately reuses Hermes' existing search and extraction providers.
It does not install Defuddle, add a new network relay, or make Tavily a
requirement.

## What was changed

- Added `web_search_markdown` to `tools/web_tools.py`.
- Added the tool to the `web` toolset and the shared core tool list in
  `toolsets.py`.
- Kept search and extraction as separate capabilities internally.
- Limited search fan-out to 10 results and extraction to 5 pages.
- Returned a per-page `status`, `url`, `snippet`, `extractor`, and Markdown
  content.
- Kept page content as untrusted external data; the normal Hermes web
  extraction path still performs URL validation, SSRF checks, provider
  selection, truncation, and image cleanup.

## Tool contract

```json
{
  "query": "site:support.google.com Gemini in Chrome",
  "search_limit": 5,
  "extract_limit": 3,
  "char_limit": 2500
}
```

The result has this shape:

```json
{
  "success": true,
  "query": "...",
  "search_provider": "...",
  "search_backend_error": null,
  "results": [
    {
      "rank": 1,
      "title": "Page title",
      "url": "https://example.com/page",
      "snippet": "Search result snippet",
      "extractor": "hermes-web-extract",
      "status": "ok",
      "content_markdown": "# Clean page content\n\n..."
    }
  ]
}
```

Behaviour details:

- `search_provider` is `web.search_backend` unless a fallback vendor answered
  (`served_by`), in which case the fallback name is reported.
- Pages are extracted with the normal budget, then page chrome before the first
  H1 and feedback/footer sections are removed, and only then `char_limit` is
  applied (head only, default 8000). Each result carries `truncated`.
- Search runs in `asyncio.to_thread`, so it does not block the event loop.
- A failed extract batch keeps the search hits and marks each as `status: error`.

A page-level extraction failure is returned as one result with
`"status": "error"`; other pages are preserved.

## What was tested

- Python syntax compilation for `tools/web_tools.py` and `toolsets.py`.
- Registration through the live Hermes registry.
- Direct live invocation against Google support search:
  - one search result was selected;
  - extraction returned `status: ok`;
  - Markdown content was returned;
  - no backend error was reported.
- `git diff --check` passed.

The direct handler test was successful in the checked-out source runtime.
The currently installed self-contained Windows `hermes.exe` launcher uses an
older staged code snapshot and does not automatically load this checkout
change. Rebuilding/updating that runtime is intentionally left separate from
this small MVP.

## What remains

### Required before calling this production-ready

1. Add focused automated tests through the registry/dispatcher, not only a
   direct function call.
2. Exercise the tool through a freshly rebuilt Hermes runtime and through the
   Windows launcher.
3. Decide whether the tool should be core in every session or live in a named
   `web`-only surface. The MVP currently follows the existing native web
   surface and is exposed in the shared core list.
4. Add a browser/CDP fallback for JavaScript-heavy pages that ordinary
   extraction cannot read.
5. Decide whether to add an optional local Defuddle extractor. It should remain
   an extractor fallback, not a search provider.
6. Define cache and byte-budget policy for multi-page Markdown results.

### Explicitly not included in this MVP

- No Defuddle installation.
- No new paid provider.
- No change to the default search backend.
- No Tavily dependency.
- No automatic citations synthesis by an LLM.
- No crawling beyond the selected search results.

## Suggested next implementation step

Run the existing Hermes dependency/runtime refresh, then verify this exact
call through a fresh `hermes chat` process:

```text
Use web_search_markdown with:
  query="site:support.google.com Gemini in Chrome"
  search_limit=2
  extract_limit=1
  char_limit=2500
```

Only after that passes should Defuddle or browser fallback work begin.
