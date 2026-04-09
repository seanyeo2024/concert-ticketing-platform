# Codebase Step Annotations

This document explains, in step form, what each major code file does in the concert ticketing platform.

It is meant to help you:

- understand the responsibility of each file
- explain the system during demos or viva
- quickly trace where a feature is implemented

It focuses on source code, app logic, frontend pages, infrastructure config, and seeded databases.

## 1. Root Files

### [README.md](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/README.md)

Purpose:

- gives the platform-level overview
- lists services, ports, and main scenarios
- explains how to run the stack

Step flow:

1. Defines what the system supports.
2. Splits the system into atomic services, composite services, and infrastructure.
3. Lists frontend entry pages.
4. shows Kong gateway routes.
5. gives startup, reset, and troubleshooting instructions.

### [docker-compose.yml](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/docker-compose.yml)

Purpose:

- wires all services, databases, Redis, RabbitMQ, and Kong together

Step flow:

1. Starts each MySQL database container with its own seed script.
2. Starts Redis for queue/session state.
3. Starts RabbitMQ for async notifications.
4. Starts each Flask microservice with env vars and network links.
5. Starts Kong as the browser-facing API gateway.

### [.env](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/.env)

Purpose:

- stores runtime configuration

Step flow:

1. defines DB credentials and service ports
2. defines external service URLs
3. defines Stripe, QR, Twilio, and SMTP settings
4. provides the Stripe Connect account mapping used for sandbox resale payouts

### [run-backend.bat](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/run-backend.bat), [run-backend.sh](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/run-backend.sh)

Purpose:

- convenience launchers for backend services

### [run-program.bat](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/run-program.bat), [run-program.sh](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/run-program.sh)

Purpose:

- convenience launchers for the static frontend

## 2. Frontend Shared Layer

### [frontend/assets/js/api.js](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/frontend/assets/js/api.js)

Purpose:

- shared frontend runtime layer
- contains API client, auth, utilities, toast helpers, navbar rendering, and live-sync utilities

Step flow:

1. Creates a custom cursor effect for desktop devices.
2. Defines seed fallback objects for demo resilience.
3. Builds a shared `API` object that talks to Kong.
4. Splits API calls by domain:
   - concerts
   - pricing
   - queue
   - tickets
   - payment
   - qr
   - notification
   - purchase
   - resale
   - cancellation
5. Normalizes concert date/time handling and local schedule overrides.
6. Provides ticket summary aggregation from local inventory.
7. Defines `ContactProfile` helpers to read and save user contact info.
8. Defines `Auth` with hardcoded demo users:
   - Alex
   - Jamie
   - Admin
9. Defines `toast` for temporary UI alerts.
10. Defines `renderNav` for the top navigation bar.
11. Defines `Util` helpers for date formatting, pricing, tags, and backgrounds.
12. Defines `LiveSync` to notify multiple tabs/pages when data changes.
13. Defines modal open/close helpers.

### [frontend/assets/css/global.css](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/frontend/assets/css/global.css)

Purpose:

- global visual system for all pages

Step flow:

1. defines shared colors, spacing, buttons, cards, modals, and tags
2. defines page-level reusable layout classes
3. supports the custom brand look used across the site

## 3. Frontend Pages

### [frontend/pages/login.html](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/frontend/pages/login.html)

Purpose:

- handles demo login

Step flow:

1. decides where to redirect after login
2. allows quick-fill demo credentials
3. validates login using `Auth.login(...)`
4. stores the logged-in user in local storage
5. redirects admin to admin page and customer to lineup

### [frontend/pages/index.html](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/frontend/pages/index.html)

Purpose:

- lineup landing page for customers

Step flow:

1. loads concerts from the concert service
2. refreshes local inventory counts for each concert
3. refreshes base prices from the pricing service
4. picks a featured upcoming concert
5. renders the featured hero card
6. renders the lineup card list
7. applies filters and pagination
8. periodically auto-refreshes inventory-sensitive content

Seat source:

- concert cards are driven by local ticket inventory counts

### [frontend/pages/concert-detail.html](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/frontend/pages/concert-detail.html)

Purpose:

- shows details for one concert and lets a customer choose a category before joining queue

Step flow:

