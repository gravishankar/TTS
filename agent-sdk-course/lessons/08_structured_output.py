"""Lesson 8 - Structured output with a JSON schema.

Concepts (CCA domain 4: prompt engineering & structured output):
  * output_format={"type": "json_schema", "schema": {...}} makes the final
    answer machine-readable; read it from ResultMessage.structured_output.
  * Prefer schemas over "please reply in JSON" prompts - validation beats hope.
  * Still validate downstream and handle is_error results.

Run: python lessons/08_structured_output.py
"""

import json

import anyio

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

SCHEMA = {
    "type": "object",
    "properties": {
        "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
        "topics": {"type": "array", "items": {"type": "string"}},
        "urgent": {"type": "boolean"},
    },
    "required": ["sentiment", "topics", "urgent"],
    "additionalProperties": False,
}


async def main() -> None:
    ticket = "The export button crashed again and our board meeting is in an hour!!"
    options = ClaudeAgentOptions(
        output_format={"type": "json_schema", "schema": SCHEMA},
        allowed_tools=[],
        max_turns=3,
    )
    async for message in query(prompt=f"Classify this support ticket:\n{ticket}", options=options):
        if isinstance(message, ResultMessage):
            if message.is_error:
                print("Failed:", message.subtype, message.errors)
            else:
                print(json.dumps(message.structured_output, indent=2))


if __name__ == "__main__":
    anyio.run(main)
