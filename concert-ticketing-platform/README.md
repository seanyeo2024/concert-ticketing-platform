# Concert Ticketing Platform — IS213 ESD Project

A microservices-based concert ticket management system built with Python/Flask, RabbitMQ, OutSystems, and Docker.

## Architecture Overview

| Layer | Services |
|---|---|
| **UI** | `frontend/` — HTML5 multi-page app |
| **Composite** | `purchase_window`, `resale_purchase`, `concert_cancellation` |
| **Atomic** | `concert` (OutSystems), `pricing`, `queue`, `ticket_inventory`, `payment`, `qr`, `notification` |
| **Messaging** | RabbitMQ (topic exchange) |
| **External** | Stripe API, Twilio/Email API |

## Scenarios

| # | Scenario | Orchestrator |
|---|---|---|
| S1 | Virtual Waiting Room + Purchase | `purchase_window` |
| S2a | Seller lists ticket for resale | `resale_purchase` |
| S2b | Buyer purchases resale ticket | `resale_purchase` |
| S3 | Concert Cancellation + Bulk Refund | `concert_cancellation` |

## Quick Start

```bash
# 1. Copy and configure environment variables
cp .env.example .env

# 2. Start all services (excluding OutSystems Concert Service)
docker-compose up --build

# 3. Open the UI
open frontend/pages/index.html
```

## Port Map

| Service | Port |
|---|---|
| Pricing | 5001 |
| Queue | 5002 |
| Ticket Inventory | 5003 |
| Payment | 5004 |
| QR | 5005 |
| Notification | 5006 |
| Purchase Window | 5010 |
| Resale Purchase | 5011 |
| Concert Cancellation | 5012 |
| RabbitMQ Management UI | 15672 |

## Project Structure

```
concert-ticketing-platform/
├── services/
│   ├── concert/                  # OutSystems — not in Docker Compose
│   ├── pricing/                  # Atomic — port 5001
│   ├── queue/                    # Atomic — port 5002
│   ├── ticket_inventory/         # Atomic — port 5003
│   ├── payment/                  # Atomic — port 5004
│   ├── qr/                       # Atomic — port 5005
│   ├── notification/             # Atomic — port 5006
│   ├── purchase_window/          # Composite — port 5010
│   ├── resale_purchase/          # Composite — port 5011
│   └── concert_cancellation/     # Composite — port 5012
├── frontend/
│   ├── pages/                    # All HTML pages
│   ├── components/               # Reusable HTML partials (navbar, modals)
│   └── assets/
│       ├── css/                  # Global styles + page-specific styles
│       ├── js/                   # API client + page scripts
│       └── images/
├── database/
│   └── seeds/                    # SQL seed files
├── infra/
│   └── rabbitmq/                 # RabbitMQ config + definitions
├── docker-compose.yml
├── .env.example
└── README.md
```

## Team Conventions

- All IDs: UUID v4 or prefixed format (e.g. `TKT-XXXXX`)
- All timestamps: UTC ISO 8601
- All money: `DECIMAL(10,2)` — never floats
- HTTP errors: standard `{ error: { code, message, service, timestamp } }` envelope
- Cross-service refs: soft references only — no cross-DB foreign keys
- Optimistic locking: always pass `version` on Ticket Inventory PUT calls
