# Road to Claude Certified Architect – Foundations

## The exam at a glance

- **60 scenario-based multiple-choice questions in 120 minutes.** You need 720/1000 to pass.
- **No pure recall.** Every question asks you to pick the *best architectural decision* for a situation.
- **Scenarios:** each sitting draws 4 of these 6.
  - Customer Support Resolution Agent
  - Code Generation with Claude Code
  - Multi-Agent Research System
  - Developer Productivity with Claude
  - Claude Code for CI/CD
  - Structured Data Extraction
- **Registration and prep:** Anthropic Academy at <https://anthropic.skilljar.com>. Check there for current price, delivery, and eligibility, since these change.

| Domain | Weight | What "expert" looks like | Lessons |
|---|---|---|---|
| D1 Agentic Architecture & Orchestration | **27%** | Knows when *not* to build an agent (single call → workflow → agent); knows the agent loop, orchestrator/subagent topologies, task decomposition, parallel vs sequential, stop conditions | 1, 2, 5, 7 |
| D2 Tool Design & MCP Integration | 18% | Designs tools with one clear job, precise descriptions and typed schemas, returns errors as `is_error`, knows MCP servers (stdio/HTTP/in-process), tool naming, least privilege | 3 |
| D3 Claude Code Configuration & Workflows | 20% | Knows CLAUDE.md hierarchy, settings.json, permission modes and rules, hooks, slash commands, skills, subagents, headless `claude -p` in CI/CD, plugins | 2, 4 + Claude Code docs |
| D4 Prompt Engineering & Structured Output | 20% | Writes clear system prompts, examples, and XML structure; prefers JSON-schema outputs over "reply in JSON"; handles validation and retry | 8 |
| D5 Context Management & Reliability | 15% | Knows context-window budgeting, compaction, subagents for context isolation, sessions/resume/fork, prompt caching, guardrails, evals, cost/turn/budget limits, error handling | 4, 5, 6 |

## 4-week plan (about 1 hour a day)

**Week 1: Foundations (D1, D4)**
- Anthropic Academy: *Claude 101*, *Building with the Claude API*, and the prompt engineering course.
- Read "Building effective agents" on anthropic.com/engineering. It covers the workflow patterns: prompt chaining, routing, parallelization, orchestrator-workers, and evaluator-optimizer.
- Do lessons 1, 2, and 8 plus exercises 1 and 7.

**Week 2: Tools and MCP (D2)**
- Academy: *Introduction to Model Context Protocol* and *MCP: Advanced Topics*.
- Read "Writing effective tools for agents" on anthropic.com/engineering.
- Do lesson 3 and exercise 2. Then wrap a real API you use (weather, GitHub, or a database) as an MCP tool.

**Week 3: Claude Code and guardrails (D3, D5)**
- Academy: *Claude Code in Action*.
- Read the Claude Code docs pages on memory (CLAUDE.md), settings, permissions, hooks, subagents, skills, and headless/GitHub Actions.
- Do lessons 4, 5, and 6 plus exercises 3 to 5.
- Run `claude -p "..." --output-format json` in a shell script so it feels like CI.

**Week 4: Orchestration and exam practice (D1, D5)**
- Do lesson 7, exercise 6, and the **capstone**.
- Read "How we built our multi-agent research system" and "Effective context engineering for AI agents" on anthropic.com/engineering.
- Take the official practice exam (if offered) plus timed mock sets, and review every wrong answer against the table above.

## Decision heuristics the exam rewards

1. **Start simple.** Use a single call if it works, then a scripted workflow, and an agent only when the path genuinely can't be known in advance.
2. **Enforce guarantees in code.** If something must *always* or *never* happen, put it in a hook, a permission rule, or `can_use_tool`, not only the prompt.
3. **Use least privilege.** Give an agent or subagent only the tools it needs, scope `cwd`, and prefer `allowed_tools` over `bypassPermissions`.
4. **Use subagents for context isolation and parallelism,** not just for organization. Only their summary comes back.
5. **Use schemas over pleading.** For machine-readable output, use JSON schema / structured outputs, and validate downstream.
6. **Tools fail informatively.** Return `is_error` with a message that helps the model recover, rather than crashing the loop.
7. **Bound every loop** with `max_turns`, `max_budget_usd`, timeouts, and a human checkpoint for irreversible actions.
8. **Manage context deliberately.** Keep stable content first so it caches, compact long sessions, and retrieve just in time instead of stuffing the window.
9. **Evaluate.** Build test sets for agent behavior, and measure cost per *completed task*, not per request.

## Self-check questions (answers at the bottom)

1. A support agent occasionally issues refunds above policy even though the system prompt forbids it. What's the most reliable fix?
   A) Repeat the rule in capitals. B) Add few-shot examples. C) A PreToolUse hook / `can_use_tool` check that denies refunds above the threshold. D) Switch to a larger model.
2. A research agent's context fills up after reading 40 documents, and answer quality drops. What's the best change?
   A) Raise `max_turns`. B) Delegate per-document reading to subagents that return summaries. C) Put all documents in the system prompt. D) Turn off tools.
3. You need to extract invoice fields from 10k PDFs nightly with no interaction. What's the simplest correct design?
   A) Multi-agent orchestrator. B) Single call per document with a JSON-schema output, run in batch, with validation. C) An interactive `ClaudeSDKClient` session. D) A Stop hook.
4. Your CI job runs Claude Code on every PR. How should you configure permissions?
   A) `bypassPermissions` everywhere. B) An explicit allow list for the needed tools and commands, a scoped working directory, and deny rules for network and destructive commands. C) Interactive approval prompts. D) No tools.
5. Two custom tools named `search` and `lookup` are confused by the model constantly. What's the first fix?
   A) Rewrite the descriptions to state each tool's distinct purpose, inputs, and when to use it, or merge them. B) Add retries. C) Increase effort. D) Use a subagent.

Answers: 1-C, 2-B, 3-B, 4-B, 5-A.
