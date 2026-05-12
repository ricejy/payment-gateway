"""Merchant HTTP server — exposes the merchant agent via A2A-style endpoints.

Runs on localhost:10000. The client agent communicates with this server
to discover services, negotiate payment (AP2), and settle (x402).

Protocol separation:
  - /a2a endpoints handle AP2 negotiation (request_service, claim_service)
  - /x402 endpoints handle payment execution (verify, settle)
  - /wallet endpoints expose ledger state (balance, transactions)
  - /dashboard serves a live visualization of protocol events
  - /events streams protocol events via SSE
"""

from __future__ import annotations

import asyncio
import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.routing import Route

from protocol.ap2_models import PaymentScheme, PaymentNetwork
from protocol.x402_models import PaymentPayload, PaymentResponse
from protocol.ledger import ledger
from merchant_agent.tools import (
    PRODUCT_CATALOG,
    get_product_catalog,
    request_payment,
    verify_and_settle,
    deliver_service,
)


# ── Event Bus (SSE) ──────────────────────────────────────────────────────────

_event_id = 0
_subscribers: set[asyncio.Queue] = set()


def _classify_endpoint(endpoint: str, method: str = "") -> str:
    if endpoint.startswith("/x402"):
        return "x402"
    if endpoint == "/a2a":
        return "ap2"
    if endpoint.startswith("/wallet"):
        return "wallet"
    return "discovery"


def emit_event(
    *,
    protocol: str,
    endpoint: str,
    method: str,
    direction: str,
    summary: str,
    detail: dict | None = None,
    status: int | None = None,
    from_: str = "client_agent",
    to: str = "merchant_server",
):
    global _event_id
    _event_id += 1
    event = {
        "id": _event_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "protocol": protocol,
        "endpoint": endpoint,
        "method": method,
        "direction": direction,
        "summary": summary,
        "detail": detail or {},
        "status": status,
        "from": from_,
        "to": to,
    }
    for q in _subscribers:
        q.put_nowait(event)


def emit_balance_update():
    event = {
        "type": "balance_update",
        "user_balance": ledger.get_balance("user_wallet"),
        "merchant_balance": ledger.get_balance("merchant_wallet"),
    }
    for q in _subscribers:
        q.put_nowait(event)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def agent_card(request: Request) -> JSONResponse:
    """GET /agent-card — describes this merchant agent's capabilities."""
    emit_event(
        protocol="discovery",
        endpoint="/agent-card",
        method="GET",
        direction="request",
        summary="Discover merchant capabilities",
    )

    card = {
        "name": "merchant_agent",
        "description": "AI-powered analysis services merchant. Accepts x402 payments.",
        "version": "0.1.0",
        "protocol": "AP2/v0.2",
        "endpoints": {
            "catalog": "/catalog",
            "negotiate": "/a2a",
            "verify": "/x402/verify",
            "settle": "/x402/settle",
            "balance": "/wallet/balance",
            "transactions": "/wallet/transactions",
        },
        "accepted_payments": {
            "schemes": [s.value for s in [PaymentScheme.SIMULATED]],
            "networks": [n.value for n in [PaymentNetwork.SIMULATED]],
            "currency": "credits",
        },
        "products": [p.model_dump() for p in PRODUCT_CATALOG],
    }

    emit_event(
        protocol="discovery",
        endpoint="/agent-card",
        method="GET",
        direction="response",
        summary=f"Agent card: {len(PRODUCT_CATALOG)} products",
        detail={"products": [p.name for p in PRODUCT_CATALOG]},
        status=200,
        from_="merchant_server",
        to="client_agent",
    )

    return JSONResponse(card)


async def catalog(request: Request) -> JSONResponse:
    """GET /catalog — returns product catalog."""
    return JSONResponse({
        "products": [p.model_dump() for p in PRODUCT_CATALOG],
    })


