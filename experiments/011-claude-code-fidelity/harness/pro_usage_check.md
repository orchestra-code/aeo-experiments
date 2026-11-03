# Experiment 011: Pro plan usage check

Measures how much of a Claude Pro plan's limits one tracking answer uses in Claude
Code. It runs 10 answers, one at a time, on the Pro account, and takes about 15
minutes. The answers are never used as study data.

Run this in your own terminal on the Mac that has the `aeo-experiments` checkout. A
person has to do step 2, because signing in opens a browser. The Pro login goes in
its own folder, so the Claude Code login you normally use is not touched.

## Before you start

- Pick a time when nothing else is using the Pro account. Do not run this during a
  claude.ai collection session or within 5 hours of one, because both draw on the
  same limits and the reading would mix them.
- The check stops by itself if the five-hour window reaches 60% or the seven-day
  window reaches 50%.

## Steps

1. Go to the repo and the study branch:

   ```bash
   cd ~/projects/aeo-experiments
   git switch exp011-claude-code-fidelity
   ```

2. Sign in to the **Pro** account, in its own folder:

   ```bash
   env -u ANTHROPIC_API_KEY CLAUDE_CONFIG_DIR="$HOME/.claude-exp011-pro" \
     experiments/011-claude-code-fidelity/data/raw/bin/claude-2.1.316 auth login
   ```

   Choose the option for a Claude subscription, not an API key, and sign in with the
   Pro account's email.

3. Run the check:

   ```bash
   uv run python experiments/011-claude-code-fidelity/harness/collect_cc.py usage-check \
     --config-dir "$HOME/.claude-exp011-pro"
   ```

   It refuses to start unless that folder holds a logged-in Pro account.

4. Paste the last three lines it prints (answers finished, five-hour window, seven-day
   window) into the Claude Code session running this study. They are also saved in
   `experiments/011-claude-code-fidelity/data/raw/ledger_usage_check.jsonl`.

5. When the study is finished, sign the folder out and delete it:

   ```bash
   env -u ANTHROPIC_API_KEY CLAUDE_CONFIG_DIR="$HOME/.claude-exp011-pro" \
     experiments/011-claude-code-fidelity/data/raw/bin/claude-2.1.316 auth logout
   rm -rf "$HOME/.claude-exp011-pro"
   ```

## If something goes wrong

- **"expected a logged-in pro account":** step 2 signed in to a different account or
  did not finish. Repeat step 2.
- **A window was already high at the start:** note it and run again after it resets.
  Rerunning skips answers that already finished.
