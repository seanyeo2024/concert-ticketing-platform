# Concert Ticketing Platform Comparison

## Scope

This document compares the current `functional-changes` branch against `main` in the concert-ticketing-platform repository.

It reflects the branch content plus the current working-tree frontend refinement that is not yet committed, so it matches the version currently being tested in the editor.

## Executive Summary

The `functional-changes` branch extends the platform in three major ways:

1. It introduces a full resale marketplace gateway and strengthens the resale purchase flow.
2. It hardens the primary checkout, pricing, payment, queue, and cancellation flows with stronger validation and rollback behavior.
3. It redesigns the frontend ticket views so ticket lifecycle states have visible business meaning instead of decorative styling.

At the infrastructure level, the branch also normalizes service ports, adds missing database seed scripts, and updates the API client and deployment stack to point at the new service layout.

## Platform Infrastructure And Deployment

### What changed

- The whole stack was aligned from the older `5100-5112` service range to the current `5000-5013` range.
- RabbitMQ management was moved to `15673` and notification MySQL was moved to `3307`.
- The environment file now includes `RESALE_TICKET_PORT`, `RABBITMQ_HOST_PORT`, and `RABBITMQ_MGMT_HOST_PORT` for the new deployment layout.
- `docker-compose.yml` now includes the new `resale_ticket` service.
- New seed scripts were added for `queue_db`, `payment_db`, `qr_db`, and `notification_db`.
- `README.md` was updated to reflect the new ports, health checks, and the resale gateway endpoints.

### Why it matters

- The branch is no longer just a feature branch; it is a reorganized deployment profile.
- The new seed files make the support databases boot consistently with schema and sample records.
- The updated compose topology makes the resale marketplace a first-class service instead of a frontend-only concept.

## Concert Management And Pricing

### Concert service

- `services/concert/src/app.py` no longer stores `basePrice` in the concert seat-category schema.
- The schema migration code that added `basePrice` dynamically was removed.

### Meaning of the change

- Pricing responsibility has been separated from concert metadata.
- Concert service now focuses on event and seat-category structure, while pricing service owns face-value and resale ceilings.

### Pricing service

- `services/pricing/src/app.py` now validates `basePrice` and `resaleCeiling` more strictly.
- `basePrice` must be numeric, non-negative, and capped.
- `resaleCeiling` must be numeric, must be at least `basePrice`, and is also capped.

### Business value

- This strengthens the resale policy by preventing invalid pricing rules from entering the system.
- It also supports the “no scalping” business story more credibly because the ceiling is enforced at the service layer.

## Queue And Purchase Window

### Queue service

- `services/queue/src/app.py` now parses `MAX_ACTIVE_WINDOWS` more safely.
- Queue depth responses now return a richer breakdown with:
  - total queue depth
  - waiting count
  - active window count
  - raw status breakdown

### Purchase window service

- `services/purchase_window/src/app.py` now rolls back ticket locks if payment fails or times out.
- It distinguishes timeout and generic request errors instead of collapsing everything into one payment failure.
- Ticket confirmation after successful payment is now treated as non-critical, with a warning instead of a hard stop.

### Business value

- The waiting-room and purchase-window flow is more robust under service failure.
- Users are less likely to get stuck with a locked ticket if payment or orchestration fails mid-flow.

## Payments And Refunds

### Payment service

- `services/payment/src/app.py` now validates payment and refund amounts more carefully.
- Amounts are parsed as numbers, checked for positivity, and capped.
- The service now uses the parsed numeric amount consistently when saving records and calling the Stripe stub.

### Why it matters

- This avoids invalid string-based amounts and reduces the risk of bad records.
- It also makes the payment layer safer for both normal purchases and resale purchases.

## Ticket Inventory And Lifecycle Rules

### Ticket inventory service

- `services/ticket_inventory/src/app.py` now validates `purchasePrice` and `resalePrice` before writing updates.
- Negative values and non-numeric values are rejected.

### Why it matters

- Ticket state transitions are now protected by more realistic business validation.
- This supports the resale policy and prevents malformed price data from leaking into the inventory layer.

## Cancellation And Refund Handling

### Concert cancellation service

