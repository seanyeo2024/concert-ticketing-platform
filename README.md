# STAGEFRONT — Event Ticketing Platform

A production-grade microservice ticketing platform implementing:
- **Scenario 1**: Virtual Waiting Room (Queue → Purchase → QR)
- **Scenario 2**: Ticket Resale (Seller lists → Buyer purchases → QR regenerated)

---

## Architecture Overview

```
                        ┌─────────────────────────────────────┐
                        │         KONG API Gateway             │
                        │  Rate Limiting · JWT · CORS          │
                        └──────────────┬──────────────────────┘
                                       │ HTTP
         ┌─────────────────────────────┼────────────────────────────┐
         ▼                             ▼                            ▼
  ┌─────────────┐            ┌─────────────────┐          ┌──────────────────┐
  │Queue Service│            │ Purchase Window │          │Resale Ticket Svc │
  │(Composite)  │            │(Composite/Orch) │          │(Composite/Orch)  │
  │replicas: 3  │            │                 │          │                  │
  └──────┬──────┘            └────────┬────────┘          └────────┬─────────┘
         │ Redis                      │ HTTP                        │ HTTP
         │                    ┌───────┼──────────┐        ┌────────┼──────────┐
         ▼                    ▼       ▼           ▼        ▼        ▼          ▼
   ┌──────────┐     ┌──────────────┐ ┌─────────┐ ┌──────────────┐ ┌─────────────┐
   │  Redis   │     │   Ticket     │ │ Payment │ │   Pricing    │ │   Ticket    │
   │  Queue   │     │  Inventory   │ │ Service │ │   Service    │ │  Inventory  │
   │  Store   │     │  (Atomic)    │ │(Atomic) │ │  (Atomic)    │ │  (Atomic)   │
   └──────────┘     └──────────────┘ └────┬────┘ └──────────────┘ └─────────────┘
                                          │ AMQP (RabbitMQ)
                         ┌────────────────┼─────────────────┐
                         ▼                ▼                  ▼
                  ┌───────────┐   ┌───────────────┐  ┌──────────────┐
                  │QR Service │   │ Notification  │  │  RabbitMQ    │
                  │(Atomic)   │   │   Service     │  │   Broker     │
                  └───────────┘   └───────────────┘  └──────────────┘
```

## AMQP Event Flow

| Topic              | Publisher          | Consumers                          |
|--------------------|--------------------|------------------------------------|
| `ticket.confirmed` | Purchase Window    | QR Service, Notification Service   |
| `payment.completed`| Payment Service    | Purchase Window (callback)         |
| `ticket.resold`    | Resale Service     | QR Service, Notification Service   |
| `window.granted`   | Queue Service      | Notification Service               |
| `hold.expired`     | Queue Service      | Notification Service, Inventory    |

## Services

| Service                | Port | Type      | Protocol   |
|------------------------|------|-----------|------------|
| `queue-service`        | 3001 | Composite | HTTP + SSE |
| `event-catalog`        | 3002 | Atomic    | HTTP       |
| `ticket-inventory`     | 3003 | Atomic    | HTTP       |
| `purchase-window`      | 3004 | Composite | HTTP       |
| `payment-service`      | 3005 | Atomic    | HTTP       |
| `notification-service` | 3006 | Atomic    | AMQP only  |
| `qr-service`           | 3007 | Atomic    | HTTP+AMQP  |
| `pricing-service`      | 3008 | Atomic    | HTTP       |
| `resale-ticket-service`| 3009 | Composite | HTTP       |

## Quick Start

```bash
# 1. Clone and install
git clone <repo>
cd ticketing-platform
npm install

# 2. Set up environment variables
cp .env.example .env
# Edit .env with your Stripe keys, SMTP, Twilio credentials

# 3. Start everything
docker-compose -f infrastructure/docker/docker-compose.dev.yml up

# Frontend: http://localhost:3000
# Kong API: http://localhost:8000
# RabbitMQ UI: http://localhost:15672
```

## Environment Variables

```env
STRIPE_SECRET_KEY=sk_test_...
SMTP_HOST=smtp.sendgrid.net
SMTP_USER=apikey
SMTP_PASS=SG....
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM=+1234567890
EMAIL_FROM=tickets@yourplatform.com
```

## Key Design Decisions

**Optimistic Locking** — Ticket inventory uses a `version` column. Concurrent updates
are rejected if the version doesn't match, preventing overselling without row locks.

**Idempotency Keys** — Payment charges include a unique key per session+ticket combo.
Safe to retry on network failure without double-charging.

**SSE for Queue Position** — `GET /queue/stream/:token` uses Server-Sent Events to push
live position updates to the browser without polling overhead.

**Orchestration Pattern** — `purchase-window` and `resale-ticket-service` are composite
services that coordinate multiple atomic services in sequence with rollback logic on failure.

**Per-service Databases** — Each service owns its own PostgreSQL instance. No shared DB,
no cross-service joins. Services communicate via HTTP or AMQP events only.

## File Structure

```
ticketing-platform/
├── frontend/               # Ticketing Website UI (HTML/CSS/JS)
│   └── index.html
├── services/
│   ├── queue-service/      # Virtual waiting room (Redis-backed)
│   ├── event-catalog/      # Concert details
│   ├── ticket-inventory/   # Seat availability + ownership
│   ├── purchase-window/    # Orchestrates Scenario 1 purchase
│   ├── payment-service/    # Stripe integration
│   ├── notification-service# Email + SMS via AMQP consumers
│   ├── qr-service/         # QR generation + invalidation
│   ├── pricing-service/    # Base and resale pricing
│   └── resale-ticket-service/ # Orchestrates Scenario 2 resale
├── shared/
│   ├── types/index.ts      # Domain types (Ticket, Concert, etc.)
│   └── utils/
│       ├── amqp.ts         # RabbitMQ publish/subscribe helpers
│       └── http.ts         # Express error classes + response helpers
└── infrastructure/
    └── docker/
        ├── docker-compose.dev.yml
        └── kong.yml        # Kong declarative config
```
