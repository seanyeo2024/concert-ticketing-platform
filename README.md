# Concert Ticketing Platform

Microservices-based concert ticketing demo for IS213/ESD. The project combines a static multi-page frontend, Flask-based backend services, RabbitMQ eventing, and MySQL per-service databases to model primary sales, resale, queueing, QR issuance, and concert cancellation.

## What Is In This Repository

This repository contains:

- A static frontend in `frontend/` with pages for browsing concerts, joining queues, selecting seats, buying tickets, managing resale, viewing profiles, and basic admin actions.
- Atomic Flask services in `services/` for pricing, queue management, ticket inventory, payment, QR issuance, and notifications.
- Composite/orchestrator Flask services in `services/` for purchase flow, resale flow, and concert cancellation.
- Docker Compose infrastructure for RabbitMQ and one MySQL database per atomic service.
- SQL seed files in `database/seeds/` for the concert and ticket inventory datasets.
- RabbitMQ bootstrap config in `infra/rabbitmq/`.

There is also a nested duplicate copy of the project at `concert-ticketing-platform/concert-ticketing-platform/`. The top-level `concert-ticketing-platform/` appears to be the main working copy.

## Tech Stack

- Frontend: HTML, CSS, vanilla JavaScript
- Backend: Python, Flask, Flask-CORS
- Databases: MySQL 8
- Messaging: RabbitMQ topic exchange
- Containerization: Docker Compose
- External/demo integrations: OutSystems Concert API, Stripe, Twilio, SendGrid

## Architecture

### Frontend

The frontend is a demo-first static site. Shared client logic lives in `frontend/assets/js/api.js`.

Important behavior:

- Uses real HTTP endpoints when services are available.
- Falls back to seeded demo data if backend requests fail.
- Includes local demo authentication with customer and admin accounts stored in browser storage.

### Atomic services

| Service | Port | Responsibility |
|---|---:|---|
| `pricing` | 5001 | Price rules and resale ceilings per concert/category |
| `queue` | 5002 | Waiting-room queue entries and purchase windows |
| `ticket_inventory` | 5003 | Ticket records, status transitions, resale inventory |
| `payment` | 5004 | Purchase/refund records with Stripe-style stubs |
| `qr` | 5005 | QR generation, validation, and invalidation |
| `notification` | 5006 | Event consumer and notification log |

### Composite services

| Service | Port | Responsibility |
|---|---:|---|
| `purchase_window` | 5010 | Queue validation, ticket lock, payment, confirmation, QR creation |
| `resale_purchase` | 5011 | Ticket listing and resale purchase transfer flow |
| `concert_cancellation` | 5012 | Concert cancellation, ticket refunds, QR invalidation |

### External dependency

- Concert service: expected to be hosted separately via OutSystems and called over HTTP through `CONCERT_SERVICE_URL`.

## Main User Flows

### 1. Primary purchase with waiting room

Handled by `purchase_window`:

1. Validate that the user has an active queue window.
2. Fetch the ticket and confirm it is available.
3. Fetch pricing.
4. Lock the ticket as `PENDING`.
5. Create a payment.
6. Confirm ticket ownership.
7. Mark the queue entry as completed.
8. Generate a QR code.
9. Publish a `ticket.purchased` event.

### 2. Resale listing and purchase

Handled by `resale_purchase`:

- Sellers can list a `CONFIRMED` ticket for resale.
- Resale price is validated against the pricing ceiling.
- Buyers can purchase a `RESALE_LISTED` ticket.
- The old QR is invalidated and a new QR is issued to the new owner.
- Resale sale events are published for notifications.

### 3. Concert cancellation

Handled by `concert_cancellation`:

- Marks the concert as `CANCELLED` via the external concert service.
- Bulk-updates ticket statuses to `REFUNDED`.
- Invalidates all QRs for the concert.
- Iterates through recorded payments and creates refunds.
- Publishes a `concert.cancelled` event.

## Frontend Pages

| Page | Purpose |
|---|---|
| `frontend/pages/index.html` | Concert listing / landing page |
| `frontend/pages/concert-detail.html` | Concert details, category view, join queue |
| `frontend/pages/queue.html` | Waiting room status and purchase window countdown |
| `frontend/pages/seat-select.html` | Seat selection and purchase submission |
| `frontend/pages/resale.html` | Browse resale listings and buy resale tickets |
| `frontend/pages/my-tickets.html` | View owned tickets, QR, and resale actions |
| `frontend/pages/profile.html` | Profile, payments, and notification history |
| `frontend/pages/login.html` | Demo sign-in |
| `frontend/pages/admin.html` | Admin dashboard, cancellation, queue depth, payments |

## API Surface Summary

### Pricing

- `GET /pricing/v1/concerts/<concertId>/prices`
- `GET /pricing/v1/concerts/<concertId>/prices/<categoryId>`
- `GET /pricing/v1/concerts/<concertId>/prices/<categoryId>/ceiling`
- `POST /pricing/v1/concerts/<concertId>/prices`
- `PUT /pricing/v1/concerts/<concertId>/prices/<categoryId>`

### Queue

- `POST /queue/v1/queue/<concertId>`
- `GET /queue/v1/queue/<concertId>/<userId>`
- `GET /queue/v1/queue/<concertId>`
- `PUT /queue/v1/queue/<concertId>/<userId>`
- `DELETE /queue/v1/queue/<concertId>/<userId>`

