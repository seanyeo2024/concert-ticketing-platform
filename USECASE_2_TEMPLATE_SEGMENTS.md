# Use Case #2: Resale Ticketing — Template Segments

Copy and paste these sections directly into your report.

---

## [Write-up of this user scenario(s) with reference to the Microservice Interaction Diagram(s).]

### Scenario Overview
The resale ticketing system enables secondary market transactions, allowing ticket owners to list unwanted tickets at market-determined prices (subject to regulatory ceilings) and buyers to purchase resale tickets with transactional consistency across multiple microservices.

---

### Figure 2a — Seller Lists Resale Ticket

**Seller uses UI to list a resale ticket.** The seller navigates to "My Tickets" page and selects a CONFIRMED ticket they wish to resale. The UI invokes the Resale Ticket Gateway via [GET] /resale-ticket/v1/listings/{concertId}/ceiling to retrieve the resale price ceiling for the ticket's category (e.g., CAT-C001-01: ceiling $580 SGD). The Resale Ticket Gateway queries the Pricing service, which returns the maximum price the seller may list at.

**UI displays the ceiling and seller enters a resale price.** The seller enters their asking price (e.g., $420) within the ceiling constraint. The UI then invokes the Resale Ticket Gateway via [POST] /resale-ticket/v1/list with the ticket ID, concert ID, resale price, and ticket version (for optimistic locking).

**Resale Ticket Gateway validates and transfers ticket state.** The gateway invokes the Ticket Inventory service via [PUT] /tickets/v1/tickets/{concertId}/{ticketId} to transition the ticket status from CONFIRMED → RESALE_LISTED and store the resale price. Ticket Inventory updates the ticket's state and returns the updated ticket object with incremented version number.

**Resale Ticket Gateway confirms listing to seller UI.** Upon success, the gateway returns confirmation to the seller UI showing ticket is now listed at $420. The seller's ticket now appears in the resale marketplace with purchase-ready status.

---

### Figure 2b — Buyer Purchases Resale Ticket

**Buyer browses resale marketplace.** The buyer navigates to the Resale page and invokes the Resale Ticket Gateway via [GET] /resale-ticket/v1/listings/{concertId}. The gateway queries the Ticket Inventory service to retrieve all tickets with status = RESALE_LISTED, then enriches each listing with pricing metadata (resale ceiling, currency) from the Pricing service. The marketplace displays all available resale listings with seat location, resale price, and seller details.

**Buyer selects a listing and initiates purchase.** The buyer clicks "Buy Now" on a specific listing (e.g., seat L-05-13 for $420). The UI invokes the Resale Purchase Orchestrator (composite microservice) via [POST] /resale/v1/purchase with the concert ID, ticket ID, buyer ID, resale price, and buyer's Stripe customer ID.

**Resale Purchase Orchestrator validates and coordinates transaction.** The orchestrator performs the following sequence:

1. **Validates Pricing**: Invokes Pricing service via [GET] /pricing/v1/concerts/{concertId}/prices/{categoryId}/ceiling to confirm resale price does not exceed ceiling. If price valid, continues; otherwise aborts.

2. **Processes Payment**: Invokes Payment service via [POST] /payment/v1/payment with buyer ID, ticket ID, type='RESALE_PURCHASE', and amount=$420. The Payment service charges the buyer via Stripe and returns a payment ID. If charge fails (insufficient funds, card declined), transaction aborts and ticket remains listed.

3. **Generates Buyer QR Code**: Invokes QR service via [POST] /qr/v1/qr with ticket ID, concert ID, buyer ID, and type='ENTRY'. The QR service generates a unique QR code for the buyer with embedded entry permission. If QR generation fails, the orchestrator retries up to 3 times with exponential backoff (1s, 2s, 4s). If still fails after retries, transaction aborts.

