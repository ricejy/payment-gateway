"""Client-side tools: discover merchants, send requests, handle x402 payments.

Payment flow uses three separate HTTP steps matching the real x402 spec:
  1. POST /x402/verify  — check if payment is valid (no funds moved)
  2. POST /x402/settle  — execute the transfer, get receipt
  3. POST /a2a claim_service — present receipt, receive delivery
"""

from __future__ import annotations

import json

import httpx

from protocol.x402_models import PaymentPayload

MERCHANT_URL = "http://localhost:10000"


def discover_merchants() -> str:
    """Discover available merchant agents and their services by fetching the agent card."""
    try:
        resp = httpx.get(f"{MERCHANT_URL}/agent-card", timeout=10)
        resp.raise_for_status()
        card = resp.json()
        products = card.get("products", [])
        lines = [
            f"## Merchant: {card['name']}",
            f"**Description**: {card['description']}",
            f"**Protocol**: {card['protocol']}",
            f"**Accepted payments**: {card['accepted_payments']}",
            "",
            "### Available Products:",
        ]
        for p in products:
            lines.append(f"- **{p['name']}** (ID: {p['product_id']}): {p['description']} — {p['price']} {p['currency']}")
        return "\n".join(lines)
    except httpx.ConnectError:
        return "ERROR: Cannot reach merchant server. Make sure it's running on http://localhost:10000"
    except Exception as e:
        return f"ERROR: {e}"


