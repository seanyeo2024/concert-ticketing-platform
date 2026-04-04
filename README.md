# Concert Ticketing Platform

Concert Ticketing Management System (CTMS) is a microservices-based demo platform for browsing concerts, joining a queue, selecting seats, purchasing tickets, listing resale tickets, and cancelling concerts. The repo includes a static frontend, multiple Flask services, MySQL databases, and RabbitMQ for event-driven flows.

## Stack

- Frontend: HTML, CSS, vanilla JavaScript
- Backend: Python, Flask, Flask-CORS
- Databases: MySQL 8
- Messaging: RabbitMQ
- Container runtime: Docker Compose

## Project Structure

```text
concert-ticketing-platform/
├── database/
│   └── seeds/
├── frontend/
│   ├── assets/
│   └── pages/
├── infra/
│   └── rabbitmq/
├── services/
│   ├── concert/
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

## Services

### Atomic Services

| Service | Host Port | Responsibility |
|---|---:|---|
| `concert` | 5100 | Concert records and seat category configuration |
| `pricing` | 5101 | Price rules and resale caps |
| `queue` | 5102 | Queue entries and purchase window allocation |
| `ticket_inventory` | 5103 | Ticket inventory and ticket state transitions |
| `payment` | 5104 | Purchase and refund records |
| `qr` | 5105 | QR generation and invalidation |
| `notification` | 5106 | Notification event consumer |

### Composite Services

| Service | Host Port | Responsibility |
|---|---:|---|
| `purchase_window` | 5110 | Primary purchase orchestration |
| `resale_purchase` | 5111 | Resale purchase orchestration |
| `concert_cancellation` | 5112 | Concert cancellation and refund orchestration |

### Infrastructure

| Service | Host Port |
|---|---:|
| RabbitMQ AMQP | 5672 |
| RabbitMQ Management UI | 15672 |
| MySQL `concert_db` | 3300 |
| MySQL `pricing_db` | 3301 |
| MySQL `queue_db` | 3302 |
| MySQL `ticket_inventory_db` | 3303 |
| MySQL `payment_db` | 3304 |
| MySQL `qr_db` | 3305 |
| MySQL `notification_db` | 3306 |

## Prerequisites

- Docker Desktop with Linux containers enabled
- Python installed locally if you want to serve the frontend with `python -m http.server`

## Environment Variables

Create a top-level `.env` file in the project root. A working local setup is:

```env
MYSQL_ROOT_PASSWORD=root
MYSQL_USER=ctms
MYSQL_PASSWORD=ctms

RABBITMQ_HOST=rabbitmq
RABBITMQ_PORT=5672
RABBITMQ_USER=ctms
RABBITMQ_PASSWORD=ctms
RABBITMQ_EXCHANGE=ctms_topic

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

PURCHASE_WINDOW_SECONDS=600
MAX_ACTIVE_WINDOWS=5
CONCERT_SERVICE_URL=http://concert:5000

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

### 1. Start the backend stack

From the project root:

```bat
cd c:\Users\Matth\Documents\IS213\concert-ticketing-platform
docker compose up --build
```

If you need a clean reset of the databases:

```bat
docker compose down -v
docker compose up --build
```

### 2. Serve the frontend

Open a second terminal:

```bat
cd c:\Users\Matth\Documents\IS213\concert-ticketing-platform\frontend
python -m http.server 8080
```

Open the app at:

- `http://localhost:8080/pages/index.html`
- Browser API traffic now goes through Kong at `http://localhost:8000`

Useful pages:

- Landing page: `http://localhost:8080/pages/index.html`
- Login: `http://localhost:8080/pages/login.html`
- Admin: `http://localhost:8080/pages/admin.html`
- My Tickets: `http://localhost:8080/pages/my-tickets.html`
- Resale: `http://localhost:8080/pages/resale.html`

## Health Checks

- Kong Proxy example: `http://localhost:8000/concerts`
- Kong Admin API: `http://localhost:8001`
- Concert: `http://localhost:5100/health`
- Pricing: `http://localhost:5101/health`
- Queue: `http://localhost:5102/health`
- Ticket Inventory: `http://localhost:5103/health`
- Payment: `http://localhost:5104/health`
- QR: `http://localhost:5105/health`
- Notification: `http://localhost:5106/health`
- Purchase Window: `http://localhost:5110/health`
- Resale Purchase: `http://localhost:5111/health`
- Concert Cancellation: `http://localhost:5112/health`
- RabbitMQ UI: `http://localhost:15672`