1. loads the selected concert
2. loads OutSystems seat-category metadata
3. loads pricing rules
4. loads local inventory summary
5. builds the displayed category list from local inventory first
6. enriches category names and prices with concert/pricing data when available
7. renders banner stats such as remaining seats
8. renders category cards
9. lets user select a category
10. sends the user into `queue.html`

Seat source:

- category availability is driven by local ticket inventory

### [frontend/pages/queue.html](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/frontend/pages/queue.html)

Purpose:

- virtual waiting room page

Step flow:

1. reads the concert and category from the URL
2. loads concert information for display
3. joins queue or resumes saved queue session
4. polls queue status repeatedly
5. sends queue heartbeats so the session stays alive
6. starts a live countdown when the purchase window is granted
7. redirects user to seat selection when window opens
8. lets user leave queue or rejoin after expiry

### [frontend/pages/seat-select.html](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/frontend/pages/seat-select.html)

Purpose:

- primary purchase page during an active purchase window

Step flow:

1. checks purchase window session from queue
2. starts window timer and heartbeat loop
3. loads available seats for the chosen concert/category
4. loads price for the chosen category
5. renders seat map from local inventory tickets
6. lets user pick one seat
7. maps demo card input to Stripe test payment method IDs
8. validates contact details
9. calls purchase orchestrator
10. shows purchase success and links to `My Tickets`

### [frontend/pages/my-tickets.html](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/frontend/pages/my-tickets.html)

Purpose:

- shows customer-owned tickets and resale actions

Step flow:

1. loads the logged-in user’s tickets
2. loads contact info for purchase/resale flows
3. splits views into active, resale, and past tickets
4. calculates lifecycle labels for each ticket
5. shows QR viewing for confirmed tickets
6. opens resale modal for eligible tickets
7. submits resale listing requests
8. lets seller cancel an active listing
9. listens for live updates across tabs

### [frontend/pages/resale.html](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/frontend/pages/resale.html)

Purpose:

- resale marketplace browse and buy page

Step flow:

1. loads all concerts and resale listings
2. hydrates category metadata for filters
3. builds concert and category filter dropdowns
4. applies price and category filters
5. renders resale listing cards
6. opens purchase modal for a chosen listing
7. ensures buyer contact details are present
8. submits resale purchase to resale gateway/orchestrator
9. refreshes listings after successful purchase

### [frontend/pages/profile.html](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/frontend/pages/profile.html)

Purpose:

- user profile, settings, and activity view

Step flow:

1. switches between tabs such as overview, activity, and settings
2. normalizes email and phone inputs
3. loads saved contact settings
4. loads payments, tickets, and notifications
5. maps those records into one activity stream
6. renders overview stats
7. saves updated contact preferences
8. refreshes on focus/visibility events

### [frontend/pages/admin.html](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/frontend/pages/admin.html)

Purpose:

- admin control panel

Step flow:

1. handles panel switching by hash
2. loads system health for each service
3. loads dashboard summary metrics
4. loads concerts with local inventory counts
5. renders all concerts list
6. opens concert detail/configure flows
7. loads configure dropdown using OutSystems seat-category totals
8. previews concert categories, inventory, and pricing rules
9. builds editable configuration rows
10. saves concert schedule updates
11. configures pricing rules and bulk ticket inventory creation
12. loads cancellation targets and triggers concert cancellation
13. opens QR scanner modal
14. decodes QR from camera or manual input
15. confirms scan result with QR service
16. auto-refreshes queue monitor and dashboard data

Seat source rules:

- admin concert list uses local ticket inventory
- configure dropdown total seats uses OutSystems seat categories

## 4. Atomic Backend Services

### [services/pricing/src/app.py](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/services/pricing/src/app.py)

Purpose:

- stores base prices and resale ceilings per concert category

Step flow:

1. connects to `pricing_db`
2. creates `price_rule` table if missing
3. optionally validates that a seat category exists in the concert service
4. returns all price rules for a concert
5. returns one price rule by category
6. returns resale ceiling for one category
7. creates a new price rule
8. updates an existing rule
9. exposes service health

### [services/ticket_inventory/src/app.py](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/services/ticket_inventory/src/app.py)

Purpose:

- source of truth for local ticket rows and ownership state

Step flow:

