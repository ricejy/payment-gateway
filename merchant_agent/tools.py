"""Merchant-side tools: product catalog, payment gating, verification, delivery."""

from __future__ import annotations

import json
import uuid

from protocol.ap2_models import (
    CartMandate,
    PaymentMandate,
    PaymentReceipt,
    PaymentRequiredMessage,
    PaymentScheme,
    PaymentNetwork,
    Product,
)
from protocol.x402_models import PaymentPayload, PaymentRequirements, PaymentResponse
from protocol.ledger import ledger

PRODUCT_CATALOG: list[Product] = [
    Product(
        product_id="prod_001",
        name="Market Analysis Report",
        description="AI-generated analysis of current market trends with actionable insights.",
        price=5.0,
    ),
    Product(
        product_id="prod_002",
        name="Code Review",
        description="Automated code quality review with security vulnerability scanning.",
        price=10.0,
    ),
    Product(
        product_id="prod_003",
        name="Data Processing Pipeline",
        description="Process and transform your dataset with advanced ETL pipeline.",
        price=20.0,
    ),
]

# Track verified payments for this session
_verified_payments: dict[str, PaymentReceipt] = {}


def get_product_catalog() -> str:
    """Returns the full catalog of available products with names, descriptions, and prices."""
    items = []
    for p in PRODUCT_CATALOG:
        items.append(
            f"- **{p.name}** (ID: {p.product_id}): {p.description} | Price: {p.price} {p.currency}"
        )
    return "Available Products:\n" + "\n".join(items)


def request_payment(product_name: str) -> str:
    """Generate AP2 PaymentRequired message for a requested product. Returns payment requirements the client must fulfill.

    Args:
        product_name: Name or ID of the product the client wants to purchase.
    """
    product = None
    for p in PRODUCT_CATALOG:
        if p.product_id == product_name or p.name.lower() == product_name.lower():
            product = p
            break

    if product is None:
        return json.dumps({"error": f"Product '{product_name}' not found. Use get_product_catalog to see available products."})

    cart = CartMandate(
        products=[product],
        total_amount=product.price,
        currency=product.currency,
        merchant_id="merchant_wallet",
    )

    requirements = PaymentRequirements(
        amount=product.price,
        currency=product.currency,
        description=f"Payment for: {product.name}",
        merchant_id="merchant_wallet",
        resource=product.product_id,
    )

    msg = PaymentRequiredMessage(
        cart_mandate=cart,
        message=f"Payment of {product.price} {product.currency} required for '{product.name}'. "
                f"Please submit an x402 payment with scheme='{requirements.scheme.value}' "
                f"and network='{requirements.network.value}'.",
    )

    return json.dumps({
        "payment_required": msg.model_dump(),
        "x402_requirements": requirements.model_dump(),
    }, default=str)


def verify_and_settle(payment_payload_json: str) -> str:
    """Verify an x402 payment payload and settle the transaction via the ledger.

    Args:
        payment_payload_json: JSON string of the x402 PaymentPayload with payer_id, amount, and token.
    """
    try:
        data = json.loads(payment_payload_json)
        payload = PaymentPayload(**data)
    except Exception as e:
        return json.dumps({"error": f"Invalid payment payload: {e}"})

    if payload.amount <= 0:
        return json.dumps({"error": "Payment amount must be positive."})

    payer_balance = ledger.get_balance(payload.payer_id)
    if payer_balance < payload.amount:
        return json.dumps({
            "error": f"Insufficient balance. Required: {payload.amount}, Available: {payer_balance}"
        })

    tx = ledger.transfer(payload.payer_id, "merchant_wallet", payload.amount)
    if tx is None:
        return json.dumps({"error": "Transfer failed."})

    receipt = PaymentReceipt(
        payment_mandate_id=payload.token,
        amount=payload.amount,
        currency="credits",
        tx_hash=tx.tx_hash,
    )
    _verified_payments[receipt.receipt_id] = receipt

    return json.dumps({
        "status": "settled",
        "receipt": receipt.model_dump(),
        "payer_new_balance": ledger.get_balance(payload.payer_id),
        "message": f"Payment of {payload.amount} credits verified and settled. TX: {tx.tx_hash}",
    }, default=str)


def deliver_service(product_name: str, receipt_id: str) -> str:
    """Deliver the purchased service/content after payment verification.

    Args:
        product_name: Name or ID of the product to deliver.
        receipt_id: Receipt ID from the payment settlement.
    """
    if receipt_id not in _verified_payments:
        return json.dumps({"error": f"No verified payment found for receipt '{receipt_id}'. Payment must be verified first."})

    _verified_payments.pop(receipt_id)

    product = None
    for p in PRODUCT_CATALOG:
        if p.product_id == product_name or p.name.lower() == product_name.lower():
            product = p
            break

    if product is None:
        return json.dumps({"error": f"Product '{product_name}' not found."})

    deliverables = {
        "prod_001": {
            "title": "Market Analysis Report — May 2026",
            "content": (
                "## Key Findings\n"
                "1. **AI Agent Economy** is growing at 35,000% YoY with 1.38M+ transactions recorded.\n"
                "2. **Agentic Commerce Protocols** (AP2, x402, A2A) are becoming the standard stack.\n"
                "3. **Stablecoin Settlement** on L2s (Base, Arbitrum) is the preferred payment rail.\n"
                "4. **Recommendation**: Invest in agent-native payment infrastructure."
            ),
        },
        "prod_002": {
            "title": "Code Review — Automated Analysis",
            "content": (
                "## Code Review Results\n"
                "- **Security**: No critical vulnerabilities detected. 2 minor issues flagged.\n"
                "- **Quality**: Code coverage at 87%. Cyclomatic complexity within bounds.\n"
                "- **Performance**: 3 optimization opportunities identified in hot paths.\n"
                "- **Rating**: 8.5/10 — Production ready with minor improvements."
            ),
        },
        "prod_003": {
            "title": "Data Processing Pipeline — Results",
            "content": (
                "## Pipeline Execution Summary\n"
                "- **Records Processed**: 150,000 rows\n"
                "- **Transformations Applied**: Dedup, normalization, enrichment\n"
                "- **Duration**: 4.2 seconds\n"
                "- **Output**: Clean dataset with 142,300 valid records (5.1% filtered)."
            ),
        },
    }

    delivery = deliverables.get(product.product_id, {
        "title": product.name,
        "content": f"Service '{product.name}' delivered successfully.",
    })

    return json.dumps({
        "status": "delivered",
        "product": product.name,
        "receipt_id": receipt_id,
        "delivery": delivery,
    })
