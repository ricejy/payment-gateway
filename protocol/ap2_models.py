"""AP2 (Agent Payments Protocol) message types and mandate schemas.

Implements the payment negotiation layer: how agents express
"payment required" and "payment submitted" using structured mandates.
Reference: https://ap2-protocol.org/
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class PaymentScheme(str, Enum):
    # we are only using simulated credits for this demo
    SIMULATED = "simulated:credits"
    # blockchain scheme for x402
    X402_EXACT = "exact"
    # for nervermined whose demo this is inspired by
    NVM_ERC4337 = "nvm:erc4337"


class PaymentNetwork(str, Enum):
    SIMULATED = "simulated"
    # real networks like base sepolia for x402
    BASE_SEPOLIA = "eip155:84532"
    BASE = "eip155:8453"

# purchasable items in the catalog
class Product(BaseModel):
    product_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    description: str
    price: float
    currency: str = "credits"

# cart mandate is a finalized, signed record of what the user wants to buy, a signed record of intent.
class CartMandate(BaseModel):
    """Finalized cart — a cryptographically-signable record of what the user wants to buy."""
    mandate_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    products: list[Product]
    total_amount: float
    currency: str = "credits"
    merchant_id: str
    accepted_schemes: list[PaymentScheme] = [PaymentScheme.SIMULATED]
    accepted_networks: list[PaymentNetwork] = [PaymentNetwork.SIMULATED]
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str | None = None

# payment mandate is a signed record of approval to spend, a signed record of approval to spend.
class PaymentMandate(BaseModel):
    """Authorized payment — the user's signed approval to spend."""
    mandate_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    cart_mandate_id: str
    amount: float
    currency: str = "credits"
    scheme: PaymentScheme = PaymentScheme.SIMULATED
    network: PaymentNetwork = PaymentNetwork.SIMULATED
    payer_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

# what the merchant sends back when you ask for a service.
class PaymentRequiredMessage(BaseModel):
    """AP2 'payment-required' response from merchant to client."""
    type: str = "payment-required"
    cart_mandate: CartMandate
    message: str = "Payment is required to access this service."

# what the client sends back when you pay for a service.
class PaymentSubmittedMessage(BaseModel):
    """AP2 'payment-submitted' from client to merchant, carrying x402 payment proof."""
    type: str = "payment-submitted"
    payment_mandate: PaymentMandate
    x402_token: str

# what the merchant sends back when you pay for a service.
class PaymentReceipt(BaseModel):
    """Settlement confirmation returned after successful payment."""
    receipt_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    payment_mandate_id: str
    amount: float
    currency: str = "credits"
    tx_hash: str
    status: str = "settled"
    settled_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
