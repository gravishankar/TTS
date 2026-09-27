"""Lesson 2 - Built-in tools, working directory and permission modes.

Concepts (CCA domains 1 & 3):
  * The SDK ships Claude Code's tools: Read, Write, Edit, Bash, Glob, Grep,
    WebSearch, WebFetch, Agent (subagents), and more.
  * allowed_tools   = pre-approved (no prompt).  disallowed_tools = removed.
  * permission_mode = "default" | "acceptEdits" | "plan" | "bypassPermissions"
                      | "dontAsk" | "auto".
  * cwd scopes where the agent works. Always sandbox experiments.

Try next: change permission_mode to "plan" and notice Claude only proposes.

Run: python lessons/02_builtin_tools.py
"""

import anyio

from claude_agent_sdk import ClaudeAgentOptions, query
from common import SANDBOX, show


async def main() -> None:
    options = ClaudeAgentOptions(
        cwd=str(SANDBOX),
        allowed_tools=["Read", "Write", "Glob"],
        disallowed_tools=["Bash", "WebFetch", "WebSearch"],
        permission_mode="acceptEdits",
        max_turns=6,
    )
    prompt = (
        "Create notes.md containing a 5-line cheat sheet of Agent SDK "
        "permission modes, then read it back and confirm it exists."
    )
    async for message in query(prompt=prompt, options=options):
        show(message)


if __name__ == "__main__":
    anyio.run(main)
