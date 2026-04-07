# Concert Ticketing Platform (CTMS)

CTMS is a microservices-based demo for browsing concerts, joining a queue, selecting seats, purchasing tickets, listing resale tickets, and cancelling concerts. It includes a static frontend, multiple Flask services, MySQL databases, Redis for queue state, RabbitMQ for events, and Kong as the API gateway.

## Stack

- Frontend: HTML, CSS, vanilla JavaScript
- Backend: Python, Flask, Flask-CORS
- Concert Service: OutSystems (cloud-hosted)
- Databases: MySQL 8
- Messaging: RabbitMQ
- Queue cache: Redis
- API gateway: Kong
- Container runtime: Docker Compose

## Concert Service (OutSystems)

Base URL (used by `CONCERT_SERVICE_URL`):

```text
https://personal-cqdsnkhp.outsystemscloud.com/ConcertAPI/rest/v1
```

Endpoints include:
- `GET /concerts`
- `POST /concerts`
- `GET /concerts/{concertId}`
- `PUT /concerts/{concertId}`
- `GET /concerts/{concertId}/seats`
- `POST /concerts/{concertId}/seats`
- `PUT /concerts/{concertId}/seats/{categoryId}`

## Project Structure

```text
concert-ticketing-platform/
├── database/
│   └── seeds/
├── frontend/
│   ├── assets/
│   └── pages/
├── infra/
│   ├── kong/
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
│   ├── resale_ticket/
│   └── ticket_inventory/
└── docker-compose.yml
```

## Services

### Atomic Services

| Service | Host Port | Responsibility |
|---|---:|---|
| `concert` (OutSystems) | N/A | Concert records and seat categories |
| `pricing` | 5101 | Price rules and resale caps |
| `queue` | 5102 | Queue entries and purchase windows |
| `ticket_inventory` | 5103 | Ticket inventory and ticket state |
| `payment` | 5104 | Purchases and refunds |
| `qr` | 5105 | QR generation and invalidation |
| `notification` | 5106 | Notification events |

### Composite / Orchestrators

| Service | Host Port | Responsibility |
|---|---:|---|
| `purchase_window` | 5110 | Primary purchase orchestration |
| `resale_purchase` | 5111 | Resale purchase orchestration |
| `resale_ticket` | 5113 | Resale marketplace gateway |
| `concert_cancellation` | 5112 | Cancellation + refunds + QR invalidation |

### Infrastructure

| Service | Host Port |
|---|---:|
| Kong Proxy | 8000 |
| Kong Admin | 8001 |
| RabbitMQ AMQP | 5672 |
| RabbitMQ UI | 15672 |
| Redis | 6379 |
| MySQL `pricing_db` | 3301 |
| MySQL `queue_db` | 3302 |
| MySQL `ticket_inventory_db` | 3303 |
| MySQL `payment_db` | 3304 |
| MySQL `qr_db` | 3305 |
| MySQL `notification_db` | 3307 |

## Prerequisites

- Docker Desktop (Linux containers enabled)
- Python installed locally (only needed to serve the static frontend)

## Environment

Create a top-level `.env` file. A working local setup is:

```env
MYSQL_ROOT_PASSWORD=root
MYSQL_USER=ctms
MYSQL_PASSWORD=ctms

RABBITMQ_HOST=rabbitmq
RABBITMQ_PORT=5672
RABBITMQ_AMQP_HOST_PORT=5672
RABBITMQ_MANAGEMENT_HOST_PORT=15672
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
EMAIL_PROVIDER=sendgrid
SENDGRID_API_KEY=dummy
EMAIL_FROM=demo@example.com
```

## Startup

### 1) Start backend services

```bat
cd c:\Users\Matth\Documents\IS213\concert-ticketing-platform
docker compose up --build
```

To reset databases and start clean:

```bat
docker compose down -v
docker compose up --build
```

### 2) Serve the frontend

```bat
cd c:\Users\Matth\Documents\IS213\concert-ticketing-platform\frontend
python -m http.server 8080
```

Open:

```text
http://localhost:8080/pages/index.html
```

Useful pages:

```text
http://localhost:8080/pages/login.html
http://localhost:8080/pages/admin.html
http://localhost:8080/pages/my-tickets.html
http://localhost:8080/pages/resale.html
```

## Gateway + Health

Kong routes all browser API traffic:

```text
http://localhost:8000/concerts
http://localhost:8000/pricing/v1/...
http://localhost:8000/queue/v1/...
http://localhost:8000/tickets/v1/...
http://localhost:8000/payment/v1/...
http://localhost:8000/qr/v1/...
http://localhost:8000/notification/v1/...
http://localhost:8000/purchase/v1/...
http://localhost:8000/resale/v1/...
http://localhost:8000/cancellation/v1/...
```

Service health endpoints:

```text
http://localhost:5101/health
http://localhost:5102/health
http://localhost:5103/health
http://localhost:5104/health
http://localhost:5105/health
http://localhost:5106/health
http://localhost:5110/health
http://localhost:5111/health
http://localhost:5112/health
http://localhost:5113/health
```

RabbitMQ UI:

```text
http://localhost:15672
```

## Demo Accounts

- Customer: `alex@demo.com` / `demo123`
- Customer: `jamie@demo.com` / `demo123`
- Admin: `admin@demo.com` / `admin123`

## Main Flows

### Customer Flow

1. Log in as a customer.
2. Browse concerts on the landing page.
3. Open a concert and join the queue.
4. Wait for a purchase window.
5. Select a seat and complete payment.
6. View tickets in My Tickets.

### Admin Flow

1. Log in as admin.
2. Create a concert.
3. Configure seat categories and pricing.
4. Save configuration to generate inventory.

### Cancellation Flow

1. Admin cancels a concert.
2. Tickets are refunded.
3. QR codes are invalidated.
4. Notifications are sent via RabbitMQ.

## Troubleshooting

### `port is already allocated`
Stop the conflicting process or change the host port in `.env`, then restart Docker Compose.

### Queue crashes on startup
Ensure `.env` includes:

```env
PURCHASE_WINDOW_SECONDS=300
MAX_ACTIVE_WINDOWS=5
```

### `basePrice` missing
If the concert DB schema is stale:

```bat
docker compose down -v
docker compose up --build
```

### Frontend calls old ports
Hard refresh the browser with `Ctrl + F5`.

### Concert data not loading
Check `CONCERT_SERVICE_URL` in `.env` and verify the OutSystems endpoint is reachable.

