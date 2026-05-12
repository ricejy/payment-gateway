# Agentic Payment Gateway Demo

A hands-on demo of **Google's AP2** (Agent Payments Protocol) and **Coinbase's x402** protocol, built with **Google ADK** (Agent Development Kit). A Client Agent discovers a Merchant Agent, negotiates a purchase via AP2 mandates, and settles payment via the x402 flow — all through a conversational UI.

> **Note:** This is an educational demo that illustrates the flow and concepts of AP2/x402/A2A using simulated infrastructure. The "settlement" is an in-memory ledger operation, not an on-chain transaction. Payment tokens are random UUIDs, not cryptographic proofs. This cannot interoperate with other AP2/x402-compliant agents. See [Future: Real x402 Integration](#future-real-x402-integration) for how to wire in real settlement.

## Protocol Overview

This project implements two complementary agentic payment protocols:

### AP2 — Agent Payments Protocol

[AP2](https://ap2-protocol.org/) defines the **payment negotiation layer** — how agents express "payment required" and "payment submitted" using structured mandates. It is an extension of Google's A2A (Agent-to-Agent) protocol and the Universal Commerce Protocol (UCP).

Key concepts in this demo:
- **CartMandate** — a finalized, signed record of what the user wants to buy (products, total, accepted payment schemes)
- **PaymentMandate** — the user's signed authorization to spend (amount, scheme, network, payer reference)
- **PaymentRequired** — merchant's response telling the client that payment is needed before service delivery
- **PaymentSubmitted** — client's response carrying the x402 payment token back to the merchant

### x402 — HTTP-Native Payments

[x402](https://www.x402.org/) defines the **payment execution layer** — leveraging the long-dormant HTTP 402 ("Payment Required") status code. A server responds with 402 and structured payment requirements; the client pays and resubmits.

Key concepts in this demo:
- **PaymentRequirements** — what the merchant accepts (scheme, network, amount, facilitator URL)
- **PaymentPayload** — client's payment proof (version, scheme, token, payer ID, amount)
- **PaymentResponse** — facilitator's verification result (valid/invalid, tx hash)

### How They Work Together

```
A2A transports messages  →  AP2 structures payment negotiation  →  x402 executes payment
```

The protocols are cleanly separated in the codebase: AP2 handles negotiation through the `/a2a` endpoint, while x402 handles payment execution through dedicated `/x402/verify` and `/x402/settle` endpoints.

## Architecture

- **Client Agent** runs in Google ADK's Web UI (port 8000). You chat with it to browse, buy, and check balances.
- **Merchant Server** runs as an HTTP server (port 10000) exposing three groups of endpoints: AP2 negotiation, x402 payment, and wallet state.
- **Payment Layer** is a simulated in-memory credit ledger (user starts with 100 credits). Can be swapped with real Nevermined x402 integration for on-chain settlement.

## Project Structure

```
payment-gateway/
├── client_agent/               # ADK agent — the one you chat with
│   ├── __init__.py             # Exports root_agent for ADK web
│   ├── agent.py                # Agent definition (gemini-2.5-flash-lite) with instructions
│   ├── tools.py                # 3-step x402 flow: verify → settle → claim
│   └── .env                    # GOOGLE_API_KEY for Gemini
├── merchant_agent/             # Merchant agent — served via HTTP, not ADK web
│   ├── __init__.py
│   ├── agent.py                # Agent definition with catalog, payment, delivery tools
│   └── tools.py                # get_product_catalog, request_payment, verify_and_settle, deliver_service
├── protocol/                   # AP2 + x402 protocol models (Pydantic)
│   ├── __init__.py
│   ├── ap2_models.py           # Product, CartMandate, PaymentMandate, PaymentRequired/Submitted, Receipt
│   ├── x402_models.py          # PaymentRequirements, PaymentPayload, PaymentResponse
│   └── ledger.py               # Simulated credit ledger (in-memory balances + transactions)
├── server/                     # HTTP server exposing merchant via separated endpoints
│   ├── __init__.py
│   ├── merchant_server.py      # AP2: /a2a | x402: /x402/* | Wallet: /wallet/* | SSE: /events
│   └── dashboard.html          # Live protocol visualization (served at /dashboard)
├── pyproject.toml              # Project config + dependencies
├── .python-version             # Python 3.12
└── README.md
```

## Prerequisites

- **Python 3.12+**
- **uv** package manager ([install](https://docs.astral.sh/uv/getting-started/installation/))
- **Google API Key** for Gemini — get one free at [Google AI Studio](https://aistudio.google.com/app/apikey)

## Setup

1. **Install dependencies:**
   ```bash
   uv sync
   ```

2. **Configure your API key** — edit `client_agent/.env`:
   ```
   GOOGLE_API_KEY="your-google-api-key-here"
   ```

## Running the Demo

You need **two terminals**:

**Terminal 1 — Start the Merchant Server:**
```bash
uv run python server/merchant_server.py
```
This starts the merchant agent HTTP server on `http://localhost:10000`.

**Terminal 2 — Start the Client Agent (ADK Web UI):**
```bash
uv run adk web --port 8000 .
```
This starts the ADK web interface on `http://localhost:8000`.

Open **http://localhost:8000** in your browser, select **client_agent** from the dropdown, and start chatting.

**Live Dashboard** — open **http://localhost:10000/dashboard** to watch the protocol exchange in real-time.

## Live Protocol Dashboard

The dashboard at `http://localhost:10000/dashboard` provides a real-time visualization of every protocol call between the client agent, merchant server, and ledger:

- **Sequence diagram** with animated arrows between Client Agent, Merchant Server, and Ledger columns
- **Color-coded by protocol**: blue = AP2 (`/a2a`), green = x402 (`/x402/*`), purple = wallet, gray = discovery
- **Internal ledger calls** — x402 verify/settle show the server↔ledger interactions (balance checks, fund transfers, TX confirmations)
- **Live wallet balances** that update after each settlement
- **Event log** with expandable payload details (click any entry)
- Connects via **Server-Sent Events** (`/events`) — no polling

Arrow directions in the sequence diagram:
- **Client → Server**: AP2 requests (`request_service`, `claim_service`), x402 requests (`verify`, `settle`)
- **Server → Client**: AP2 responses (`PaymentRequired`, `Delivered`), x402 responses (`Valid`, `Settled`)
- **Server → Ledger**: Internal calls to check balances and transfer funds
- **Ledger → Server**: Balance confirmations and TX hash confirmations

Open the dashboard in one browser tab and the ADK Web UI in another, then watch the arrows appear as you chat.

## Demo Walkthrough

### 1. Discover Available Services
```
You: What services are available?
```
The client agent calls `discover_merchants()` which fetches the merchant's **agent card** from `GET /agent-card`. This returns the merchant's name, description, accepted payment schemes, and full product catalog.

### 2. Request a Purchase
```
You: I want to buy the Market Analysis Report
```
The client calls `send_request_to_merchant("Market Analysis Report")` which sends a JSON-RPC request to `POST /a2a` with method `request_service`. The merchant responds with an **AP2 PaymentRequired** message containing:
- A `CartMandate` (product details, total amount, accepted schemes)
- `PaymentRequirements` (x402 scheme, network, amount, facilitator URL)

The agent presents the cost and asks for your approval.

### 3. Approve and Pay (3-Step x402 Flow)
```
You: Yes, go ahead
```
The client calls `approve_and_pay()` which executes three separate HTTP requests matching the real x402 protocol:

| Step | Endpoint | Protocol | What happens |
|------|----------|----------|-------------|
| 1 | `POST /x402/verify` | x402 | Validates payment is possible (checks balance) — no funds moved |
| 2 | `POST /x402/settle` | x402 | Executes the credit transfer, debits payer, credits merchant, returns receipt with tx hash |
| 3 | `POST /a2a` `claim_service` | AP2 | Presents receipt to merchant, receives the purchased content |

### 4. Check Balance and History
```
You: Check my balance
You: Show my transaction history
```
Both tools query the merchant server's wallet endpoints (`/wallet/balance`, `/wallet/transactions`) to show accurate post-settlement state.

## Merchant Server API

### AP2 Negotiation Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/agent-card` | GET | Agent card — merchant capabilities, accepted payments, product catalog |
| `/catalog` | GET | Product catalog only |
| `/a2a` | POST | AP2 negotiation. Methods: `request_service`, `claim_service` |

### x402 Payment Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/x402/verify` | POST | Validate payment payload (check balance, no funds moved) |
| `/x402/settle` | POST | Execute payment (debit payer, credit merchant, return receipt) |

### Wallet Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/wallet/balance` | GET | Current balance for an account (`?account_id=user_wallet`) |
| `/wallet/transactions` | GET | Transaction history for an account |

### A2A Message Format

Requests use JSON-RPC 2.0:
```json
{
  "jsonrpc": "2.0",
  "method": "request_service",
  "params": { "product_name": "Market Analysis Report" },
  "id": 1
}
```

### Product Catalog

| Product | Price | Description |
|---------|-------|-------------|
| Market Analysis Report | 5 credits | AI-generated market trends analysis |
| Code Review | 10 credits | Automated code quality + security scan |
| Data Processing Pipeline | 20 credits | ETL pipeline for dataset transformation |

## Implementation Details

### Protocol Models (`protocol/`)

**`ap2_models.py`** — Pydantic models for AP2 message types:
- `Product` — item in the catalog with ID, name, description, price
- `CartMandate` — signed cart: products, total, merchant_id, accepted schemes/networks, expiry
- `PaymentMandate` — signed payment authorization: amount, scheme, network, payer reference
- `PaymentRequiredMessage` — wraps CartMandate with a human-readable message
- `PaymentSubmittedMessage` — wraps PaymentMandate + x402 token
- `PaymentReceipt` — settlement confirmation with receipt_id and tx_hash

**`x402_models.py`** — Pydantic models for x402 payment execution:
- `PaymentRequirements` — scheme, network, amount, facilitator_url, merchant_id, resource
- `PaymentPayload` — x402_version, scheme, network, token, payer_id, amount
- `PaymentResponse` — valid (bool), tx_hash, message, receipt_id

**`ledger.py`** — Simulated in-memory credit ledger:
- Tracks balances per account (`user_wallet` starts at 100, `merchant_wallet` at 0)
- `transfer()` atomically debits sender and credits receiver, generates a mock tx hash
- Records all transactions with timestamps for history queries

### Client Agent (`client_agent/`)

Built with Google ADK's `Agent` class using `gemini-2.5-flash-lite`. The agent has five tools:

| Tool | Purpose |
|------|---------|
| `discover_merchants()` | Fetches merchant agent card via `GET /agent-card` |
| `send_request_to_merchant(product_name)` | Sends AP2 request via `POST /a2a`, receives PaymentRequired |
| `check_wallet_balance()` | Queries `GET /wallet/balance` on the merchant server |
| `approve_and_pay(...)` | 3-step flow: `/x402/verify` → `/x402/settle` → `/a2a claim_service` |
| `get_transaction_history()` | Queries `GET /wallet/transactions` on the merchant server |

The agent is instructed to **never pay without explicit user approval** and to always show the price and balance before asking.

### Merchant Agent (`merchant_agent/`)

Defines the merchant's business logic as tool functions. Served over HTTP via `server/merchant_server.py`, not via ADK web.

| Tool | Purpose |
|------|---------|
| `get_product_catalog()` | Returns formatted product list |
| `request_payment(product_name)` | Builds AP2 PaymentRequired + x402 requirements |
| `verify_and_settle(payment_payload_json)` | Validates balance, transfers credits, returns receipt |
| `deliver_service(product_name, receipt_id)` | Returns the purchased content (only after verified payment) |

### Merchant HTTP Server (`server/merchant_server.py`)

Starlette/Uvicorn app on port 10000 with three endpoint groups:
- **AP2 endpoints** (`/a2a`) — handle payment negotiation (`request_service`) and post-payment delivery (`claim_service`)
- **x402 endpoints** (`/x402/*`) — handle payment execution (`verify` and `settle`)
- **Wallet endpoints** (`/wallet/*`) — expose ledger state (`balance` and `transactions`)

## Payment Flow Sequence

```
User                Client Agent              Merchant Server           Ledger
 │                       │                          │                     │
 │  "buy X"              │                          │                     │
 │──────────────────────►│                          │                     │
 │                       │                          │                     │
 │                       │  POST /a2a               │  [AP2 negotiation]  │
 │                       │  {request_service}       │                     │
 │                       │─────────────────────────►│                     │
 │                       │  PaymentRequired (AP2)   │                     │
 │                       │  + x402 Requirements     │                     │
 │                       │◄─────────────────────────│                     │
 │                       │                          │                     │
 │  "5 credits for X.    │                          │                     │
 │   Approve?"           │                          │                     │
 │◄──────────────────────│                          │                     │
 │  "yes"                │                          │                     │
 │──────────────────────►│                          │                     │
 │                       │                          │                     │
 │                       │  POST /x402/verify       │  [x402 execution]   │
 │                       │  {PaymentPayload}        │                     │
 │                       │─────────────────────────►│  check balance      │
 │                       │  {valid: true}           │                     │
 │                       │◄─────────────────────────│                     │
 │                       │                          │                     │
 │                       │  POST /x402/settle       │                     │
 │                       │  {PaymentPayload}        │                     │
 │                       │─────────────────────────►│  transfer(user→merch)│
 │                       │                          │────────────────────►│
 │                       │  {receipt, tx_hash}      │  tx_hash            │
 │                       │◄─────────────────────────│◄────────────────────│
 │                       │                          │                     │
 │                       │  POST /a2a               │  [AP2 delivery]     │
 │                       │  {claim_service}         │                     │
 │                       │─────────────────────────►│  verify receipt     │
 │                       │  {delivery content}      │                     │
 │                       │◄─────────────────────────│                     │
 │                       │                          │                     │
 │  "Paid! Here's your   │                          │                     │
 │   report. Balance: 95"│                          │                     │
 │◄──────────────────────│                          │                     │
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Agent Framework | [Google ADK](https://github.com/google/adk-python) (Agent Development Kit) |
| LLM | Gemini 2.5 Flash Lite |
| Protocol Models | [Pydantic](https://docs.pydantic.dev/) v2 |
| HTTP Server | [Starlette](https://www.starlette.io/) + [Uvicorn](https://www.uvicorn.org/) |
| HTTP Client | [httpx](https://www.python-httpx.org/) |
| Package Manager | [uv](https://docs.astral.sh/uv/) |
| Python | 3.12 |

## References

- [AP2 Protocol](https://ap2-protocol.org/) — Google's Agent Payments Protocol specification
- [AP2 GitHub](https://github.com/google-agentic-commerce/AP2) — Reference implementation and SDK
- [x402 Protocol](https://www.x402.org/) — Coinbase's HTTP-native payment standard
- [x402 GitHub](https://github.com/coinbase/x402) — Reference implementation and SDKs
- [Google ADK](https://adk.dev/) — Agent Development Kit documentation
- [Nevermined AP2 + x402 Demo](https://nevermined.ai/blog/building-agentic-payments-with-nevermined-x402-a2a-and-ap2) — Production demo with on-chain settlement
- [AP2 Illustrated Guide](https://arthurchiao.art/blog/ap2-illustrated-guide/) — Visual walkthrough of the protocol flow

## Future: Real x402 Integration

The simulated ledger can be replaced with real on-chain settlement via [Nevermined](https://nevermined.app/):

1. Sign up at nevermined.app, get API keys
2. Install `payments-py` SDK
3. Configure payment plans on the Nevermined platform
4. Swap `protocol/ledger.py` with `NeverminedFacilitator` calls
5. Settlement happens on Base Sepolia testnet with real tx hashes

See the [Nevermined ADK demo](https://github.com/nevermined-io/a2a-x402/tree/main/python/examples/adk-demo) for a production reference implementation.