### Ticket Inventory

- `GET /tickets/v1/tickets/<concertId>`
- `GET /tickets/v1/tickets/<concertId>/resale`
- `GET /tickets/v1/tickets/<concertId>/<ticketId>`
- `POST /tickets/v1/tickets`
- `PUT /tickets/v1/tickets/<concertId>/<ticketId>`
- `PUT /tickets/v1/tickets/<concertId>/cancel-all`

### Payment

- `POST /payment/v1/payment`
- `POST /payment/v1/payment/refund`
- `GET /payment/v1/payment/<paymentId>`
- `GET /payment/v1/payment/user/<userId>`
- `GET /payment/v1/payment/concert/<concertId>`

### QR

- `POST /qr/v1/qr`
- `GET /qr/v1/qr/<ticketId>`
- `GET /qr/v1/qr/<ticketId>/validate`
- `PUT /qr/v1/qr/<ticketId>/invalidate`
- `PUT /qr/v1/qr/concert/<concertId>/invalidate-all`

### Notification

- `GET /notification/v1/notification/<notificationId>`
- `GET /notification/v1/notification/user/<userId>`

### Composite flows

- `POST /purchase/v1/window/<concertId>`
- `POST /resale/v1/list`
- `POST /resale/v1/purchase`
- `POST /cancellation/v1/<concertId>`

## Eventing

RabbitMQ is configured as a topic-based event bus. The code currently publishes or consumes these routing keys:

- `ticket.purchased`
- `ticket.resale.listed`
- `ticket.resale.sold`
- `concert.cancelled`
- `queue.window.granted`
- `queue.window.expired`

The `notification` service binds a `notification_all` queue to receive all routing keys.

## Data and Demo Behavior

- `database/seeds/ticket_inventory_db.sql` seeds ticket inventory data.
- `database/seeds/concert_db.sql` contains concert-related seed data.
- `frontend/assets/js/api.js` also embeds fallback demo data for concerts, categories, prices, tickets, payments, and notifications.
- Demo login accounts are defined in the frontend:
  - Customer: `alex@demo.com` / `demo123`
  - Customer: `jamie@demo.com` / `demo123`
  - Admin: `admin@demo.com` / `admin123`

## Running The Project

### Prerequisites

- Docker and Docker Compose
- An accessible OutSystems Concert API endpoint
- Optional real credentials for Stripe, Twilio, and SendGrid if you want to replace the stubs

### Start with Docker Compose

```bash
docker-compose up --build
```

This starts:

- RabbitMQ with management UI on `http://localhost:15672`
- MySQL containers for pricing, queue, ticket inventory, payment, QR, and notification
- All Flask services in the repository

### Environment variables expected by Compose

The compose file references variables such as:

- `MYSQL_ROOT_PASSWORD`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `RABBITMQ_HOST`
- `RABBITMQ_PORT`
- `RABBITMQ_USER`
- `RABBITMQ_PASSWORD`
- `RABBITMQ_EXCHANGE`
- `PRICING_PORT`
- `QUEUE_PORT`
- `TICKET_INVENTORY_PORT`
- `PAYMENT_PORT`
- `QR_PORT`
- `NOTIFICATION_PORT`
- `PURCHASE_WINDOW_PORT`
- `RESALE_PURCHASE_PORT`
- `CONCERT_CANCELLATION_PORT`
- `PURCHASE_WINDOW_SECONDS`
- `CONCERT_SERVICE_URL`
- `STRIPE_SECRET_KEY`
- `QR_HMAC_SECRET`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`
- `EMAIL_PROVIDER`
- `SENDGRID_API_KEY`
- `EMAIL_FROM`

Note: this repository currently does not appear to include a top-level `.env.example`, so you will need to define these values yourself before running Compose successfully.

### Opening the frontend

The frontend pages are plain HTML files. You can open `frontend/pages/index.html` directly in a browser, but the best experience comes when the backend services are running locally on the documented ports.

## Project Structure

```text
concert-ticketing-platform/
├── database/
│   └── seeds/
├── frontend/
│   ├── assets/
│   │   ├── css/
│   │   └── js/
│   └── pages/
├── infra/
│   └── rabbitmq/
├── services/
│   ├── concert_cancellation/
│   ├── notification/
│   ├── payment/
│   ├── pricing/
│   ├── purchase_window/
│   ├── qr/
│   ├── queue/
│   ├── resale_purchase/
│   └── ticket_inventory/
└── docker-compose.yml
```

## Current Implementation Notes

- The payment service contains Stripe-style stubs rather than a full Stripe SDK integration.
- The notification service contains email and SMS stubs rather than live delivery integrations.
- The frontend is resilient for demos because it falls back to local seed data when services are unavailable.
- The notification service starts a background RabbitMQ consumer thread at app startup.
- Ticket updates use optimistic locking via a `version` field in `ticket_inventory`.

## Suggested Next Improvements

- Add a real `.env.example`.
- Document the OutSystems Concert API contract more explicitly.
- Replace payment and notification stubs with real integrations.
- Add automated tests for orchestrator failure and rollback paths.
- Remove or clarify the duplicated nested project folder.
