"""Merchant Agent — sells AI services, gates access behind AP2/x402 payment."""

from google.adk.agents import Agent

from .tools import get_product_catalog, request_payment, verify_and_settle, deliver_service

merchant_agent = Agent(
    model="gemini-2.5-flash-lite",
    name="merchant_agent",
    description="A merchant agent that sells AI analysis services. Requires x402 payment before delivering results.",
    instruction=(
        "You are a merchant agent offering AI-powered services. Follow this protocol:\n\n"
        "1. When a client asks what's available, use `get_product_catalog` to show products.\n"
        "2. When a client wants to buy something, use `request_payment` to generate an AP2 "
        "PaymentRequired message with x402 payment requirements.\n"
        "3. When a client submits payment (a JSON payload with payer_id, amount, token), "
        "use `verify_and_settle` to verify and settle the payment via the ledger.\n"
        "4. After successful payment, use `deliver_service` with the product name and receipt_id "
        "to provide the purchased content.\n\n"
        "Always be professional. Clearly communicate payment requirements and confirm settlement "
        "before delivering any service."
    ),
    tools=[get_product_catalog, request_payment, verify_and_settle, deliver_service],
)
