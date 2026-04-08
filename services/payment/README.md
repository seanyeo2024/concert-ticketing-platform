# Payment Service

Atomic payment microservice for the concert ticketing platform.

## Purpose

This service handles:

- ticket purchase payments
- resale purchase payments
- refunds
- resale seller payout records
- payment record persistence in MySQL

It is designed for demo and test flows only. It uses a Stripe **test secret key** from the root `.env`, but the frontend does **not** use Stripe.js or real card tokenization.

## Port

- Container port: `5004`
- Host port: from `.env` -> `PAYMENT_PORT=5104`
- Local access through Docker Compose: `http://localhost:5104`
- Gateway access through Kong: `http://localhost:8000/payment/v1`

## Environment Variables

The service expects:

```env
MYSQL_HOST=mysql_payment
MYSQL_PORT=3306
MYSQL_DATABASE=payment_db
MYSQL_USER=ctms
MYSQL_PASSWORD=ctms
STRIPE_SECRET_KEY=sk_test_...
```

From the current project setup, `STRIPE_SECRET_KEY` is already defined in the root `.env`.

## Current Integration Mode

This project is **not** doing a real production payment integration.

Current behavior:

1. The frontend collects demo card input.
2. The frontend maps supported test card numbers to Stripe test payment method IDs.
3. The purchase flow sends that payment method ID to the backend as `stripeToken`.
4. This service creates a Stripe test `PaymentIntent`.
5. The result is saved into `payment_record`.

This keeps the existing purchase orchestration intact while still allowing test success and test failure scenarios.

## Payment Model

This project currently uses a platform-mediated settlement model.

### Primary ticket purchase

- the buyer pays the platform
- Stripe charges the buyer through the platform account
- the service records a `PURCHASE` payment

### Resale ticket purchase

- the new buyer pays the platform
- Stripe charges the buyer through the platform account
- the service records a `RESALE_PURCHASE` payment
- the platform then records a seller payout entry after the resale purchase succeeds

Important:

- this is **not** a real Stripe customer-to-customer transfer
- this is **not** Stripe Connect
- the seller-side payout is currently an internal platform settlement record for demo purposes

In other words:

- buyer -> platform is handled through Stripe test payments
- platform -> seller is currently represented by an internal payout record in `payment_record`

## Resale Settlement Flow

The resale path is:

1. buyer pays for the resale ticket
2. payment service creates a `RESALE_PURCHASE` payment
3. ownership transfer continues in the resale orchestration
4. payment service records a seller payout entry linked to that buyer payment

The seller payout record uses:

- `type='REFUND'`
- `reason='RESALE_PAYOUT'`

This keeps the existing UI and payment history logic working for demo use.

## Concert Cancellation Refund Behavior

Concert cancellation currently uses the Stripe-backed refund endpoint.

Current orchestration:

1. the concert is marked `CANCELLED`
2. eligible tickets are moved to `REFUNDED`
3. QR codes are invalidated
4. the cancellation service fetches all concert payments of type:
   - `PURCHASE`
   - `RESALE_PURCHASE`
5. the cancellation service selects the latest successful purchase per ticket
6. each selected payment record is sent to `POST /payment/v1/payment/refund`

Current refund-selection rule:

- one refund path is chosen per ticket
- for a resold ticket, the latest successful purchase is refunded
- in practice, that means the current effective holder path is refunded instead of every historical buyer

It does **not** refund the internal resale seller payout record, because the concert payment lookup excludes `REFUND` rows.

So the current cancellation behavior is:

- refund the latest successful purchase-side payment per ticket
- not every historical purchase for that ticket

This is a known limitation of the current demo approach and should be described as such in demos and API documentation.

## Supported Test Cards

On the seat selection page:

- `4242 4242 4242 4242` -> success
- `4000 0000 0000 9995` -> insufficient funds
- `4000 0000 0000 0002` -> card declined

The backend maps these to Stripe test payment method IDs such as:

- `pm_card_visa`
- `pm_card_insufficientFunds`
- `pm_card_chargeDeclined`

## API Endpoints

### Health

- `GET /health`

Example response:

```json
{
  "status": "ok",
  "service": "payment",
  "stripeConfigured": true
}
```

### Config

- `GET /payment/v1/config`

Returns service mode and whether Stripe is configured.

### Create Payment

- `POST /payment/v1/payment`

Example request:

```json
{
  "userId": "USR-0042",
  "ticketId": "TKT-10003",
  "concertId": "CONC-000001",
  "amount": 388.00,
  "currency": "SGD",
  "type": "PURCHASE",
  "stripeToken": "pm_card_visa"
}
```

Example success response:

```json
{
  "paymentId": "PAY-AB12CD34",
  "status": "SUCCESS",
  "stripePaymentIntentId": "pi_xxx",
  "amount": "388.00",
  "currency": "SGD",
  "paymentMethodId": "pm_card_visa",
  "createdAt": "2026-04-08T12:00:00.000000"
}
```

### Refund Payment

- `POST /payment/v1/payment/refund`

Example request:

```json
{
  "userId": "USR-0042",
  "ticketId": "TKT-10003",
  "paymentId": "PAY-AB12CD34",
  "amount": 388.00,
  "reason": "CONCERT_CANCELLED"
}
```

Use this endpoint for true refund scenarios such as:

- concert cancellation
- refunding an earlier successful payment

Do **not** use this endpoint for resale seller settlement.

### Record Resale Seller Payout

- `POST /payment/v1/payment/resale-payout`

This endpoint records the seller-side payout after a buyer has successfully completed a resale purchase.

Example request:

```json
{
  "sellerId": "USR-0099",
  "ticketId": "TKT-10003",
  "concertId": "CONC-000001",
  "buyerPaymentId": "PAY-AB12CD34",
  "amount": 388.00
}
```

Example success response:

```json
{
  "paymentId": "PAY-CD34EF56",
  "type": "REFUND",
  "status": "SUCCESS",
  "reason": "RESALE_PAYOUT",
  "amount": "388.00",
  "currency": "SGD",
  "originalPaymentId": "PAY-AB12CD34",
  "createdAt": "2026-04-08T12:00:00.000000",
  "mode": "demo_internal_settlement"
}
```

Rules:

- `buyerPaymentId` must exist
- it must reference a successful `RESALE_PURCHASE`
- only one payout record can exist for the same resale buyer payment

### Lookup Endpoints

- `GET /payment/v1/payment/<paymentId>`
- `GET /payment/v1/payment/user/<userId>`
- `GET /payment/v1/payment/concert/<concertId>`

## Database

Primary table:

- `payment_record`

Stores:

- internal payment ID
- user ID
- ticket ID
- concert ID
- payment type
- amount and currency
- payment status
- Stripe payment intent ID
- Stripe refund ID
- original payment linkage for refunds
- resale payout linkage through `originalPaymentId`

## Payment Types and Reasons

Common values currently used in `payment_record`:

- `type='PURCHASE'`
- `type='RESALE_PURCHASE'`
- `type='REFUND'`

Common `reason` values:

- `CONCERT_CANCELLED`
- `RESALE_PAYOUT`

Interpretation:

- `PURCHASE` = primary sale buyer charge
- `RESALE_PURCHASE` = resale buyer charge
- `REFUND` + `RESALE_PAYOUT` = seller payout record in the current demo model

## API Usage by Other Services

Current internal usage:

- `purchase_window` calls `POST /payment/v1/payment` for primary ticket purchases
- `concert_cancellation` calls `POST /payment/v1/payment/refund` for concert refunds
- `resale_purchase` calls `POST /payment/v1/payment` for the buyer charge
- `resale_purchase` then calls `POST /payment/v1/payment/resale-payout` for seller settlement

## Secret Key vs Publishable Key

Stripe has two different key types for different trust levels.

### Secret key

- Starts with `sk_test_` or `sk_live_`
- Must stay on the backend only
- Can create charges, refunds, payment intents, and other privileged Stripe objects
- If exposed publicly, anyone could act as your Stripe server

In this project:

- you already have `STRIPE_SECRET_KEY`
- it is used only by the payment service backend

### Publishable key

- Starts with `pk_test_` or `pk_live_`
- Safe to expose in frontend code
- Used with Stripe.js on the browser
- Cannot create charges directly
- Used to tokenize card details or confirm payment flows securely from the browser

In this project:

- there is currently **no** `STRIPE_PUBLISHABLE_KEY`
- that is acceptable because this project is not doing a full real browser-side Stripe integration

## Why This Project Does Not Need a Publishable Key Right Now

Because the current setup is a demo/test integration:

- no real customer payment data is being sent to Stripe.js from the browser
- no real checkout form is embedded with Stripe Elements
- the frontend only maps known test card numbers to test payment method IDs

So for your current scope, the **secret key is enough** for backend test payments.

The resale payout record does not require a Stripe publishable key either, because it is not a browser-side Stripe payment flow.

## Important Limitation

This is acceptable for demo purposes, but it is **not** a production-safe card integration model.

For a real payment deployment, you would want:

- a Stripe publishable key in the frontend
- Stripe.js or Checkout
- no raw/demo card handling logic in your own page
- a real seller payout/transfer model such as Stripe Connect if resale money must move to sellers through Stripe

## Run Notes

Typical startup path:

```bash
docker compose up --build payment mysql_payment
```

Or bring up the full stack:

```bash
docker compose up --build
```
