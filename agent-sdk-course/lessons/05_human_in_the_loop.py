"""Lesson 5 - Human-in-the-loop approval with can_use_tool.

Concepts (CCA domains 1 & 5):
  * can_use_tool(tool_name, input, context) is called for any tool that is
    NOT pre-approved. Return PermissionResultAllow (optionally with a
    modified updated_input) or PermissionResultDeny(message=..., interrupt=?).
  * It needs streaming input, so we use ClaudeSDKClient here.
  * Pattern: auto-allow reads, ask a human for writes, rewrite risky inputs.

Run: python lessons/05_human_in_the_loop.py
"""

import anyio

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)
from common import SANDBOX, show

READ_ONLY = {"Read", "Glob", "Grep"}


async def approve(tool_name: str, tool_input: dict, context: ToolPermissionContext):
    if tool_name in READ_ONLY:
        return PermissionResultAllow(updated_input=tool_input)
    answer = input(f"\nAllow {tool_name} {tool_input}? [y/N] ").strip().lower()
    if answer == "y":
        return PermissionResultAllow(updated_input=tool_input)
    return PermissionResultDeny(message="The human reviewer declined this action.")


async def main() -> None:
    options = ClaudeAgentOptions(cwd=str(SANDBOX), can_use_tool=approve, max_turns=6)
    async with ClaudeSDKClient(options=options) as client:
        await client.query("Write hello.txt containing 'hi', then list the files here.")
        async for message in client.receive_response():
            show(message)


if __name__ == "__main__":
    anyio.run(main)
