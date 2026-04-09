# Concert Ticketing Platform (CTMS)

CTMS is a microservices-based concert ticketing demo that covers the full ticket lifecycle: concert setup, queueing, primary purchase, QR issuance, resale listing and purchase, concert cancellation, refunds, and notifications.

The platform uses a static frontend, multiple Flask microservices, MySQL databases, Redis for queue state, RabbitMQ for asynchronous events, and Kong as the API gateway. The concert domain itself is hosted separately on OutSystems and consumed as an external service.

## What This Demo Supports

- Browse concerts and seat categories
- Join a virtual waiting room before purchase
- Purchase tickets through an orchestrated checkout flow
- Generate and invalidate ticket QR codes
- List tickets for resale and buy resale tickets
- Prevent resale above configured ceiling prices
- Cancel concerts and trigger ticket refunds
- Publish notification events through RabbitMQ

## Architecture

### Atomic services

| Service | Host Port | Purpose |
|---|---:|---|
| `concert` (OutSystems) | N/A | Concert records and seat category definitions |
| `pricing` | `5101` | Base prices and resale ceiling rules |
| `queue` | `5102` | Queue state, purchase windows, Redis-backed admission |
| `ticket_inventory` | `5103` | Ticket creation, ownership, status, resale listing state |
| `payment` | `5104` | Purchase, resale purchase, refund, and payout records |
| `qr` | `5105` | QR generation, lookup, scanning, and invalidation |
| `notification` | `5106` | Contact preferences and RabbitMQ-driven notifications |

### Composite services

| Service | Host Port | Purpose |
|---|---:|---|
| `purchase_window` | `5110` | Primary ticket purchase orchestration |
| `resale_purchase` | `5111` | Resale purchase orchestration |
| `concert_cancellation` | `5112` | Cancellation, refund, QR invalidation, event publishing |
| `resale_ticket` | `5113` | Resale marketplace gateway for browse/list/unlist/purchase |

### Infrastructure

| Component | Host Port | Notes |
|---|---:|---|
| Kong Proxy | `8000` | Browser/API entry point |
| Kong Admin | `8001` | Kong admin API |
| RabbitMQ AMQP | `5673` | From the current `.env` |
| RabbitMQ Management UI | `15673` | From the current `.env` |
| Redis | `6379` | Queue/session cache |
| MySQL `pricing_db` | `3301` | Seeded on startup |
| MySQL `queue_db` | `3302` | Seeded on startup |
| MySQL `ticket_inventory_db` | `3303` | Seeded on startup |
| MySQL `payment_db` | `3304` | Seeded on startup |
| MySQL `qr_db` | `3305` | Seeded on startup |
| MySQL `notification_db` | `3307` | Seeded on startup |

## High-Level Flow

1. Admin creates or updates concerts and seat categories through the hosted Concert service.
2. Pricing rules are configured in the pricing service.
3. Customers browse concerts from the frontend through Kong.
4. Customers join the queue and wait for a purchase window.
5. The purchase orchestrator locks a ticket, processes payment, and requests a QR code.
6. Purchased tickets can later be listed on the resale marketplace if policy allows.
7. Resale purchases transfer ownership, invalidate the seller QR, and issue a buyer QR.
8. If a concert is cancelled, tickets are refunded, QRs are invalidated, and notifications are emitted.

## Project Structure

```text
concert-ticketing-platform/
  database/
    seeds/
  diagrams/
  frontend/
    assets/
    pages/
  infra/
    kong/
    rabbitmq/
  scripts/
  services/
    concert_cancellation/
    notification/
    payment/
    pricing/
    purchase_window/
    qr/
    queue/
    resale_purchase/
    resale_ticket/
    ticket_inventory/
  docker-compose.yml
  README.md
```

## Frontend Pages

Serve the frontend locally, then open:

- `http://localhost:8080/pages/index.html`
- `http://localhost:8080/pages/login.html`
- `http://localhost:8080/pages/admin.html`
- `http://localhost:8080/pages/my-tickets.html`
- `http://localhost:8080/pages/resale.html`

## Gateway Routes

Kong exposes the browser-facing API surface:

