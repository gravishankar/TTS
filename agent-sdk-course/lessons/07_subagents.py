"""Lesson 7 - Orchestrator + subagents.

Concepts (CCA domain 1, the heaviest-weighted):
  * agents={name: AgentDefinition(...)} registers specialists. The main agent
    delegates through the "Agent" tool.
  * Each subagent gets a FRESH context window: only its final report returns
    to the orchestrator. That is the main reason to use them - context
    isolation - plus parallelism and least-privilege tool sets.
  * Give each subagent a narrow description (it drives routing), minimal
    tools, and optionally a cheaper model.

Run: python lessons/07_subagents.py
"""

import anyio

from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, query
from common import BUDGET_USD, MODEL, SANDBOX, show

AGENTS = {
    "researcher": AgentDefinition(
        description="Reads files in the workspace and summarises facts. Use for any fact-finding.",
        prompt="You gather facts from files. Report findings as terse bullets with file names.",
        tools=["Read", "Glob", "Grep"],
        model="haiku",
    ),
    "writer": AgentDefinition(
        description="Writes polished markdown documents from provided notes.",
        prompt="You turn notes into a clear, well-structured markdown document.",
        tools=["Write"],
        model="sonnet",
    ),
}


async def main() -> None:
    options = ClaudeAgentOptions(
        model=MODEL,
        max_budget_usd=BUDGET_USD,
        cwd=str(SANDBOX),
        agents=AGENTS,
        allowed_tools=["Agent", "Read", "Glob", "Grep", "Write"],
        permission_mode="acceptEdits",
        max_turns=12,
    )
    prompt = (
        "Use the researcher subagent to inventory every file in this folder, "
        "then the writer subagent to produce SUMMARY.md from its findings."
    )
    async for message in query(prompt=prompt, options=options):
        show(message)


if __name__ == "__main__":
    anyio.run(main)
