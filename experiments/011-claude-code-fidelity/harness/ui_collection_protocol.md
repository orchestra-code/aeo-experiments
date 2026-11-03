# claude.ai collection protocol (experiment 011, arm `ui_default`)

One person collects every claude.ai answer by hand. Nothing here automates the consumer app;
only the checklist and the export ingest are scripted. It is 009's protocol with one arm, on
the same account, so the settings below should already be in place. Check them anyway.

## Before the first wave

1. Sign in to the same claude.ai account as 009. Use the same account, browser and network
   location for every wave.
2. Confirm these settings are still off, and write down what you find in the wave log:
   - **Memory**: off.
   - **Search and reference chats**: off.
   - **Profile / personal preferences**: empty.
   - **Styles**: Normal, no custom style.
   - **Connectors** and integrations: all off.
3. Leave every other capability at its account default and note its state in the wave log.
4. Never use a **Project**, and never use an **incognito** chat (the export leaves those out).

## Each wave

40 chats, one session. In 009's pilot, 10 chats used 11% of the Pro plan's five-hour window, so
one sheet should use about 44%. If the limit interrupts you, stop, note the row and resume from
that row when it resets.

1. Open `experiments/011-claude-code-fidelity/data/raw/ui_sheets/wN.csv`. The order is
   randomized per wave. Work from the top down.
2. Start the wave log at `data/raw/ui_sheets/wN_log.md`: start time, city, and the settings
   state. Note if anything on the account changed by itself.
3. For each row:
   1. Start a **new chat**. Never continue an old one.
   2. Check that the picker shows Opus 5.5 with Medium reasoning.
   3. Check that web search is on in the search-and-tools menu.
   4. Paste the row's `text` exactly, with nothing added, and send.
   5. Wait until the answer has finished completely.
   6. Do not regenerate, edit, reply or rate the answer. If Claude asks a clarifying question,
      leave it unanswered and write that in `notes`. The first reply is what gets scored.
   7. Rename the chat to the row's `chat_name`, for example `e011-w1-ui_default-b2b_07`.
      **The `e011-` prefix matters.** The account still holds 009's chats on the same prompts,
      and the ingest uses this prefix to tell them apart.
   8. Mark the row `done`. Note anything unusual in `notes`.
4. **If a chat goes wrong** (error, network failure, wrong model or setting): rename it
   `e011-wN-ui_default-item_id-void`, note why, and redo the row in a fresh chat.
5. Write the end time in the wave log.

## Export (once per wave, after the last chat)

1. **Settings > Privacy > Export data.** The export arrives by email as a zip.
2. Save the zip, unopened and unrenamed, in `data/raw/ui_exports/wN/`.
3. Tell the study session, or run:

   ```bash
   uv run python experiments/011-claude-code-fidelity/harness/ingest_claude_export.py --wave N
   ```

   It must report 40 of 40, with no duplicates. It will see 009's chats in the export and skip
   them. That is expected.

## What not to do

- Do not use the account's chats for anything else during a wave session.
- Do not change settings between waves.
- Do not delete 009's or this study's chats until the results are frozen.
