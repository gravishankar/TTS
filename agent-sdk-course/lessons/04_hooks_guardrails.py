"""Lesson 4 - Hooks: deterministic guardrails around a probabilistic model.

Concepts (CCA domains 3 & 5: configuration, reliability):
  * Hooks run YOUR code at lifecycle events: PreToolUse, PostToolUse,
    PostToolUseFailure, UserPromptSubmit, Stop, SubagentStart/Stop,
    PreCompact, Notification, PermissionRequest.
  * HookMatcher(matcher="Bash|Write", hooks=[fn]) filters by tool name.
  * A PreToolUse hook can deny a call with
    hookSpecificOutput.permissionDecision = "deny" (+ a reason Claude sees).
  * Exam rule of thumb: if something MUST happen every time, enforce it in a
    hook, not in the prompt. Prompts are guidance; hooks are guarantees.

Run: python lessons/04_hooks_guardrails.py
"""

from typing import Any

import anyio

from claude_agent_sdk import ClaudeAgentOptions, HookMatcher, query
from common import BUDGET_USD, MODEL, SANDBOX, show

BLOCKED = ("rm -rf", "sudo", "curl ", "| sh")
AUDIT_LOG: list[str] = []


async def block_dangerous_bash(input_data: dict[str, Any], tool_use_id, context) -> dict[str, Any]:
    command = input_data["tool_input"].get("command", "")
    if any(pattern in command for pattern in BLOCKED):
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"Blocked by policy: {command!r}",
            }
        }
    return {}


async def audit_every_tool(input_data: dict[str, Any], tool_use_id, context) -> dict[str, Any]:
    AUDIT_LOG.append(f"{input_data['tool_name']}: {input_data['tool_input']}")
    return {}


async def main() -> None:
    options = ClaudeAgentOptions(
        model=MODEL,
        max_budget_usd=BUDGET_USD,
        cwd=str(SANDBOX),
        allowed_tools=["Bash"],
        max_turns=6,
        hooks={
            "PreToolUse": [HookMatcher(matcher="Bash", hooks=[block_dangerous_bash])],
            "PostToolUse": [HookMatcher(hooks=[audit_every_tool])],
        },
    )
    prompt = "Run `ls -la`, then run `rm -rf ./*` to clean up. Report what happened."
    async for message in query(prompt=prompt, options=options):
        show(message)
    print("\nAudit log:", *AUDIT_LOG, sep="\n  ")


if __name__ == "__main__":
    anyio.run(main)
