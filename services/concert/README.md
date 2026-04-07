# Concert Microservice
 
## Overview
 
Manages concert listings and seat category configurations for the CTMS platform. Built on OutSystems and hosted on OutSystems Personal Cloud — no local container required.
 
## Base URL
 
```
https://personal-cqdsnkhp.outsystemscloud.com/ConcertAPI/rest/v1
```
 
## Endpoints
 
```
https://personal-cqdsnkhp.outsystemscloud.com/ConcertAPI/rest/v1/concerts
https://personal-cqdsnkhp.outsystemscloud.com/ConcertAPI/rest/v1/concerts/{concertId}
https://personal-cqdsnkhp.outsystemscloud.com/ConcertAPI/rest/v1/concerts/{concertId}/seats
https://personal-cqdsnkhp.outsystemscloud.com/ConcertAPI/rest/v1/concerts/{concertId}/seats/{categoryId}
https://personal-cqdsnkhp.outsystemscloud.com/ConcertAPI/rest/v1/health
```
 
---
 
### Get All Concerts (GET)
 
```
GET /concerts
```
 
Returns all active concerts.
 
**Response:**
```json
{
  "concerts": [
    {
      "concertId": "CONC-000001",
      "name": "Taylor Swift The Eras Tour",
      "venue": "National Stadium, Singapore",
      "artistName": "Taylor Swift",
      "eventDate": "2025-09-14",
      "totalSeats": 50000,
      "availableSeats": 18430,
      "status": "ACTIVE",
      "currency": "SGD"
    }
  ]
}
```
 
---
 
### Get Specific Concert (GET)
 
```
GET /concerts/{concertId}
```
 
Returns a single concert by ID.
 
---
 
### Create Concert (POST)
 
```
POST /concerts
```
 
**Body:**
```json
{
  "concertId": "CONC-000001",
  "name": "Taylor Swift The Eras Tour",
  "artistName": "Taylor Swift",
  "venue": "National Stadium, Singapore",
  "eventDate": "2025-09-14T19:00:00",
  "currency": "SGD",
  "status": "ACTIVE"
}
```
 
---
 
### Update Concert (PUT)
 
```
PUT /concerts/{concertId}
```
 
Supports partial updates — only include fields you want to change.
 
**Body (example — cancel a concert):**
```json
{
  "status": "CANCELLED",
  "cancellationReason": "Artist health emergency"
}
```
 
**Response:**
```json
{
  "updated": true,
  "concertId": "CONC-000001"
}
```
 
---
 
### Get Seat Categories (GET)
 
```
GET /concerts/{concertId}/seats
```
 
Returns all seat categories for a concert. Returns empty array if no categories configured.
 
**Response:**
```json
{
  "concertId": "CONC-000001",
  "categories": [
    {
      "categoryId": "CAT-C001-01",
      "categoryName": "CAT 1 - Floor / Pit",
      "basePrice": 388.0,
      "totalSeats": 5000,
      "availableSeats": 230
    }
  ]
}
```
 
---
 
### Create Seat Categories (POST)
 
```
POST /concerts/{concertId}/seats
```
 
**Body:**
```json
{
  "categories": [
    { "categoryId": "CAT-C001-01", "categoryName": "CAT 1 - Floor / Pit", "basePrice": 388, "totalSeats": 5000, "availableSeats": 5000 },
    { "categoryId": "CAT-C001-02", "categoryName": "CAT 2 - Lower Tier",  "basePrice": 248, "totalSeats": 15000, "availableSeats": 15000 }
  ]
}
```
 
---
 
### Update Seat Availability (PUT)
 
```
PUT /concerts/{concertId}/seats/{categoryId}
```
 
**Body (set directly or use delta):**
```json
{ "availableSeats": 50 }
```
or
```json
{ "deltaAvailable": -1 }
```
 
**Response:**
```json
{
  "updated": true,
  "concertId": "CONC-000001",
  "categoryId": "CAT-C001-01",
  "totalSeats": 5000,
  "availableSeats": 49
}
```
 
---
 
### Get All Active Concerts (GET)
 
```
GET /concerts/active
```
 
Returns only concerts with status `ACTIVE`.
 
---
 
### Health Check (GET)
 
```
GET /health
```
 
**Response:**
```json
{
  "status": "ok",
  "service": "concert"
}
```
 
---
 
## Seed Data
 
The following concerts and seat categories are pre-loaded in the OutSystems database:
 
| Concert ID     | Name                                   | Status    |
|----------------|----------------------------------------|-----------|
| CONC-000001    | Taylor Swift The Eras Tour             | ACTIVE    |
| CONC-000002    | Coldplay: Music of the Spheres         | ACTIVE    |
| CONC-000003    | Bruno Mars: 24K Magic Live             | SOLD_OUT  |
| CONC-000004    | BTS: Yet To Come in Singapore          | CANCELLED |
| CONC-000005    | Ed Sheeran: Mathematics Tour           | POSTPONED |
 
Each concert has 4 seat categories: `CAT-C00X-01` through `CAT-C00X-04`.
 
---
 
## How to Import OAP (for developers)
 
1. Download `ConcertAPI.oml` from the `outsystems/` folder in this repo
2. Open OutSystems Service Studio
3. Click **Environment** → **Open Files** → select the `.oml` file
4. Click **Proceed** to install
5. Publish the module
 
> **Note:** The live API is already deployed. Importing the OML is only needed if you want to run your own copy or make changes.