1. connects to `ticket_inventory_db`
2. creates `ticket` table if missing
3. defines allowed status transitions:
   - `AVAILABLE -> PENDING`
   - `PENDING -> AVAILABLE|CONFIRMED|REFUNDED`
   - `CONFIRMED -> RESALE_LISTED|USED|REFUNDED`
   - `RESALE_LISTED -> RESALE_PENDING|CONFIRMED|REFUNDED`
   - `RESALE_PENDING -> RESALE_LISTED|CONFIRMED|REFUNDED`
4. lists tickets for a concert
5. lists resale-listed tickets for a concert
6. fetches a single ticket
7. bulk-creates ticket rows for admin configuration
8. updates a ticket with optimistic locking
9. marks all active tickets as pending refund during concert cancellation
10. confirms refund status in batches
11. exposes health

### [services/payment/src/app.py](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/services/payment/src/app.py)

Purpose:

- records payments and talks to Stripe

Step flow:

1. connects to `payment_db`
2. creates `payment_record` table if missing
3. validates amount and currency
4. resolves frontend test payment method aliases to Stripe test method IDs
5. loads Stripe Connect account mappings from env
6. for normal purchase:
   - creates Stripe `PaymentIntent`
   - stores `PURCHASE`
7. for resale purchase:
   - requires `sellerId`
   - resolves seller connected account
   - creates Stripe destination charge
   - stores `RESALE_PURCHASE`
8. for refund:
   - finds original payment
   - calls Stripe refund
   - reverses transfer if original type was resale purchase
   - stores `REFUND`
9. keeps the old `resale-payout` endpoint for backward-compatible internal bookkeeping
10. exposes lookup endpoints by payment, user, and concert
11. exposes health and config endpoint

### [services/qr/src/app.py](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/services/qr/src/app.py)

Purpose:

- creates, validates, scans, and invalidates ticket QR codes

Step flow:

1. connects to `qr_db`
2. creates `qr_code` table if missing
3. generates signed QR payloads using `QR_HMAC_SECRET`
4. generates base64 QR images
5. decodes and verifies QR payload integrity
6. fetches ticket and concert metadata when validating a QR
7. generates QR for a ticket owner
8. returns existing QR by ticket ID
9. validates QR without consuming it
10. scans QR and optionally confirms entry
11. updates ticket status to `USED` when confirmed
12. invalidates one QR or all QRs for a concert
13. exposes health

### [services/queue/src/app.py](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/services/queue/src/app.py)

Purpose:

- MySQL-backed queue implementation

Step flow:

1. connects to `queue_db`
2. creates queue schema
3. fetches concert metadata
4. checks available inventory
5. expires old granted windows
6. rebalances waiting positions
7. grants new windows when capacity is available
8. publishes queue events to RabbitMQ
9. supports join, status lookup, depth lookup, update, and leave

Note:

- this file is the SQL queue implementation
- the app appears to use the Redis-backed implementation for richer session handling

### [services/queue/src/redis_queue.py](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/services/queue/src/redis_queue.py)

Purpose:

- Redis-backed queue/session implementation

Step flow:

1. defines Redis keys for entries, waiting set, granted set, and locks
2. reads and saves queue entries in Redis
3. computes queue position
4. detects stale sessions and heartbeats
5. expires granted windows
6. grants new windows when seats are available
7. publishes queue-related events
8. exposes queue join, status, depth, update, leave
9. validates queue sessions for seat selection
10. accepts heartbeat updates
11. consumes a granted session when purchase begins

### [services/notification/src/app.py](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/services/notification/src/app.py)

Purpose:

- contact preference storage and event-driven notification delivery

Step flow:

1. connects to `notification_db`
2. creates notification/contact tables if missing
3. validates and normalizes phone/email data
4. stores contact hints for users
5. fetches concert metadata to enrich messages
6. defines templates for queue, purchase, resale, and cancellation events
7. composes email and SMS bodies
8. sends email through SMTP or SendGrid
9. sends SMS or WhatsApp through Twilio
10. logs each delivery attempt
11. consumes RabbitMQ events continuously
12. exposes notification lookup endpoints
13. exposes contact get/update endpoints
14. exposes config and test-delivery endpoints
15. exposes health

