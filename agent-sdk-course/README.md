# Claude Agent SDK: Hands-On Course

Eight short, runnable Python lessons that take you from your first `query()` call to multi-agent orchestration. Each lesson maps to a domain of the **Claude Certified Architect – Foundations** exam. The study plan is in [STUDY_PLAN.md](STUDY_PLAN.md).

## 1. Setup (about 5 minutes)

**Prerequisites:** Python 3.10+ and Node.js 18+. The SDK drives the Claude Code CLI under the hood.

```bash
# from the repo root
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r agent-sdk-course/requirements.txt

# The CLI the SDK talks to (recent SDK versions bundle it, but installing it is harmless)
npm install -g @anthropic-ai/claude-code

# Credentials: pick ONE
export ANTHROPIC_API_KEY=sk-ant-...  # from console.anthropic.com
# or use Bedrock / Vertex: CLAUDE_CODE_USE_BEDROCK=1 / CLAUDE_CODE_USE_VERTEX=1

# Smoke test
cd agent-sdk-course
python lessons/01_hello_query.py
```

If you'd rather use TypeScript, install `npm i @anthropic-ai/claude-agent-sdk`. The concepts are the same, and the API is `query({ prompt, options })` with camelCase option names.

Each run costs a few cents. The lessons cap `max_turns`, and you can also set `max_budget_usd` in `ClaudeAgentOptions`.

## 2. The mental model

```
your code ──query(prompt, options)──▶ Claude Code harness ──▶ Claude
    ▲                                   │  agent loop:
    │                                   │  think → call tool → observe → repeat
    └──── stream of Messages ◀──────────┘  (hooks + permissions gate every tool call)
          SystemMessage · AssistantMessage · UserMessage(tool results) · ResultMessage
```

- **`query()`**: one-shot and stateless. Each call starts a new session.
- **`ClaudeSDKClient`**: a stateful, interactive client. It supports multi-turn conversations, interrupts, and `can_use_tool`.
- **`ClaudeAgentOptions`**: all configuration goes here: tools, permissions, hooks, subagents, MCP servers, model, budget, and output schema.
- **Where it fits:** the Messages API is for a single call. The API Tool Runner loops over your own tools. The **Agent SDK** is the full Claude Code harness with built-in tools that you host yourself. **Managed Agents** gives you the harness plus hosting by Anthropic. Expect exam questions that ask you to choose between these.

## 3. Lessons

| # | File | You learn | Exam domain |
|---|------|-----------|-------------|
| 1 | `01_hello_query.py` | `query()`, the message stream, `ResultMessage` (cost, session) | D1 Agentic architecture |
| 2 | `02_builtin_tools.py` | Built-in tools, `allowed_tools`/`disallowed_tools`, `permission_mode`, `cwd` | D1, D3 |
| 3 | `03_custom_tools_mcp.py` | `@tool` + `create_sdk_mcp_server`, `mcp__server__tool` naming, `is_error` | D2 Tool design & MCP |
| 4 | `04_hooks_guardrails.py` | `PreToolUse` deny, `PostToolUse` audit, `HookMatcher` | D3, D5 |
| 5 | `05_human_in_the_loop.py` | `can_use_tool`, `PermissionResultAllow/Deny`, `ClaudeSDKClient` | D1, D5 |
| 6 | `06_sessions.py` | Multi-turn, `resume`, `fork_session`, compaction | D5 Context & reliability |
| 7 | `07_subagents.py` | `AgentDefinition`, orchestrator and specialists, context isolation | D1 (27%, the largest) |
| 8 | `08_structured_output.py` | `output_format` JSON schema, `structured_output` | D4 Prompting & structured output |

Run any lesson from `agent-sdk-course/` with `python lessons/NN_name.py`. Agents only touch `sandbox/`, which git ignores.

**How to study each lesson:**
1. Read the docstring.
2. Predict what will happen.
3. Run it.
4. Do the "Try next" or one of the exercises below.

## 4. Exercises (do these; they're what make you an expert)

1. **L2:** Switch to `permission_mode="plan"`. What changes, and when would you use plan mode in production?
2. **L3:** Add a `get_price` tool, then make `reorder` refuse quantities over 100 by returning `is_error`. Check that Claude recovers.
3. **L4:** Add a `UserPromptSubmit` hook that injects today's date as context. Then add a `Stop` hook that blocks stopping until a file exists.
4. **L5:** Make the approver rewrite `Write` paths so they always land inside `sandbox/` by editing `updated_input`.
5. **L6:** Fork a session twice with different follow-ups and compare the two results.
6. **L7:** Add a `critic` subagent that reviews `SUMMARY.md`. Then look at cost per model in `ResultMessage.model_usage`.
7. **L8:** Extract structured invoices from three messy text files in `sandbox/`. Add validation and a retry.
8. **Capstone:** Build a customer-support agent (one of the exam scenarios) with custom tools for order lookup and refunds, a hook that blocks refunds over $500 without approval, a structured final report, and a `max_budget_usd`.

## 5. Official references

- Agent SDK docs: <https://code.claude.com/docs/en/agent-sdk/overview>
- Python API reference: <https://code.claude.com/docs/en/agent-sdk/python>
- Python SDK repo (examples folder): <https://github.com/anthropics/claude-agent-sdk-python>
- Anthropic Academy (free courses and the exam): <https://anthropic.skilljar.com>