- `GET /concerts`
- `GET|POST|PUT /pricing/v1/...`
- `GET|POST|PUT|DELETE /queue/v1/...`
- `GET|POST|PUT /tickets/v1/...`
- `GET|POST /payment/v1/...`
- `GET|POST|PUT /qr/v1/...`
- `GET|PUT /notification/v1/...`
- `POST /purchase/v1/...`
- `POST /resale/v1/...`
- `GET|POST|PUT /resale-ticket/v1/...`
- `POST /cancellation/v1/...`

Base URL:

```text
http://localhost:8000
```

## Concert Service

The concert service is hosted externally on OutSystems and is not started by Docker Compose.

Configured base URL:

```text
https://personal-cqdsnkhp.outsystemscloud.com/ConcertAPI/rest/v1
```

Common endpoints:

- `GET /concerts`
- `POST /concerts`
- `GET /concerts/{concertId}`
- `PUT /concerts/{concertId}`
- `GET /concerts/{concertId}/seats`
- `POST /concerts/{concertId}/seats`
- `PUT /concerts/{concertId}/seats/{categoryId}`

## Prerequisites

- Docker Desktop with Linux containers enabled
- Python 3.x for serving the static frontend

## Environment Setup

Create a root `.env` file before starting the stack.

Use placeholder or local test credentials only. Do not commit real Stripe, Twilio, SMTP, or email credentials.

Example:

```env
MYSQL_ROOT_PASSWORD=root
MYSQL_USER=ctms
MYSQL_PASSWORD=ctms

RABBITMQ_HOST=rabbitmq
RABBITMQ_PORT=5672
RABBITMQ_AMQP_HOST_PORT=5673
RABBITMQ_MANAGEMENT_HOST_PORT=15673
RABBITMQ_USER=ctms
RABBITMQ_PASSWORD=ctms
RABBITMQ_EXCHANGE=ctms_topic

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_HOST_PORT=6379

KONG_PROXY_PORT=8000
KONG_ADMIN_PORT=8001

CONCERT_PORT=5100
PRICING_PORT=5101
QUEUE_PORT=5102
TICKET_INVENTORY_PORT=5103
PAYMENT_PORT=5104
QR_PORT=5105
NOTIFICATION_PORT=5106
PURCHASE_WINDOW_PORT=5110
RESALE_PURCHASE_PORT=5111
CONCERT_CANCELLATION_PORT=5112
RESALE_TICKET_PORT=5113

PURCHASE_WINDOW_SECONDS=300
MAX_ACTIVE_WINDOWS=5
CONCERT_SERVICE_URL=https://personal-cqdsnkhp.outsystemscloud.com/ConcertAPI/rest/v1

STRIPE_SECRET_KEY=dummy
QR_HMAC_SECRET=dev-secret
TWILIO_ACCOUNT_SID=dummy
TWILIO_AUTH_TOKEN=dummy
TWILIO_FROM_NUMBER=+10000000000
TWILIO_WHATSAPP_FROM_NUMBER=+14155238886
USE_WHATSAPP_SANDBOX_FOR_SMS=false
FORCE_EMAIL_NOTIFICATIONS=true
EMAIL_PROVIDER=gmail_smtp
SENDGRID_API_KEY=dummy
EMAIL_FROM=demo@example.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USERNAME=dummy
SMTP_PASSWORD=dummy
SMTP_FROM=demo@example.com
```

## Notification Smoke Test

After the stack is up, you can verify the notification service directly without going through checkout.

Check the loaded delivery configuration:

```bash
curl http://localhost:8000/notification/v1/config
```

Send a test email and SMS to your own recipients:

```bash
curl -X POST http://localhost:8000/notification/v1/test \
  -H "Content-Type: application/json" \
  -d "{\"userId\":\"demo-user\",\"email\":\"you@example.com\",\"phoneNumber\":\"+6591234567\",\"channels\":[\"email\",\"sms\"],\"subject\":\"CTMS smoke test\",\"body\":\"This is a notification smoke test.\"}"
```

If you want to test WhatsApp delivery through Twilio sandbox, change `channels` to include `whatsapp` and set `USE_WHATSAPP_SANDBOX_FOR_SMS=true`.

## Running The Platform

### Start backend services

Windows:

```bat
run-backend.bat
```

macOS/Linux:

```sh
./run-backend.sh
```

Or directly:

```sh
docker compose up --build
```

### Start frontend

Windows:

```bat
run-program.bat
```

macOS/Linux:

```sh
./run-program.sh
```

Or directly:

```sh
cd frontend
python -m http.server 8080
```

## Resetting The Stack

To wipe MySQL volumes and reseed the local environment:

```sh
docker compose down -v
docker compose up --build
```

Helper scripts are also included:

- `run-backend-wipe-db.bat`
- `run-backend-wipe-db.sh`

## Health Checks

Direct service health endpoints:

- `http://localhost:5101/health`
- `http://localhost:5102/health`
- `http://localhost:5103/health`
- `http://localhost:5104/health`
- `http://localhost:5105/health`
- `http://localhost:5106/health`
- `http://localhost:5110/health`
- `http://localhost:5111/health`
- `http://localhost:5112/health`
- `http://localhost:5113/health`

RabbitMQ UI:

```text
http://localhost:15673
```

## Demo Accounts

| Role | Email | Password |
|---|---|---|
| Customer | `alex@demo.com` | `demo123` |
| Customer | `jamie@demo.com` | `demo123` |
| Admin | `admin@demo.com` | `admin123` |

## Main Demo Scenarios

### Customer purchase flow

1. Sign in as `alex@demo.com` or `jamie@demo.com`.
2. Browse the concert lineup.
3. Open a concert and join the queue.
4. Wait for the purchase window.
5. Select a ticket and complete payment.
6. View the ticket and QR code in `My Tickets`.

### Admin flow

1. Sign in as `admin@demo.com`.
2. Create or update a concert.
3. Configure seat categories.
4. Configure price and resale ceiling rules.
5. Verify inventory and ticket availability.

### Resale flow

1. Purchase a ticket as a customer.
2. Go to `My Tickets` and list the ticket for resale.
3. Browse listings from the resale marketplace page.
4. Purchase a resale ticket as another customer.
5. Confirm that ownership changes and a new QR is issued.

### Cancellation flow

1. Cancel a concert as admin.
2. Verify ticket statuses become refunded.
3. Verify QR codes are invalidated.
4. Verify refund records and notification events are created.

## Diagrams And Supporting Documents

- [Combined Diagram 1-3 Overview](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/diagrams/Combined%20Diagram%201-3-Overview.drawio.png)
- [Combined Diagram 1-3 Virtual Waiting Room](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/diagrams/Combined%20Diagram%201-3-Virtual%20Waiting%20Room.drawio.png)
- [Combined Diagram 1-3 Resale Of Tickets](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/diagrams/Combined%20Diagram%201-3-Resale%20of%20Tickets.drawio%20(1).png)
- [Combined Diagram 1-3 Concert Cancellation](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/diagrams/Combined%20Diagram%201-3-Concert%20Cancellation.drawio.png)
- [Combined Diagram 1-3 DB](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/diagrams/Combined%20Diagram%201-3-DB.drawio.png)
- [Use Case 2 Resale Ticketing](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/USECASE_2_RESALE_TICKETING.md)
- [Branch Comparison Notes](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/BRANCH_COMPARISON_MAIN_VS_FUNCTIONAL_CHANGES.md)

## Troubleshooting

### `port is already allocated`

Change the conflicting host port in `.env`, then restart Docker Compose.

### Queue service fails on startup

Check that these environment variables exist:

```env
PURCHASE_WINDOW_SECONDS=300
MAX_ACTIVE_WINDOWS=5
```

### Concert data does not load

Verify `CONCERT_SERVICE_URL` and confirm the hosted OutSystems endpoint is reachable.

### Frontend keeps calling old values

Hard refresh the browser with `Ctrl + F5`.

### Seed data or schema looks stale

Recreate the containers and volumes:

```sh
docker compose down -v
docker compose up --build
```

## Notes

- This is a demo-oriented system, not a production-hardened deployment.
- The frontend is plain HTML, CSS, and JavaScript served as static files.
- Payment flows use test-mode behavior and should be treated as sandbox/demo flows only.
- The checked-in root `.env` should be treated as local developer configuration, not documentation.