async def a2a_handler(request: Request) -> JSONResponse:
    """POST /a2a — AP2 negotiation endpoint."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Invalid JSON"}, "id": None},
            status_code=400,
        )
    method = body.get("method", "")
    params = body.get("params", {})

    if method == "request_service":
        product_name = params.get("product_name", "")
        emit_event(
            protocol="ap2",
            endpoint="/a2a",
            method="POST",
            direction="request",
            summary=f"request_service: {product_name}",
            detail={"product_name": product_name},
        )

        result = json.loads(request_payment(product_name))

        if "error" in result:
            emit_event(
                protocol="ap2",
                endpoint="/a2a",
                method="POST",
                direction="response",
                summary=f"Error: {result['error']}",
                detail=result,
                status=404,
                from_="merchant_server",
                to="client_agent",
            )
        else:
            amount = result["x402_requirements"]["amount"]
            emit_event(
                protocol="ap2",
                endpoint="/a2a",
                method="POST",
                direction="response",
                summary=f"PaymentRequired: {amount} credits",
                detail={
                    "product": product_name,
                    "amount": amount,
                    "scheme": result["x402_requirements"]["scheme"],
                },
                status=200,
                from_="merchant_server",
                to="client_agent",
            )

        return JSONResponse({"jsonrpc": "2.0", "result": result, "id": body.get("id")})

    elif method == "claim_service":
        product_name = params.get("product_name", "")
        receipt_id = params.get("receipt_id", "")

        if not receipt_id:
            emit_event(
                protocol="ap2",
                endpoint="/a2a",
                method="POST",
                direction="response",
                summary="Error: receipt_id required",
                status=400,
                from_="merchant_server",
                to="client_agent",
            )
            return JSONResponse(
                {"jsonrpc": "2.0", "error": {"code": -32602, "message": "receipt_id is required"}, "id": body.get("id")},
                status_code=400,
            )

        emit_event(
            protocol="ap2",
            endpoint="/a2a",
            method="POST",
            direction="request",
            summary=f"claim_service: {product_name}",
            detail={"product_name": product_name, "receipt_id": receipt_id[:12] + "..."},
        )

        delivery_result = json.loads(deliver_service(product_name, receipt_id))

        if "error" in delivery_result:
            emit_event(
                protocol="ap2",
                endpoint="/a2a",
                method="POST",
                direction="response",
                summary=f"Delivery denied: {delivery_result['error']}",
                detail=delivery_result,
                status=402,
                from_="merchant_server",
                to="client_agent",
            )
            return JSONResponse(
                {"jsonrpc": "2.0", "error": delivery_result, "id": body.get("id")},
                status_code=402,
                headers={"X-PAYMENT-STATUS": "unverified"},
            )

        emit_event(
            protocol="ap2",
            endpoint="/a2a",
            method="POST",
            direction="response",
            summary=f"Delivered: {product_name}",
            detail={"product": product_name, "status": "delivered"},
            status=200,
            from_="merchant_server",
            to="client_agent",
        )

        return JSONResponse({
            "jsonrpc": "2.0",
            "result": delivery_result,
            "id": body.get("id"),
        })

    else:
        return JSONResponse(
            {"jsonrpc": "2.0", "error": {"code": -32601, "message": f"Unknown method: {method}"}, "id": body.get("id")},
            status_code=400,
        )


async def x402_verify(request: Request) -> JSONResponse:
    """POST /x402/verify — check whether a payment payload is valid (no funds moved)."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(PaymentResponse(valid=False, message="Invalid JSON").model_dump())

    try:
        payload = PaymentPayload(**body.get("payload", {}))
    except Exception as e:
        return JSONResponse(PaymentResponse(valid=False, message=str(e)).model_dump())

    emit_event(
        protocol="x402",
        endpoint="/x402/verify",
        method="POST",
        direction="request",
        summary=f"Verify: {payload.amount} credits from {payload.payer_id}",
        detail={"payer_id": payload.payer_id, "amount": payload.amount},
    )

    emit_event(
        protocol="x402",
        endpoint="/x402/verify",
        method="POST",
        direction="internal_request",
        summary=f"Check balance: {payload.payer_id}",
        detail={"payer_id": payload.payer_id, "amount": payload.amount},
        from_="merchant_server",
        to="ledger",
    )

    balance = ledger.get_balance(payload.payer_id)
    is_valid = balance >= payload.amount > 0

    emit_event(
        protocol="x402",
        endpoint="/x402/verify",
        method="POST",
        direction="internal_response",
        summary=f"Balance: {balance} credits ({'sufficient' if is_valid else 'INSUFFICIENT'})",
        detail={"balance": balance, "required": payload.amount, "sufficient": is_valid},
        from_="ledger",
        to="merchant_server",
    )

    emit_event(
        protocol="x402",
        endpoint="/x402/verify",
        method="POST",
        direction="response",
        summary=f"{'Valid' if is_valid else 'INVALID'}: balance={balance}",
        detail={"valid": is_valid, "balance": balance, "required": payload.amount},
        status=200,
        from_="merchant_server",
        to="client_agent",
    )

    return JSONResponse(PaymentResponse(
        valid=is_valid,
        message=f"Payment of {payload.amount} credits verified. Balance: {balance}"
                if is_valid
                else f"Insufficient balance. Required: {payload.amount}, Available: {balance}",
    ).model_dump())