## 5. Composite Backend Services

### [services/purchase_window/src/app.py](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/services/purchase_window/src/app.py)

Purpose:

- orchestrates primary purchase

Step flow:

1. validates purchase request
2. resolves queue/session context
3. resolves target ticket
4. locks ticket by moving it from `AVAILABLE` to `PENDING`
5. fetches price for the selected category
6. calls payment service for `PURCHASE`
7. if payment fails, rolls ticket back to `AVAILABLE`
8. if payment succeeds:
   - confirms ticket ownership
   - sets purchase price
   - generates buyer QR
   - publishes purchase event
9. returns final purchase response

### [services/resale_purchase/src/app.py](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/services/resale_purchase/src/app.py)

Purpose:

- orchestrates listing and buying a resale ticket

Step flow for `POST /resale/v1/list`:

1. checks required fields
2. fetches ticket from inventory
3. verifies seller owns it
4. verifies ticket is `CONFIRMED`
5. verifies resale policy, including one-time resale rule
6. optionally checks price ceiling with pricing service
7. updates ticket to `RESALE_LISTED`
8. emits resale-listed notification event

Step flow for `POST /resale/v1/purchase`:

1. fetches ticket and confirms it is resale-listed
2. reads seller from current `ownerId`
3. checks resale ceiling again
4. moves ticket to `RESALE_PENDING`
5. calls payment service for `RESALE_PURCHASE`
6. if payment fails, rolls back ticket to `RESALE_LISTED`
7. records backward-compatible resale payout entry
8. invalidates seller QR
9. transfers ticket ownership to buyer
10. resets resale fields on the ticket
11. generates buyer QR
12. publishes notifications to seller and buyer

### [services/resale_ticket/src/app.py](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/services/resale_ticket/src/app.py)

Purpose:

- frontend-facing resale gateway

Step flow:

1. lists resale marketplace entries for a concert
2. enriches listings with category pricing/currency metadata
3. proxies seller list request to resale orchestrator
4. proxies seller unlist request through inventory updates
5. proxies buyer purchase request to resale orchestrator
6. exposes health

### [services/concert_cancellation/src/app.py](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/services/concert_cancellation/src/app.py)

Purpose:

- orchestrates concert cancellation and refund workflow

Step flow:

1. receives cancellation request for a concert
2. marks concert as cancelled in concert service
3. asks inventory to queue all eligible tickets for refund
4. asks QR service to invalidate all QRs for the concert
5. fetches payment history for the concert
6. keeps the latest successful purchase-side payment per ticket
7. calls payment refund endpoint for those selected payments
8. marks refunded tickets in inventory
9. publishes cancellation/refund notifications
10. returns summary of affected records

## 6. Shared RabbitMQ Publishers

### [services/queue/src/amqp_publisher.py](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/services/queue/src/amqp_publisher.py)
### [services/purchase_window/src/amqp_publisher.py](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/services/purchase_window/src/amqp_publisher.py)
### [services/resale_purchase/src/amqp_publisher.py](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/services/resale_purchase/src/amqp_publisher.py)
### [services/concert_cancellation/src/amqp_publisher.py](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/services/concert_cancellation/src/amqp_publisher.py)
### [services/notification/src/amqp_publisher.py](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/services/notification/src/amqp_publisher.py)

Purpose:

- small helper modules that publish JSON payloads to RabbitMQ

Step flow:

1. open RabbitMQ connection using env vars
2. declare the configured topic exchange
3. publish payload using routing key
4. close connection cleanly

## 7. Database Seed Files

### [database/seeds/pricing_db.sql](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/database/seeds/pricing_db.sql)

Purpose:

- seeds the pricing database schema and demo rules

### [database/seeds/ticket_inventory_db.sql](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/database/seeds/ticket_inventory_db.sql)

Purpose:

- seeds inventory ticket rows for local ticket-based seat availability

### [database/seeds/payment_db.sql](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/database/seeds/payment_db.sql)

Purpose:

- seeds the payment database schema and sample payment records

### [database/seeds/qr_db.sql](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/database/seeds/qr_db.sql)

Purpose:

- seeds QR-related records

### [database/seeds/queue_db.sql](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/database/seeds/queue_db.sql)

Purpose:

- seeds queue-related schema/data

