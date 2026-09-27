"""Lesson 3 - Your own tools via an in-process MCP server.

Concepts (CCA domain 2: tool design & MCP):
  * @tool(name, description, schema) turns an async function into a tool.
  * create_sdk_mcp_server bundles tools; they run in YOUR process (no subprocess).
  * Tool names are namespaced: mcp__<server>__<tool>.
  * Good tool design: one clear job, precise description, typed inputs,
    informative errors returned as is_error rather than raised exceptions.

Run: python lessons/03_custom_tools_mcp.py
"""

from typing import Any

import anyio

from claude_agent_sdk import ClaudeAgentOptions, create_sdk_mcp_server, query, tool
from common import BUDGET_USD, MODEL, show

INVENTORY = {"widget": 12, "gadget": 0, "doohickey": 7}


@tool(
    "check_stock",
    "Return the units in stock for one product SKU. Use before promising delivery.",
    {"sku": str},
)
async def check_stock(args: dict[str, Any]) -> dict[str, Any]:
    sku = args["sku"].lower()
    if sku not in INVENTORY:
        return {
            "content": [{"type": "text", "text": f"Unknown SKU '{sku}'. Known: {list(INVENTORY)}"}],
            "is_error": True,
        }
    return {"content": [{"type": "text", "text": f"{sku}: {INVENTORY[sku]} units"}]}


@tool("reorder", "Place a restock order for a SKU.", {"sku": str, "quantity": int})
async def reorder(args: dict[str, Any]) -> dict[str, Any]:
    INVENTORY[args["sku"].lower()] = INVENTORY.get(args["sku"].lower(), 0) + args["quantity"]
    return {"content": [{"type": "text", "text": f"Ordered {args['quantity']} x {args['sku']}"}]}


async def main() -> None:
    server = create_sdk_mcp_server(name="shop", version="1.0.0", tools=[check_stock, reorder])
    options = ClaudeAgentOptions(
        model=MODEL,
        max_budget_usd=BUDGET_USD,
        mcp_servers={"shop": server},
        allowed_tools=["mcp__shop__check_stock", "mcp__shop__reorder"],
        system_prompt="You are an inventory assistant. Reorder 20 units of anything out of stock.",
        max_turns=8,
    )
    async for message in query(prompt="Check widget, gadget and sprocket.", options=options):
        show(message)
    print("Final inventory:", INVENTORY)


if __name__ == "__main__":
    anyio.run(main)
