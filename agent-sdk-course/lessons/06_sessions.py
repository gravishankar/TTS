"""Lesson 6 - Multi-turn conversations and session resume.

Concepts (CCA domain 5: context management):
  * ClaudeSDKClient keeps one conversation open across many query() calls.
  * Every run has a session_id (on the ResultMessage). Pass it later as
    ClaudeAgentOptions(resume=session_id) to continue from disk, or add
    fork_session=True to branch without mutating the original.
  * Context is finite: long sessions are auto-compacted (PreCompact hook fires).

Run: python lessons/06_sessions.py
"""

import anyio

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, query
from common import show


async def main() -> None:
    session_id = None
    async with ClaudeSDKClient(options=ClaudeAgentOptions(max_turns=1)) as client:
        await client.query("My favourite exam domain is tool design. Remember it.")
        async for message in client.receive_response():
            show(message)
        await client.query("Which domain did I say?")  # same conversation
        async for message in client.receive_response():
            show(message)
            if isinstance(message, ResultMessage):
                session_id = message.session_id

    print("\n--- resuming from disk in a brand-new query() ---")
    async for message in query(
        prompt="Remind me once more what my favourite domain is.",
        options=ClaudeAgentOptions(resume=session_id, max_turns=1),
    ):
        show(message)


if __name__ == "__main__":
    anyio.run(main)
