"""Shared helper: pretty-print the message stream every lesson produces."""

from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

SANDBOX = Path(__file__).resolve().parent.parent / "sandbox"
SANDBOX.mkdir(exist_ok=True)


def show(message) -> None:
    """Print one message from the agent loop in a readable form."""
    if isinstance(message, SystemMessage):
        print(f"[system:{message.subtype}]")
    elif isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                print(f"Claude: {block.text}")
            elif isinstance(block, ThinkingBlock):
                print("  (thinking...)")
            elif isinstance(block, ToolUseBlock):
                print(f"  -> tool {block.name}({block.input})")
    elif isinstance(message, UserMessage) and isinstance(message.content, list):
        for block in message.content:
            if isinstance(block, ToolResultBlock):
                status = "error" if block.is_error else "ok"
                print(f"  <- tool result [{status}]")
    elif isinstance(message, ResultMessage):
        cost = f"${message.total_cost_usd:.4f}" if message.total_cost_usd else "n/a"
        print(
            f"\n== done: {message.subtype} | turns={message.num_turns} "
            f"| cost={cost} | session={message.session_id}"
        )