async def x402_settle(request: Request) -> JSONResponse:
    """POST /x402/settle — execute the payment: debit payer, credit merchant, return receipt."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    payload_data = body.get("payload", {})

    emit_event(
        protocol="x402",
        endpoint="/x402/settle",
        method="POST",
        direction="request",
        summary=f"Settle: {payload_data.get('amount', '?')} credits",
        detail={"payer_id": payload_data.get("payer_id"), "amount": payload_data.get("amount")},
    )

    emit_event(
        protocol="x402",
        endpoint="/x402/settle",
        method="POST",
        direction="internal_request",
        summary=f"Transfer: {payload_data.get('amount', '?')} credits",
        detail={"payer_id": payload_data.get("payer_id"), "amount": payload_data.get("amount")},
        from_="merchant_server",
        to="ledger",
    )

    result = json.loads(verify_and_settle(json.dumps(payload_data)))

    if "error" in result:
        emit_event(
            protocol="x402",
            endpoint="/x402/settle",
            method="POST",
            direction="internal_response",
            summary=f"Transfer FAILED: {result['error']}",
            detail=result,
            from_="ledger",
            to="merchant_server",
        )
        emit_event(
            protocol="x402",
            endpoint="/x402/settle",
            method="POST",
            direction="response",
            summary=f"Settlement FAILED: {result['error']}",
            detail=result,
            status=402,
            from_="merchant_server",
            to="client_agent",
        )
        return JSONResponse(result, status_code=402, headers={"X-PAYMENT-STATUS": "failed"})

    tx_hash = result.get("receipt", {}).get("tx_hash", "")
    emit_event(
        protocol="x402",
        endpoint="/x402/settle",
        method="POST",
        direction="internal_response",
        summary=f"TX confirmed: {tx_hash[:16]}...",
        detail={
            "tx_hash": tx_hash,
            "amount": result.get("receipt", {}).get("amount"),
        },
        from_="ledger",
        to="merchant_server",
    )

    emit_event(
        protocol="x402",
        endpoint="/x402/settle",
        method="POST",
        direction="response",
        summary=f"Settled! TX: {tx_hash[:16]}...",
        detail={
            "tx_hash": tx_hash,
            "amount": result.get("receipt", {}).get("amount"),
            "new_balance": result.get("payer_new_balance"),
        },
        status=200,
        from_="merchant_server",
        to="client_agent",
    )

    emit_balance_update()

    return JSONResponse(result, headers={"X-PAYMENT-STATUS": "settled"})


async def wallet_balance(request: Request) -> JSONResponse:
    """GET /wallet/balance?account_id=... — returns current balance for an account."""
    account_id = request.query_params.get("account_id", "user_wallet")
    balance = ledger.get_balance(account_id)
    return JSONResponse({"account_id": account_id, "balance": balance, "currency": "credits"})


async def wallet_transactions(request: Request) -> JSONResponse:
    """GET /wallet/transactions?account_id=... — returns transaction history."""
    account_id = request.query_params.get("account_id", "user_wallet")
    txs = ledger.get_transactions(account_id)
    return JSONResponse({
        "account_id": account_id,
        "transactions": [
            {
                "tx_hash": tx.tx_hash,
                "from": tx.from_id,
                "to": tx.to_id,
                "amount": tx.amount,
                "currency": tx.currency,
                "timestamp": tx.timestamp,
            }
            for tx in txs
        ],
    })


# ── Dashboard & SSE ──────────────────────────────────────────────────────────

async def dashboard(request: Request) -> HTMLResponse:
    """GET /dashboard — serves the live protocol visualization."""
    html_path = Path(__file__).parent / "dashboard.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


async def events_sse(request: Request) -> StreamingResponse:
    """GET /events — SSE stream of protocol events."""
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers.add(queue)

    async def event_generator():
        try:
            init = {
                "type": "balance_update",
                "user_balance": ledger.get_balance("user_wallet"),
                "merchant_balance": ledger.get_balance("merchant_wallet"),
            }
            yield f"data: {json.dumps(init)}\n\n"

            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _subscribers.discard(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Routes & App ──────────────────────────────────────────────────────────────

routes = [
    Route("/dashboard", dashboard, methods=["GET"]),
    Route("/events", events_sse, methods=["GET"]),
    Route("/agent-card", agent_card, methods=["GET"]),
    Route("/catalog", catalog, methods=["GET"]),
    Route("/a2a", a2a_handler, methods=["POST"]),
    Route("/x402/verify", x402_verify, methods=["POST"]),
    Route("/x402/settle", x402_settle, methods=["POST"]),
    Route("/wallet/balance", wallet_balance, methods=["GET"]),
    Route("/wallet/transactions", wallet_transactions, methods=["GET"]),
]

app = Starlette(routes=routes)


def main():
    import uvicorn
    print("Starting Merchant Agent Server on http://localhost:10000")
    print("Endpoints:")
    print("  Dashboard:        http://localhost:10000/dashboard")
    print("  AP2 negotiation:  /agent-card, /catalog, /a2a (request_service, claim_service)")
    print("  x402 payment:     /x402/verify, /x402/settle")
    print("  Wallet:           /wallet/balance, /wallet/transactions")
    print("  SSE events:       /events")
    uvicorn.run(app, host="0.0.0.0", port=10000)


if __name__ == "__main__":
    main()