- `services/concert_cancellation/src/app.py` now returns clearer errors when the concert cannot be cancelled.
- A missing concert now surfaces as a 404.
- Upstream rejection messages are propagated when the Concert service explains why the cancellation failed.

### Business value

- Admins get clearer failure feedback.
- Refund and cancellation handling is easier to debug and explain in a demo.

## Resale Marketplace

### New composite microservice

#### `services/resale_ticket/` - Composite

- This is the new marketplace gateway for resale operations.
- It exposes browse, list, unlist, and purchase endpoints for the resale market.
- It delegates listing and purchasing to `resale_purchase` for consistency, while enriching listing results with pricing ceiling information.

#### Responsibilities

- Browse resale listings by concert.
- Seller list ticket.
- Seller unlist ticket.
- Buyer purchase resale ticket.

### Existing resale orchestration

- `services/resale_purchase/src/app.py` gained a reusable buyer QR generation helper.
- Listing a ticket now checks whether the ticket has already been resold once.
- If a successful `RESALE_PURCHASE` already exists for that ticket, the listing is rejected.
- Purchase flow now:
  - validates the resale price ceiling more defensively,
  - invalidates the seller’s QR and reports whether that succeeded,
  - retries ticket confirmation if a version conflict occurs,
  - generates and returns the buyer QR more cleanly,
  - exposes additional response fields for the frontend.

### Business value

- The resale flow now enforces the rule that a ticket can only be resold once.
- The gateway/service split makes the resale feature easier to demo and explain.
- The returned QR and invalidation status make the transfer experience more transparent.

## Frontend Marketplace Experience

### Resale page

- `frontend/pages/resale.html` now loads resale listings through the new `resaleTicket` API client.
- A disclaimer modal appears before checkout so buyers explicitly acknowledge resale policy.
- The success modal now shows QR-related state more clearly.
- Listings now disable buying your own listing in the UI.

### My Tickets page

- `frontend/pages/my-tickets.html` no longer uses decorative random colors.
- Ticket colors now represent business meaning:
  - primary purchase and resale-eligible
  - resale-bought and resale-locked
  - listed on resale market
  - pending transaction
  - cancelled by organizer
  - closed lifecycle such as used or refunded history
- A policy legend explains the meaning of each color.
- Resale-bought tickets are marked as resale-locked only in the buyer’s active Upcoming view.
- Seller payout history in the Refunded tab keeps the “Resale payout received” note without showing the resale-lock badge.
- Cancelled concert tickets are now clearly shown as cancelled and inactive instead of blending into generic refunded history.

### Frontend API layer

- `frontend/assets/js/api.js` was updated to the new port map.
- It now includes a dedicated `resaleTicket` client for marketplace operations.
- The old resale calls are routed through the new marketplace gateway.

### Business value

- The frontend now tells the same story as the backend.
- Colour, legend, labels, and disabled actions are all tied to policy instead of decoration.
- The resale lock is visible where it matters most: the buyer’s active ticket, not the seller’s payout history.

## Documentation And Deliverables

### New branch-specific documents

- `USECASE_2_RESALE_TICKETING.md` was added as a detailed resale-ticketing design and flow document.
- `USECASE_2_TEMPLATE_SEGMENTS.md` was added as a supporting template/segment document.

### Updated README

- The README now documents the new service ports, the resale gateway, the updated health URLs, and the environment variables needed to run the stack.

## Extra Microservices

### Newly added microservice

- `services/resale_ticket/` - Composite microservice
  - Role: resale marketplace gateway
  - Endpoints: browse listings, list ticket, unlist ticket, purchase ticket
  - Composition: delegates to `ticket_inventory`, `pricing`, and `resale_purchase`

### Existing services that were strengthened

- `services/resale_purchase/` - Composite
- `services/purchase_window/` - Composite
- `services/concert_cancellation/` - Composite
- `services/concert/` - Atomic
- `services/pricing/` - Atomic
- `services/queue/` - Atomic
- `services/payment/` - Atomic
- `services/ticket_inventory/` - Atomic

### Note

- No new atomic microservice was added in this branch.
- The main structural addition is the new composite `resale_ticket` gateway.

## Bottom Line

Compared with `main`, this branch moves the platform from a basic ticketing demo into a more complete resale-aware ticketing system with stronger lifecycle rules, clearer UI policy signaling, and more resilient backend orchestration.