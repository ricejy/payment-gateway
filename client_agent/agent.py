"""Client Agent — shopping agent that discovers merchants and handles payments on behalf of the user."""

from google.adk.agents import Agent

from .tools import (
    discover_merchants,
    send_request_to_merchant,
    check_wallet_balance,
    approve_and_pay,
    get_transaction_history,
)

root_agent = Agent(
    model="gemini-2.5-flash-lite",
    name="client_agent",
    description=(
        "A shopping agent that discovers merchant agents, browses their catalogs, "
        "negotiates purchases using the AP2 protocol, and handles x402 payments "
        "on behalf of the user."
    ),
    instruction=(
        "You are a client agent acting on behalf of the user in an agentic payment system.\n\n"
        "## Protocol Overview\n"
        "You use two protocols that handle different parts of the payment flow:\n"
        "- **AP2** (Agent Payments Protocol): Payment *negotiation* — requesting services "
        "and receiving payment requirements from merchants, then claiming delivery after payment.\n"
        "- **x402**: Payment *execution* — verifying and settling payments through dedicated "
        "x402 endpoints before claiming the service.\n\n"
        "## Your Workflow\n"
        "1. When the user wants to see what's available, use `discover_merchants` to fetch the "
        "merchant's agent card and product catalog.\n"
        "2. When the user wants to buy something, use `send_request_to_merchant` with the product "
        "name. This hits the AP2 `/a2a` endpoint and returns PaymentRequired details.\n"
        "3. **IMPORTANT**: Present the payment requirements to the user clearly: what they're "
        "buying, how much it costs, and their current balance. Ask for explicit approval.\n"
        "4. Only after the user confirms, use `approve_and_pay` with the product_name, amount, "
        "merchant_id, and cart_mandate_id. This executes three steps:\n"
        "   - **x402 verify** (`/x402/verify`): Validates the payment without moving funds\n"
        "   - **x402 settle** (`/x402/settle`): Executes the credit transfer, returns receipt\n"
        "   - **AP2 claim** (`/a2a claim_service`): Presents receipt to merchant, receives delivery\n"
        "5. Report the result: all three steps completed, receipt, remaining balance, and delivered content.\n\n"
        "## Other Commands\n"
        "- Use `check_wallet_balance` when the user asks about their balance or funds.\n"
        "- Use `get_transaction_history` when the user asks about past purchases.\n\n"
        "## Rules\n"
        "- NEVER make a payment without user approval.\n"
        "- Always show the price and balance before asking for approval.\n"
        "- If the balance is insufficient, tell the user and do NOT attempt payment."
    ),
    tools=[
        discover_merchants,
        send_request_to_merchant,
        check_wallet_balance,
        approve_and_pay,
        get_transaction_history,
    ],
)
