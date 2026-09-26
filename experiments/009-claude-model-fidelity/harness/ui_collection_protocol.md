# claude.ai collection protocol (experiment 009, arms `ui_default` and `ui_think`)

One person collects every UI answer by hand in claude.ai. Automating the
consumer app is against its terms, so nothing here is scripted except the
checklist and the export ingest. Follow the steps in order for every wave.

## Before the first wave (once)

1. Sign in to the claude.ai account used for the whole study, on a paid plan.
   Use the same account, browser and network location for every wave. The
   account signs in from Pittsburgh, and the API arms' `user_location` matches
   it (Pittsburgh, Pennsylvania, US, the collector's default) in every
   confirmatory wave. The pilot's API calls used Boston, a recorded pilot
   deviation.
2. Open **Settings** and switch off everything that personalizes answers:
   - **Memory**: off (the "generate memory from chat history" setting).
   - **Search and reference chats**: off.
   - **Profile / personal preferences** ("What personal preferences should
     Claude consider"): empty.
   - **Styles**: use Normal; no custom style.
   - **Connectors** and integrations: disconnect or disable all of them
     (Gmail, Drive, Calendar and any other MCP connector).
3. Leave every other capability at its account default (artifacts, code
   execution and file creation, and so on) and write down its state in the
   wave log. The study measures a default subscriber, not a stripped one.
4. Never use a **Project**, and never use an **incognito** chat (incognito
   chats are left out of the data export).

## Pilot only: record what the picker offers

In the pilot, before collecting, write down in the wave log:

- the exact model name shown in the picker (expected: Opus 5.5) and whether it
  is the default for a new chat;
- which reasoning control the picker exposes for Opus 5.5 (an extended
  thinking toggle, an effort setting, or nothing), and its default state.

`ui_default` is the picker's default reasoning state. `ui_think` is the other
state the picker offers (extended thinking on, or the higher effort setting).
If the picker offers no reasoning control, `ui_think` is dropped and the spec
records why.

**Observed 2026-09-26 (pilot, fresh Pro account):** the picker shows
"Opus 5.5, Medium reasoning (default)".

- `ui_default` = Opus 5.5 with **Medium** reasoning (the UI default). This
  matches API `output_config.effort: "medium"` on the `opus55_*` arms.
- `ui_think` = Opus 5.5 with **High** reasoning.

TODO (pilot): confirm the exact wording of the higher setting ("High" or
otherwise) and every other option the picker lists, from Jim's pilot notes,
and update this section before wave 1.

## Each wave

**Two sessions per wave.** In the pilot, 10 Opus chats used 11% of the Pro
plan's 5-hour limit, so the 80-chat sheet runs in two sessions on the same
day: rows 1 to 40, then rows 41 to 80 in a later 5-hour window. If the usage
limit interrupts a session, stop, note the row in the wave's notes file, and
resume from that row in the next window. Never start a chat while limited.

1. Generate the wave's checklist (it holds prompt text, so it stays under
   `data/raw/`):

   ```bash
   uv run python experiments/009-claude-model-fidelity/harness/make_ui_sheet.py --wave N
   ```

   Open `data/raw/ui_sheets/wN.csv`. The order is randomized per wave; work
   from the top down and do not reorder.
2. Write the session start time, your approximate location (city), and the
   settings state from steps 2 and 3 above in the wave log.
3. Tell Jim (or run it yourself) to submit the wave's API batch now, so the
   API arms run during the same window as the UI session.
4. For each row of the sheet:
   1. Start a **new chat** (never continue an old one).
   2. Check the model picker shows Opus 5.5 and set the reasoning control for
      the row's arm (`ui_default`: Medium, `ui_think`: High). Check it again before
      sending: the sheet mixes arms, so the setting changes between rows.
   3. Check that web search is on in the search-and-tools menu.
   4. Paste the row's prompt text exactly, with nothing added, and send.
   5. Wait until the answer has finished completely (no spinner, no "searching").
   6. Do not regenerate, edit the prompt, reply, or rate the answer.
   7. Rename the chat to the row's `chat_name` (`wN-arm-item_id`, for example
      `w1-ui_think-b2b_07`). Renaming is metadata only and does not change the
      answer.
   8. Mark the row `done`. Note anything unusual in `notes`: an error, a
      refusal, a usage-limit warning, a model or setting you could not select.
5. **If a chat goes wrong** (error, network failure, usage limit, wrong model
   or wrong reasoning setting noticed after sending): rename it
   `wN-arm-item_id-void`, write the reason in `notes`, and redo the row in a
   fresh chat with the normal name. The ingest never matches a `-void` chat.
   If you hit the plan's usage limit, stop, write the time in the log, and
   resume from the same row when the limit resets.
6. When the sheet is complete, write the session end time in the wave log.

## Export (once per wave, after the last chat)

1. **Settings > Privacy > Export data.** The export arrives by email as a zip.
2. Save the zip, unopened and unrenamed, into
   `experiments/009-claude-model-fidelity/data/raw/ui_exports/wN/`.
3. Run the ingest and read its coverage report:

   ```bash
   uv run python experiments/009-claude-model-fidelity/harness/ingest_claude_export.py --wave N
   ```

   Every expected chat should be matched, with no duplicates or ambiguous
   chats. Rename and re-export if the report lists any, and fix missing rows
   before the next wave.

## What not to do

- Do not use the claude.ai chats for anything else during a wave session.
- Do not change settings between waves. If a setting changes by itself (a
  product update), write it down in the wave log.
- Do not delete any chat until the study's results are frozen.