def send_request_to_merchant(product_name: str) -> str:
    """Send a purchase request to the merchant agent for a specific product. Returns AP2 payment requirements if payment is needed.

    Args:
        product_name: The name or product_id of the item to purchase.
    """
    try:
        resp = httpx.post(
            f"{MERCHANT_URL}/a2a",
            json={
                "jsonrpc": "2.0",
                "method": "request_service",
                "params": {"product_name": product_name},
                "id": 1,
            },
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json().get("result", {})

        if "payment_required" in result:
            pr = result["payment_required"]
            reqs = result["x402_requirements"]
            return json.dumps({
                "status": "payment_required",
                "message": pr["message"],
                "product": pr["cart_mandate"]["products"][0]["name"],
                "amount": reqs["amount"],
                "currency": reqs["currency"],
                "scheme": reqs["scheme"],
                "network": reqs["network"],
                "merchant_id": reqs["merchant_id"],
                "cart_mandate_id": pr["cart_mandate"]["mandate_id"],
            }, indent=2)

        return json.dumps(result, indent=2)
    except httpx.ConnectError:
        return "ERROR: Cannot reach merchant server. Make sure it's running on http://localhost:10000"
    except Exception as e:
        return f"ERROR: {e}"


def check_wallet_balance() -> str:
    """Check the user's current wallet balance by querying the merchant server."""
    try:
        resp = httpx.get(f"{MERCHANT_URL}/wallet/balance", params={"account_id": "user_wallet"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        balance = data["balance"]

        tx_resp = httpx.get(f"{MERCHANT_URL}/wallet/transactions", params={"account_id": "user_wallet"}, timeout=10)
        tx_resp.raise_for_status()
        txs = tx_resp.json().get("transactions", [])
        recent = txs[-5:] if txs else []

        lines = [f"**Wallet Balance**: {balance} {data['currency']}"]
        if recent:
            lines.append("\n**Recent Transactions**:")
            for tx in recent:
                direction = "SENT" if tx["from"] == "user_wallet" else "RECEIVED"
                other = tx["to"] if direction == "SENT" else tx["from"]
                lines.append(f"- {direction} {tx['amount']} credits {'to' if direction == 'SENT' else 'from'} {other} | TX: {tx['tx_hash'][:16]}...")
        return "\n".join(lines)
    except httpx.ConnectError:
        return "ERROR: Cannot reach merchant server."
    except Exception as e:
        return f"ERROR: {e}"


def approve_and_pay(product_name: str, amount: float, merchant_id: str, cart_mandate_id: str) -> str:
    """Execute the full x402 payment flow: verify -> settle -> claim delivery.

    This calls three separate endpoints matching the real x402 protocol:
      1. POST /x402/verify  — checks the payment is valid (sufficient balance)
      2. POST /x402/settle  — executes the on-chain transfer, returns receipt
      3. POST /a2a claim_service — presents receipt to merchant, receives delivery

    Only call this AFTER the user has explicitly approved the payment.

    Args:
        product_name: Name of the product being purchased.
        amount: Payment amount in credits.
        merchant_id: The merchant's wallet ID.
        cart_mandate_id: The cart mandate ID from the payment requirements.
    """
    payment_payload = PaymentPayload(
        payer_id="user_wallet",
        amount=amount,
        scheme="simulated:credits",
        network="simulated",
    )
    payload_dict = payment_payload.model_dump()

    try:
        # Step 1: x402 VERIFY — check payment validity without moving funds
        verify_resp = httpx.post(
            f"{MERCHANT_URL}/x402/verify",
            json={"payload": payload_dict},
            timeout=10,
        )
        verify_resp.raise_for_status()
        verify_result = verify_resp.json()

        if not verify_result.get("valid"):
            return json.dumps({
                "status": "failed",
                "step": "x402/verify",
                "message": verify_result.get("message", "Payment verification failed."),
            }, indent=2)

        # Step 2: x402 SETTLE — execute the transfer, debit payer, credit merchant
        settle_resp = httpx.post(
            f"{MERCHANT_URL}/x402/settle",
            json={"payload": payload_dict},
            timeout=10,
        )
        settle_result = settle_resp.json()

        if "error" in settle_result:
            return json.dumps({
                "status": "failed",
                "step": "x402/settle",
                "message": settle_result["error"],
            }, indent=2)

        receipt = settle_result.get("receipt", {})
        receipt_id = receipt.get("receipt_id", "")

        # Step 3: AP2 CLAIM — present receipt to merchant, receive delivery
        claim_resp = httpx.post(
            f"{MERCHANT_URL}/a2a",
            json={
                "jsonrpc": "2.0",
                "method": "claim_service",
                "params": {
                    "product_name": product_name,
                    "receipt_id": receipt_id,
                },
                "id": 3,
            },
            timeout=10,
        )
        claim_result = claim_resp.json()

        if "error" in claim_result:
            return json.dumps({
                "status": "failed",
                "step": "a2a/claim_service",
                "message": claim_result["error"],
                "receipt": receipt,
            }, indent=2)

        delivery = claim_result.get("result", {})

        return json.dumps({
            "status": "success",
            "message": "Payment settled and service delivered!",
            "steps_completed": [
                "x402/verify — payment validated",
                f"x402/settle — {settle_result.get('message', 'transfer complete')}",
                "a2a/claim_service — delivery received",
            ],
            "receipt": receipt,
            "new_balance": settle_result.get("payer_new_balance"),
            "delivery": delivery.get("delivery", {}),
        }, indent=2)

    except httpx.ConnectError:
        return "ERROR: Cannot reach merchant server."
    except Exception as e:
        return f"ERROR: {e}"


def get_transaction_history() -> str:
    """Get the full transaction history for the user's wallet from the merchant server."""
    try:
        resp = httpx.get(f"{MERCHANT_URL}/wallet/transactions", params={"account_id": "user_wallet"}, timeout=10)
        resp.raise_for_status()
        txs = resp.json().get("transactions", [])

        if not txs:
            return "No transactions yet."

        lines = ["## Transaction History\n"]
        for tx in txs:
            direction = "SENT" if tx["from"] == "user_wallet" else "RECEIVED"
            other = tx["to"] if direction == "SENT" else tx["from"]
            lines.append(
                f"| {direction} | {tx['amount']} credits | {'to' if direction == 'SENT' else 'from'} {other} | {tx['tx_hash'][:20]}... | {tx['timestamp']} |"
            )
        return "\n".join(lines)
    except httpx.ConnectError:
        return "ERROR: Cannot reach merchant server."
    except Exception as e:
        return f"ERROR: {e}"
