"""Lesson 1 - The agent loop in one call.

Concepts (CCA domain 1: agentic architecture):
  * query() starts a fresh session, runs Claude's gather -> act -> verify loop,
    and yields every message as it happens.
  * The stream always ends with a ResultMessage (cost, turns, session_id).
  * With no tools allowed, this is just a chat completion routed through the
    Claude Code harness - the "simplest tier" you should reach for first.

Run: python lessons/01_hello_query.py
"""

import anyio

from claude_agent_sdk import ClaudeAgentOptions, query
from common import BUDGET_USD, MODEL, show


async def main() -> None:
    options = ClaudeAgentOptions(
        model=MODEL,
        max_budget_usd=BUDGET_USD,
        system_prompt="You are a concise tutor for the Claude Agent SDK.",
        max_turns=1,
        allowed_tools=[],  # no tools: pure reasoning
    )
    async for message in query(
        prompt="In three bullet points, what is an 'agent loop'?",
        options=options,
    ):
        show(message)


if __name__ == "__main__":
    anyio.run(main)
