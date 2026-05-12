"""x402 payment execution layer models.

Implements the HTTP 402-based payment flow: merchant returns payment
requirements, client submits payment proof, facilitator verifies and settles.
Reference: https://www.x402.org/
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from .ap2_models import PaymentNetwork, PaymentScheme

# What the merchant demands: scheme, network, amount, currency, facilitator URL, merchant ID, resource ID.
class PaymentRequirements(BaseModel):
    """What the merchant requires for payment (returned in 402 response)."""
    scheme: PaymentScheme = PaymentScheme.SIMULATED
    network: PaymentNetwork = PaymentNetwork.SIMULATED
    amount: float
    currency: str = "credits"
    description: str = ""
    facilitator_url: str = "http://localhost:10000/x402"
    merchant_id: str = ""
    resource: str = ""

# What the client sends as payment proof: a version, scheme, network, token, payer ID, and amount.
class PaymentPayload(BaseModel):
    """Client's payment proof (sent in X-PAYMENT header)."""
    x402_version: int = 2
    scheme: PaymentScheme = PaymentScheme.SIMULATED
    network: PaymentNetwork = PaymentNetwork.SIMULATED
    token: str = Field(default_factory=lambda: str(uuid.uuid4()))
    payer_id: str = ""
    amount: float = 0.0

# The payment facilitator's response: a boolean indicating whether the payment is valid, a transaction hash, a message, and a receipt ID.
class PaymentResponse(BaseModel):
    """Facilitator's verification/settlement result."""
    valid: bool
    tx_hash: str = ""
    message: str = ""
    receipt_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