### [database/seeds/notification_db.sql](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/database/seeds/notification_db.sql)

Purpose:

- seeds contact and notification schema/data

## 8. Infrastructure Config

### [infra/kong/kong.yml](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/infra/kong/kong.yml)

Purpose:

- defines gateway routes from browser-facing URLs to internal services

Step flow:

1. maps `/pricing/v1` to pricing service
2. maps `/queue/v1` to queue service
3. maps `/tickets/v1` to inventory service
4. maps `/payment/v1` to payment service
5. maps `/qr/v1` to QR service
6. maps `/purchase/v1` to purchase orchestrator
7. maps `/resale/v1` and `/resale-ticket/v1` to resale services
8. maps `/cancellation/v1` to cancellation service

### [infra/rabbitmq/rabbitmq.conf](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/infra/rabbitmq/rabbitmq.conf)

Purpose:

- RabbitMQ runtime configuration

### [infra/rabbitmq/definitions.json](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/infra/rabbitmq/definitions.json)

Purpose:

- preload exchange, queues, and bindings

## 9. Supporting Docs And Diagrams

### [services/payment/README.md](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/services/payment/README.md)

Purpose:

- payment-service-specific documentation
- explains Stripe test mode and Stripe Connect resale routing

### [services/concert/README.md](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/services/concert/README.md)

Purpose:

- documents the external OutSystems concert service contract

### [USECASE_2_RESALE_TICKETING.md](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/USECASE_2_RESALE_TICKETING.md)
### [USECASE_2_TEMPLATE_SEGMENTS.md](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/USECASE_2_TEMPLATE_SEGMENTS.md)
### [BRANCH_COMPARISON_MAIN_VS_FUNCTIONAL_CHANGES.md](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/BRANCH_COMPARISON_MAIN_VS_FUNCTIONAL_CHANGES.md)
### [BRANCH_COMPARISON_TABLE_MAIN_VS_FUNCTIONAL_CHANGES.md](/c:/Users/Matth/Documents/IS213/concert-ticketing-platform/BRANCH_COMPARISON_TABLE_MAIN_VS_FUNCTIONAL_CHANGES.md)

Purpose:

- project analysis, comparison, and use-case notes

## 10. End-to-End Function Mapping

### Browse concert

1. `index.html` calls `API.concerts.list()`
2. concert data comes from OutSystems
3. local ticket counts are added through `API.tickets.summary(...)`
4. lineup cards are rendered

### Join queue

1. `concert-detail.html` loads categories from local inventory
2. customer chooses category
3. page redirects to `queue.html`
4. queue service grants or delays purchase window

### Primary purchase

1. `seat-select.html` loads available seats from local inventory
2. user selects seat and enters demo payment/contact data
3. `purchase_window` locks ticket
4. `payment` charges buyer
5. `qr` generates QR
6. ticket becomes `CONFIRMED`

### Resale listing

1. `my-tickets.html` opens resale modal
2. `resale_ticket` proxies listing request
3. `resale_purchase` validates ownership/policy/price cap
4. inventory ticket becomes `RESALE_LISTED`

### Resale purchase

1. `resale.html` shows marketplace listing
2. buyer confirms purchase
3. `resale_ticket` proxies purchase
4. `resale_purchase` moves ticket to `RESALE_PENDING`
5. `payment` creates Stripe Connect destination charge
6. seller QR is invalidated
7. buyer becomes owner and gets new QR
8. ticket returns to `CONFIRMED`

### Concert cancellation

1. admin triggers cancellation in `admin.html`
2. `concert_cancellation` updates concert status
3. inventory queues tickets for refund
4. payment service refunds latest effective purchase per ticket
5. QR service invalidates QRs
6. notifications are published

## 11. What Is Local Vs External

### External

- concert records
- seat category master definitions
- admin concert create/update at the concert-service level

### Local

- ticket rows
- seat availability on lineup/detail/admin list
- queue sessions
- payment records
- QR records
- resale listing state
- notification preferences and logs

## 12. Recommended Use

If you are explaining the system live, use this order:

1. root README
2. `api.js`
3. lineup and concert detail pages
4. queue and purchase flow
5. resale flow
6. cancellation flow
7. Kong and RabbitMQ config

