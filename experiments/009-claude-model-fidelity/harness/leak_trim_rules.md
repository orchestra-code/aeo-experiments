# Leaked-prompt trim rules (experiment 009)

The leaked claude.ai system prompt is never committed. This file records only
where it came from, which sections the trim removes, and why. The prompt text
itself, the trimmed templates and the manifest (hashes, char counts, token
counts) live under `data/raw/system_prompts/`, which is gitignored.
`harness/leak_prompt.py` applies these rules mechanically.

## Source

- Repository: `asgeirtj/system_prompts_leaks`, file `Anthropic/claude-opus-5.5.md`
- Pinned commit: `17200e1475ae6ecfa55383f7988efcb706c48bb3`
  ("Add Claude Opus 5.5 system prompt (claude.ai)", 2026-09-22)
- Size as fetched: 477,019 characters, 65,464 words. `count_tokens` puts it at
  158,640 tokens on Opus 5.5 and Sonnet 5, and 120,691 on Haiku 4.5. That is
  about three times the plan's estimate of 37k words; most of the difference is
  the tool definitions block.

## Two variants

| Variant | File (data/raw/system_prompts/) | Used by |
|---|---|---|
| `raw` | `claude-opus-5.5.full.template.md` | pilot comparison only (`--leak-variant raw`) |
| `trimmed` | `claude-opus-5.5.trimmed.template.md` | every `*_leak` arm (default) |

Both variants drop the leaker's own per-user context (see below). The trimmed
variant is about 18,100 tokens on Opus 5.5 and Sonnet 5 and 12,500 on Haiku 4.5.

## Rules

1. The prompt is split on top-level `# name` headings, ignoring lines inside
   code fences. Every top-level section must be listed in the script as kept,
   removed, or partially kept. An unlisted section stops the script, so a new
   commit cannot be trimmed without review.
2. **Kept whole:** `claude_behavior`, `preferences_info`, `search_instructions`
   (except two cuts, rule 4), `thinking_behavior` (except rule 5).
3. **Removed whole** (trimmed variant only), because the API arms attach none
   of these tools or features:
   - memory: `memory_filesystem`, `privacy_requirements` (memory-save consent),
     `memory_application_instructions`, `forbidden_memory_phrases`,
     `appropriate_boundaries_re_memory`, `memory_application_examples`,
     `preferences_guardrails` (filters on the memory preferences block)
   - `end_conversation_tool_info`
   - artifacts and files: `persistent_storage_for_artifacts`,
     `publishing_artifacts`, `computer_use`, `available_skills`,
     `network_configuration`, `filesystem_configuration`
   - visual tools: `request_evaluation_checklist`,
     `when_to_use_visualizer_for_inline_visuals`
   - connector and plugin suggestions: `mcp_app_suggestions`,
     `suggest_catalog_plugins_and_skills`
   - past chats: `past_chats_tools`
4. **Cut inside `search_instructions`** (trimmed only): the
   `using_image_search_tool` block and the paragraph that introduces
   `web_search_fast`. Neither tool exists on the API.
5. **Partially kept** (trimmed only):
   - `Tools`: about 264,000 characters of claude.ai tool JSON definitions are
     removed (the API sends its own `web_search` definition). The section's
     tail is kept: the identity preamble, the current-date line and the
     chat-surface line.
   - `anthropic_api_in_artifacts`: the guide to calling the API from inside an
     artifact is removed. Its tail is kept: `citation_instructions` and the
     user-location line.
6. **Per-user context removed from both variants:** the end of
   `thinking_behavior` holds the leaker's saved preference and memory
   snapshot. It is not part of the base prompt and would bias answer length.
7. **Slots** (both variants): the leak's capture date (long form with weekday,
   and short form) becomes `{{RUN_DATE_LONG}}` / `{{RUN_DATE}}`, and
   the leaker's city becomes `{{USER_LOCATION}}`. `arms.build_params` fills
   them with the run date and the collector's `--user-location`; with no
   location, the location line is dropped.

## Known gaps between the trimmed prompt and claude.ai

- claude.ai also offers `web_search_fast` and `web_fetch`; the API arms attach
  only `web_search`. The kept text still mentions `web_fetch` in a few places.
- The kept `citation_instructions` describe claude.ai's `<cite index=...>`
  markup. In the smoke test no arm wrote those tags as text, and API citations
  came back as structured `citations[]` as usual. The pilot rechecks this.
