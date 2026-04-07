# Concert Ticketing Platform Branch Comparison (Table Version)

## 1) High-Level Summary

| Area | What Changed In functional-changes vs main | Why It Matters |
|---|---|---|
| Resale architecture | Added a new resale marketplace gateway service and integrated it into frontend/backend flows. | Creates a clearer service boundary and more complete resale user journey. |
| Core transaction hardening | Added stronger validation, rollback handling, and defensive error handling in key orchestration paths. | Reduces inconsistent states during payment/checkout failures. |
| Ticket lifecycle UX | Reworked ticket card policy indicators and resale-lock behavior in My Tickets. | Makes business rules explicit to users and assessors during demo. |
| Deployment profile | Ports, compose wiring, seed scripts, and README were updated to a new baseline. | Improves reproducibility and environment consistency. |

## 2) Extra Microservices (Explicit)

| Service | New/Existing | Type | Branch Status | Purpose |
|---|---|---|---|---|
| services/resale_ticket | New | Composite | Added in functional-changes | Resale marketplace gateway for listings, list/unlist, and purchase endpoints. |
| services/resale_purchase | Existing | Composite | Strengthened | Enforces one-time resale rule and improved purchase transfer flow. |
| services/purchase_window | Existing | Composite | Strengthened | Improved rollback and payment error handling for primary checkout. |
| services/concert_cancellation | Existing | Composite | Strengthened | Better cancellation error propagation and not-found handling. |
| services/concert | Existing | Atomic | Adjusted | Removed seat-category basePrice ownership from concert schema. |
| services/pricing | Existing | Atomic | Strengthened | Stricter basePrice/resaleCeiling numeric validation and caps. |
| services/queue | Existing | Atomic | Strengthened | Safer MAX_ACTIVE_WINDOWS parsing and richer queue depth output. |
| services/payment | Existing | Atomic | Strengthened | Stronger amount parsing/validation for payments and refunds. |
| services/ticket_inventory | Existing | Atomic | Strengthened | Numeric validation for purchasePrice and resalePrice updates. |

## 3) Infrastructure And DevOps Changes

| File(s) | Change Category | Exact Difference | Impact |
|---|---|---|---|
| docker-compose.yml | Service topology | Added resale_ticket service wiring. | Enables new resale gateway in runtime stack. |
| docker-compose.yml | Database bootstrapping | Added seed mounts for queue_db, payment_db, qr_db, notification_db. | Ensures missing schemas are created consistently. |
| docker-compose.yml | Port mapping | Notification DB host port changed to 3307. | Avoids conflict and aligns docs/runtime. |
| README.md, frontend/assets/js/api.js, .env semantics | Port baseline normalization | Shifted old 5100-5112 style ports to 5000-5013 mapping. | Unified endpoint expectations across docs/frontend/services. |
| README.md | Runtime docs | Added resale gateway health/endpoint documentation and updated RabbitMQ UI port usage. | Improves onboarding and troubleshooting. |

## 4) Database Seed Additions

| Seed File | Status vs main | What It Adds | Service Supported |
|---|---|---|---|
| database/seeds/queue_db.sql | New | queue_entry schema bootstrap for queue runtime state. | queue (Atomic) |
| database/seeds/payment_db.sql | New | payment_record schema + sample transactions. | payment (Atomic) |
| database/seeds/qr_db.sql | New | qr_record schema + sample QR records. | qr (Atomic) |
| database/seeds/notification_db.sql | New | notification_log schema + sample notifications. | notification (Atomic) |

## 5) Backend Service Logic Changes