4. **Transfers Ticket Ownership**: Invokes Ticket Inventory service via [PUT] /tickets/v1/tickets/{concertId}/{ticketId} to transition ticket ownership from seller → buyer and update ticket state:
   - `ownerId = buyer_id` (buyer now owns ticket)
   - `purchasePrice = 420` (buyer's cost basis is the resale price, not original face value)
   - `status = CONFIRMED` (ticket ready to use)
   - `qrId = new_qr_id` (buyer's QR code ID)
   - Incremented `version` (optimistic locking)
   
   Ticket Inventory uses version-based optimistic locking: if version mismatch detected (concurrent update), returns HTTP 409 Conflict. The orchestrator detects conflict, fetches fresh ticket state, and retries transfer (up to 3 attempts total).

5. **Invalidates Seller's QR Code**: Invokes QR service via [DELETE] /qr/v1/qr/{oldQrId} to revoke the seller's original QR code. The seller can no longer scan for venue entry.

6. **Records Seller Payout**: Payment service automatically creates a RESALE_PAYOUT record for the seller with amount=$420 and type='RESALE_PAYOUT', enabling seller to see earnings in their payment history.

**Resale Purchase Orchestrator returns transaction confirmation.** The orchestrator returns success response to buyer UI with:
- Payment ID (receipt reference)
- New QR code (SVG data)
- Confirmation that seller's QR invalidated
- Message: "Purchase complete. Your ticket is ready."

**Frontend redirects to My Tickets with sync context.** The buyer UI displays success modal showing the new QR code, then auto-redirects to My Tickets page with URL parameters: `?refreshConcert={concertId}&refreshTicket={ticketId}&owner={buyerId}`. These parameters signal the My Tickets page to poll for the transferred ticket.

**My Tickets page syncs transferred ticket.** Upon loading with refresh parameters, the My Tickets page executes `syncTransferredTicket()` function which polls the Ticket Inventory service via [GET] /tickets/v1/tickets/{concertId}/{ticketId} up to 8 times over a 4-second window (500ms poll interval). Polling stops when ticket ownership confirms `ownerId===buyerId` and `status===CONFIRMED`. Upon match, the transferred ticket is inserted into the buyer's ticket inventory and rendered in the "Upcoming" tab immediately. **Deterministic UX guarantee**: Buyer sees their newly purchased resale ticket within 4 seconds.

---

## External Services

| Service Name | Description of Functionality | Link to External Documentation |
|---|---|---|
| **Stripe Payment Processing** | Credit card and digital wallet charge authorization for resale purchases. Payment microservice invokes Stripe API endpoint `POST /v1/charges` with buyer's Stripe customer ID, charge amount (resale price in cents), and currency. Returns transaction status (succeeded/failed) and charge ID. On failure (insufficient funds, card declined, expired card), returns HTTP 402 and transaction aborts without charging buyer. | [Stripe Charges API Documentation](https://stripe.com/docs/api/charges) |
| **RabbitMQ Message Broker** | Asynchronous event publishing for notifications. Resale Purchase Orchestrator publishes events to topic exchange `concert-ticketing.events` with routing keys `ticket.resale_purchase`, `ticket.resale_payout`, etc. Notification microservice subscribes to `*.notify` binding key and sends email/SMS confirmations to buyer and seller. Durable message queue ensures events are not lost if Notification service temporarily unavailable. | [RabbitMQ Topic Exchanges Documentation](https://www.rabbitmq.com/tutorials/tutorial-five-python.html) |

---

## Beyond the Labs

### 1. Distributed Optimistic Locking with Automatic Retry

**What It Is**: Ticket Inventory implements version-based optimistic locking so that concurrent resale purchase attempts don't double-sell the same ticket. Each ticket state includes a `version` number; when transferring ownership, the Resale Purchase Orchestrator increments version and includes it in the update request. If version doesn't match (another process updated ticket concurrently), Ticket Inventory returns HTTP 409 Conflict. The orchestrator then retries up to 3 times, fetching fresh ticket state each time, until successful.

**Why It Matters**: Without this, two buyers could race to purchase the same resale ticket simultaneously, causing data corruption or double-charging. Pessimistic locking (holding locks on entire ticket table) would block all concurrent operations and severely reduce throughput. Optimistic locking allows concurrent reads with automatic conflict detection and retry—the hallmark of scalable microservice architectures.

**Lab Extension**: Standard ESD labs teach ACID transactions within a single database; this extends to multi-service transactions with conflict resolution patterns not traditionally covered in foundational coursework. Multi-version concurrency control (MVCC) is taught in advanced database courses but rarely implemented in microservice contexts.

---

### 2. Graceful Degradation in Composite Orchestrators

**What It Is**: The Resale Purchase Orchestrator wraps external service calls (particularly Pricing service) in try/except blocks. If Pricing service is unavailable or returns an error, instead of crashing with HTTP 500, the orchestrator assumes a conservative fallback (e.g., ceiling price is sufficiently high) and continues processing the transaction. This prevents cascade failures where one downed service blocks an entire workflow.

**Why It Matters**: In production, services fail. Hardware fails, networks partition, deployments break. Financial transactions (payments) are too critical to abort on auxiliary service failures (pricing validation). Graceful degradation acknowledges this reality and provides fallback logic to maintain availability even when some dependencies degrade. The classic pattern is the Circuit Breaker, but this lightweight approach (fallback + retry) is pragmatic for non-critical dependencies.

**Lab Extension**: Labs typically assume all services are always available (idealized environment). Real production systems must handle partial failures, cascade failures, and network partitions. Netflix's Hystrix library and modern frameworks teach these patterns, but implementing fallback logic by hand (as shown here) demonstrates deep understanding of resilience principles.

---

### 3. Exponential Backoff Retry for External Service Calls

**What It Is**: When invoking the QR service to generate a new QR code for the buyer, if the call fails with a transient error (network hiccup, brief service overload), the Resale Purchase Orchestrator retries automatically with exponential backoff: 1st attempt immediately, 2nd attempt after 1 second, 3rd attempt after 2 seconds, 4th attempt after 4 seconds. Each delay increases exponentially. If all retries exhausted, the transaction aborts.

**Why It Matters**: Transient failures (brief network glitches) are common. Retrying immediately often succeeds. Exponential backoff prevents "thundering herd" where many clients retry simultaneously, overwhelming a recovering service. This is industry-standard practice in distributed systems (Amazon Web Services SDKs, Google Cloud libraries all implement exponential backoff by default).

**Lab Extension**: Labs teach basic request-response patterns; they don't typically cover failure modes and recovery strategies. Implementing retry logic with exponential backoff is expected in production systems but rarely taught in foundational coursework.

---

### 4. Deterministic Frontend Sync Polling with Time-Bounded Guarantee

**What It Is**: After a buyer completes a resale purchase, the frontend redirects to My Tickets page with special URL parameters (`?refreshConcert=...&refreshTicket=...&owner=...`). The My Tickets page executes a `syncTransferredTicket()` function that polls the backend API every 500ms, checking if the transferred ticket now appears under the buyer's ownership. Polling runs for up to 4 seconds (8 attempts), with deterministic guarantee: "If backend write succeeds and network communication succeeds, buyer sees their new ticket within 4 seconds."

**Why It Matters**: Microservices store data in separate databases (ticket_inventory_db, payment_db, etc.). After a distributed transaction completes, data propagation through the system takes time (milliseconds to seconds). Without sync polling, buyer might see blank ticket list for several seconds after purchase, creating poor UX. Sync polling bridges the gap between "transaction completed" and "UI reflects latest data."

**Lab Extension**: Labs teach request-response in single-threaded scenarios; they don't typically cover distributed data synchronization. Polling with time bounds is a pragmatic pattern for eventual consistency systems. More sophisticated implementations use WebSockets, Server-Sent Events, or CQRS pattern (separate read/write models), but simple polling is the most straightforward introduction to this concept.

---

### 5. API Gateway Pattern for Multi-Service Aggregation

**What It Is**: The Resale Ticket Gateway service (port 5013) provides a user-facing API that aggregates data from multiple atomic services. For example, [GET] /resale-ticket/v1/listings/{concertId} internally calls:
1. Ticket Inventory service to fetch all RESALE_LISTED tickets
2. Pricing service to fetch ceiling prices for each ticket's category

The gateway then stitches responses together and returns a single response to the frontend with ticket + pricing metadata in one call. Without this gateway, frontend would need to chain N+1 API calls (one per ticket), creating chattiness and poor UX.

**Why It Is Matters**: The API Gateway pattern is foundational to microservices architecture. It prevents frontend from depending on internal service structure; provides a stable API contract; enables composition of atomic services into higher-level operations. This is taught in advanced architecture courses and is standard in production microservices (Netflix API Gateway, AWS API Gateway, Kong).

**Lab Extension**: Labs teach point-to-point communication between frontend and one service; they rarely show how to aggregate multiple services into a cohesive user-facing API. This is where microservices architecture becomes pragmatic.

---

### 6. Payment Type Discrimination for Dual-Actor Workflows

**What It Is**: When a buyer purchases a resale ticket, the Payment service records two separate payment records:
1. `RESALE_PURCHASE`: $420 deducted from buyer (type = RESALE_PURCHASE)
2. `RESALE_PAYOUT`: $420 credited to seller (type = RESALE_PAYOUT)

Both records exist in payment_db.payments table but with different `type` field. The My Tickets page filters payments by type: it shows seller payouts (type=RESALE_PAYOUT) in the "Refunded" tab, allowing sellers to see their earnings without a separate ledger system.

**Why It Matters**: Payment records serve as source of truth for financial transactions. Using payment type discrimination (instead of separate ledger or eventual consistency via message queues) keeps the payment service simple and the data model normalized. This is pragmatic financial system design: one record per transaction, but transactions can be viewed from different actors' perspectives (buyer vs. seller).

**Lab Extension**: Labs teach transaction isolation and ACID properties; they don't typically show how payment systems handle multiple actor types (buyer, seller, platform) or how to achieve meaningful financial reporting from a single table via filtering/aggregation.

---

### 7. Explicit Metrics Aggregation for Admin Dashboards

**What It Is**: The Queue service provides a [GET] /queue/v1/queue/{concertId} endpoint that returns explicit aggregate metrics:
```json
{
  "queueDepth": 10,           // Total number of people in queue
  "waitingCount": 7,          // Actively waiting
  "windowGrantedCount": 3,    // Allowed to purchase now
  "breakdown": [...]          // Detailed breakdown by status
}
```

Instead of just returning the breakdown array, the service also computes and returns aggregate totals. This enables admin dashboard to display key metrics (e.g., "3 waiting, 1 buying, 6 sold") in a single glance without client-side computation.

**Why It Matters**: Admin dashboards need real-time visibility into system state. Returning explicit aggregates ensures consistency between what dashboard reports and what database contains (no client-side math errors). For high-frequency dashboards, pre-computing aggregates in the service (not client) avoids O(N) computation on frontend.

**Lab Extension**: Labs teach basic aggregation (COUNT, SUM, GROUP BY); they don't show how microservices should expose aggregates in REST endpoints for real-time monitoring. This is operational observability in action.

---

### 8. Upstream Error Propagation Instead of Generic Failure Messages

**What It Is**: When Concert Cancellation service encounters an error (e.g., Refund service unreachable), instead of returning generic `{"error": "Cancellation failed"}`, it returns:
```json
{
  "error": "Refund failed: Connection timeout to Payment service",
  "upstream_service": "payment",
  "concert_id": "CONC-000001",
  "status": 500
}
```

The upstream service name and error details are propagated to the caller. This aids debugging: developers immediately know which service failed and why.

**Why It Matters**: Production debugging requires detailed error context. Generic failure messages are useless for troubleshooting. By propagating upstream errors, each microservice becomes more transparent, and the system as a whole is easier to debug.

**Lab Extension**: Labs teach error handling at service boundaries but typically use simple error codes or generic messages. Production systems must preserve error context through the call chain (similar to stack traces in monoliths, but distributed).

---

### 9. Infrastructure-as-Code: Database Seeding for Reproducible Initialization

**What It Is**: Each microservice is shipped with SQL seed files (database/seeds/queue_db.sql, payment_db.sql, qr_db.sql, notification_db.sql) that define complete database schema + sample data. Docker Compose executes these scripts on container startup:
```yaml
queue_db:
  image: mysql:8.0
  volumes:
    - ./database/seeds/queue_db.sql:/docker-entrypoint-initdb.d/init.sql
```

New developers simply run `docker compose up -d` and wait 30 seconds; all databases are initialized with realistic test data.

**Why It Matters**: Reproducible environments are crucial for team collaboration. Without seed files, new developers must manually create schemas, insert test data, and debug mismatches. Seed files codify the expected database state and enable one-command environment setup.

**Lab Extension**: Labs run services manually or with minimal automation. Production practices use Infrastructure-as-Code (Terraform, CloudFormation, docker-compose) to ensure consistency. This project demonstrates IaC principles applied to local development.

---

### 10. Frontend API Client with Graceful Fallback to Seed Data

**What It Is**: The frontend API client (frontend/assets/js/api.js) includes comprehensive SEED data that mirrors production schemas. Every API call is wrapped in try/catch; if the backend is unavailable, the call falls back to SEED data:
```javascript
concerts: {
  list: async () => { 
    try { 
      return await req(`${BASE.concert}/concerts`); 
    } catch { 
      return { concerts: SEED.concerts };  // Fallback to offline data
    } 
  },
}
```

This enables the frontend to remain fully functional for UI testing / product demos even if backend services are down.

**Why It Matters**: Frontend development/testing shouldn't be blocked by backend unavailability. Fallback seed data enables designers and frontend engineers to work independently. Product demos can run offline. This is a pragmatic development practice for large teams.

**Lab Extension**: Labs teach client-server communication in success cases; they don't typically cover offline-first strategies or fallback mechanisms. Modern frontend practices (particularly mobile apps and progressive web apps) require this thinking.

---

### 11. Comprehensive Historical Reconciliation for Financial Data Consistency

**What It Is**: After deploying the fix that ensures `purchasePrice = resalePrice` in ticket ownership transfers, a one-time PowerShell reconciliation script was executed to validate and correct any historical tickets where the fix wasn't applied. The script:
1. Fetches all concerts
2. For each concert, fetches all tickets and recent RESALE_PURCHASE payments
3. For each resale ticket, checks if purchasePrice matches the resale amount paid
4. If mismatch and ticket is owned by the buyer who paid → updates purchasePrice
5. Logs every action with reason (updated, skipped, validation failure)
6. Provides audit trail for compliance/financial review

**Why It Matters**: Financial systems must be consistent. Historical data (even pre-fix transactions) must eventually be corrected to maintain accuracy for billing, refunds, and audits. Reconciliation scripts are standard practice in financial systems (banks, payment processors, accounting platforms all run regular reconciliation).

**Lab Extension**: Labs teach correct implementations going forward; they don't teach how to remediate historical data after bugs are discovered. Production financial systems require discipline around data consistency and comprehensive reconciliation practices. This demonstrates professional-grade thinking about data integrity.

---

## Summary

The Resale Ticketing microservice implementation combines foundational ESD concepts (microservices, service coordination, databases) with production-grade resilience patterns (graceful degradation, retry logic, distributed locking, sync polling) and operational practices (seeding, reconciliation, error propagation). Collectively, these techniques demonstrate how microservices are built and operated at enterprise scale.
