# Spending your $100 credit wisely

## Where the money goes

| Activity | What pays for it | Typical cost |
|---|---|---|
| Running lessons on your own computer | Your **API credit** (console.anthropic.com) | $0.03–0.10 per run on Haiku |
| Chatting with Claude in a cloud Claude Code session like this one | Your **Claude plan usage**, not normally API credit | Tokens, plus a container while the session is active |
| Container time (the cloud computer itself) | Included with the session; it shuts down on its own when idle | Nothing to switch off |

Check which balance your $100 is in:
- **console.anthropic.com → Billing:** API credit. The lessons spend this.
- **claude.ai → Settings → Usage:** plan usage. Cloud sessions spend this.

## Rules that save the most

1. **Run lessons on your own computer, not in the cloud.** Code runs for free locally; you only pay for the model calls. Use cloud sessions to *ask questions* and *get your code reviewed*.
2. **Stay on Haiku while learning.** You're learning the SDK, not testing model intelligence. Switch to `COURSE_MODEL=sonnet` only to compare a result once.
3. **Never remove `max_turns` or `max_budget_usd`.** A looping agent without them is the only way to burn real money fast.
4. **Set a spend limit in the Console:** Settings → Limits, for example $20/month. This is your safety net if a script misbehaves.
5. **Read before you run.** Predicting the output is where the learning happens. Re-running the same lesson ten times teaches you nothing new.
6. **Keep prompts and tool outputs small.** Cost scales with tokens, so don't have agents read huge files or whole folders "just in case".
7. **Check `total_cost_usd`** printed at the end of every run (`== done: ... cost=$...`). Seeing it builds the habit the exam's cost questions test.

## Using cloud sessions efficiently

- **Batch your questions:** one message with three questions beats three sessions.
- **Continue the same session** instead of starting new ones. A new session re-reads everything from scratch.
- **Ask for explanations, not re-runs**, unless you actually need output you can't get locally.
- **Paste the error** when stuck, instead of asking me to reproduce it.

## Suggested budget ($100)

| Use | Budget |
|---|---|
| Lessons 1–8 and exercises (Haiku) | $5 |
| Capstone project (Haiku, a few Sonnet comparisons) | $10 |
| Experiments of your own | $15 |
| **Reserve**: leave it untouched | $70 |

You should finish the whole course using **less than a third** of the credit.