## Demo Accounts

- Customer: `alex@demo.com` / `demo123`
- Customer: `jamie@demo.com` / `demo123`
- Admin: `admin@demo.com` / `admin123`

## Main Flows

### Customer Flow

1. Log in as a customer.
2. Browse concerts from the landing page.
3. Open a concert and join the queue.
4. Wait until a purchase window is granted.
5. Select a real available seat.
6. Complete payment.
7. View the ticket from `My Tickets`.

### Admin Flow

1. Log in as `admin@demo.com`.
2. Create a concert from the admin page.
3. Open `Configure Concert` for that concert.
4. Add one or more seat categories.
5. Set seat count, base price, and resale cap for each category.
6. Save configuration.

The configure flow creates:

- Seat categories in the concert service
- Pricing rules in the pricing service
- Ticket inventory records in the ticket inventory service

The admin page also verifies that ticket inventory was actually created before showing success.

### Concert Cancellation Flow

1. Open the admin page.
2. Use the cancellation section to cancel a concert.
3. The cancellation service updates the concert status, invalidates QRs, refunds payments, and publishes a cancellation event.

## Queue Behavior

The queue service auto-grants purchase windows locally.

- `MAX_ACTIVE_WINDOWS=10` by default
- Up to `min(MAX_ACTIVE_WINDOWS, availableSeats)` users can hold an active purchase window at the same time
- Expired windows are released automatically
- Waiting users are promoted when slots open

If a queue request returns `410 GONE`, that means the purchase window expired and the user must rejoin.

## Notes and Limitations

- The frontend should be served over HTTP. Opening the HTML files directly from disk can cause browser issues.
- The payment, email, and SMS integrations are stubbed for local demo use.
- Kong runs in DB-less mode using `infra/kong/kong.yml`.
- If you re-run queue or purchase tests many times, old queue data may remain in MySQL until you reset the stack with `docker compose down -v`.
- The services are designed for a local demo environment, not production deployment.

## Kong Gateway

Kong is configured as the browser-facing API gateway for this project.

- Proxy URL: `http://localhost:8000`
- Admin API: `http://localhost:8001`
- Declarative config: `infra/kong/kong.yml`

The frontend now sends API requests through Kong for these route prefixes:

- `/concerts`
- `/pricing/v1`
- `/queue/v1`
- `/tickets/v1`
- `/payment/v1`
- `/qr/v1`
- `/notification/v1`
- `/purchase/v1`
- `/resale/v1`
- `/cancellation/v1`

### Quick Tests

After `docker compose up --build`, verify that Kong is proxying requests:

```bat
curl http://localhost:8000/concerts
curl http://localhost:8000/pricing/v1/concerts/CONC-000001/prices
curl http://localhost:8000/tickets/v1/tickets/CONC-000001
```

To inspect what Kong loaded:

```bat
curl http://localhost:8001/services
curl http://localhost:8001/routes
```

### End-to-End Browser Test

1. Start Docker Compose.
2. Serve `frontend/` with `python -m http.server 8080`.
3. Open `http://localhost:8080/pages/index.html`.
4. Open browser DevTools and go to `Network`.
5. Refresh the page and confirm API requests go to `http://localhost:8000/...`.
6. Browse a concert, join a queue, and complete a purchase attempt.

## Troubleshooting

### `port is already allocated`

Another process is already using that host port. Either stop the conflicting process or change the host port in `.env`, then restart Docker Compose.

### RabbitMQ boot failure from invalid password hash

Use the provided `infra/rabbitmq/definitions.json` and make sure `.env` uses:

```env
RABBITMQ_USER=ctms
RABBITMQ_PASSWORD=ctms
RABBITMQ_EXCHANGE=ctms_topic
```

### Frontend is still calling old ports

Hard refresh the browser with `Ctrl + F5` after frontend changes.

### Queue position looks wrong

If queue values seem unexpectedly large, stale queue rows may still exist in the local database. Reset with:

```bat
docker compose down -v
docker compose up --build
```

### Purchase says ticket not found

This usually means the concert was not fully configured or the selected ticket inventory was not created correctly. Reconfigure the concert from the admin page and verify ticket inventory creation succeeds.
