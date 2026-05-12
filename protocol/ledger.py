"""Simulated credit ledger for the payment gateway demo.

In-memory ledger that tracks balances and transactions. Stands in for
real blockchain settlement — swap with NeverminedFacilitator for production.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field


@dataclass
class Transaction:
    tx_hash: str
    from_id: str
    to_id: str
    amount: float
    currency: str = "credits"
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class Ledger:
    def __init__(self):
        self._balances: dict[str, float] = {}
        self._transactions: list[Transaction] = []

    def create_account(self, account_id: str, initial_balance: float = 100.0) -> float:
        if account_id not in self._balances:
            self._balances[account_id] = initial_balance
        return self._balances[account_id]

    def get_balance(self, account_id: str) -> float:
        return self._balances.get(account_id, 0.0)

    def debit(self, account_id: str, amount: float) -> bool:
        balance = self._balances.get(account_id, 0.0)
        if balance < amount:
            return False
        self._balances[account_id] = balance - amount
        return True

    def credit(self, account_id: str, amount: float) -> None:
        self._balances.setdefault(account_id, 0.0)
        self._balances[account_id] += amount

    def transfer(self, from_id: str, to_id: str, amount: float) -> Transaction | None:
        if not self.debit(from_id, amount):
            return None
        self.credit(to_id, amount)
        tx = Transaction(
            tx_hash=f"0x{uuid.uuid4().hex}",
            from_id=from_id,
            to_id=to_id,
            amount=amount,
        )
        self._transactions.append(tx)
        return tx

    def get_transactions(self, account_id: str | None = None) -> list[Transaction]:
        if account_id is None:
            return list(self._transactions)
        return [
            tx for tx in self._transactions
            if tx.from_id == account_id or tx.to_id == account_id
        ]


# Singleton ledger shared across the demo
ledger = Ledger()
ledger.create_account("user_wallet", initial_balance=100.0)
ledger.create_account("merchant_wallet", initial_balance=0.0)
