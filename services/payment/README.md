# Payment Service

Atomic payment microservice for the concert ticketing platform.

## Purpose

This service handles:

- ticket purchase payments
- resale purchase payments
- refunds
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

## Important Limitation

This is acceptable for demo purposes, but it is **not** a production-safe card integration model.

For a real payment deployment, you would want:

- a Stripe publishable key in the frontend
- Stripe.js or Checkout
- no raw/demo card handling logic in your own page

## Run Notes

Typical startup path:

```bash
docker compose up --build payment mysql_payment
```

Or bring up the full stack:

```bash
docker compose up --build
```