| Service File | Feature Area | Change In functional-changes | Business Rule / Reliability Effect |
|---|---|---|---|
| services/resale_ticket/src/app.py | Resale marketplace | New gateway endpoints for listings, seller list/unlist, buyer purchase; listing enrichment with pricing ceiling. | Centralized marketplace interface and cleaner API contract. |
| services/resale_purchase/src/app.py | Resale listing policy | On listing, checks payments to block any ticket already successfully resold once. | Enforces one-time resale policy server-side. |
| services/resale_purchase/src/app.py | Resale transfer flow | Added seller QR invalidation status, buyer QR helper/retries, confirm retry logic, richer success payload. | Safer ownership transfer and stronger frontend observability. |
| services/purchase_window/src/app.py | Primary checkout | Added payment timeout/request exception handling and rollback behavior. | Prevents stuck pending locks after payment-side failures. |
| services/payment/src/app.py | Payment validation | Amount parsing hardening, positive/cap checks for charge/refund flows. | Reduces malformed financial records and invalid values. |
| services/pricing/src/app.py | Pricing validation | Validates basePrice/resaleCeiling numeric correctness and bounds. | Strengthens anti-scalping ceiling governance. |
| services/ticket_inventory/src/app.py | Inventory integrity | Added numeric checks for purchasePrice/resalePrice updates. | Prevents bad pricing values in ticket lifecycle updates. |
| services/queue/src/app.py | Queue telemetry | More robust env parsing and richer queue depth response payload. | Better queue observability for frontend/admin UX. |
| services/concert_cancellation/src/app.py | Cancellation orchestration | Better upstream error mapping and 404 propagation from concert service. | Clearer operational feedback for failed cancellation attempts. |
| services/concert/src/app.py | Ownership boundary | Removed seat_category basePrice field and migration code. | Keeps pricing ownership in pricing service only. |

## 6) Frontend And UX Changes

| Frontend File | Feature | Difference vs main | User-Facing Outcome |
|---|---|---|---|
| frontend/assets/js/api.js | API integration | Added resaleTicket client and routed resale actions through gateway-compatible calls. | Frontend aligned with new resale service topology. |
| frontend/pages/resale.html | Buyer flow controls | Added pre-checkout disclaimer modal for resale policy acknowledgement. | Buyer explicitly accepts one-time resale limitation before checkout. |
| frontend/pages/resale.html | Listing interaction | Blocks self-buy action and improves listing action rendering. | Prevents accidental or invalid own-listing purchases in UI. |
| frontend/pages/resale.html | Purchase completion UX | Enhanced success state with QR transfer notes and QR readiness visibility. | Clearer confirmation after resale transfer. |
| frontend/pages/my-tickets.html | Policy visualization | Replaced decorative color rotation with policy-based color states + legend. | Colors now communicate lifecycle/business meaning. |
| frontend/pages/my-tickets.html | Resale ownership rule UX | Shows resale-lock cues only where appropriate for buyer side, keeps seller payout context clean. | Avoids misleading resale-lock messaging in refunded seller history. |
| frontend/pages/my-tickets.html | Refunded differentiation | Distinguishes cancelled-by-organizer inactive refunds from other refunded lifecycle states. | Better interpretation of refund reasons in demo/reporting. |

## 7) Documentation And Deliverables Added

| File | Status vs main | Purpose |
|---|---|---|
| USECASE_2_RESALE_TICKETING.md | New | Detailed use case documentation for resale ticketing logic and flows. |
| USECASE_2_TEMPLATE_SEGMENTS.md | New | Supporting template/segments artifact for use case delivery. |
| README.md | Modified | Updated runbook, ports, health checks, and resale gateway references. |

## 8) Net Change Snapshot

| Metric | Value |
|---|---|
| Files changed | 22 |
| Insertions | 2037 |
| Deletions | 134 |
| New microservices | 1 (Composite: services/resale_ticket) |
| New atomic microservices | 0 |

## 9) Copy-Paste Notes For Word

| Tip | Recommendation |
|---|---|
| Best paste mode | Paste as Keep Source Formatting or Merge Formatting. |
| If table borders disappear | In Word: select table, Table Design, apply a light grid style. |
| If you need shorter version | Keep sections 1, 2, 5, and 8 only for an executive report format. |
