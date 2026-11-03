# Tixelise POS — Sell Flow API

The four calls a POS application needs: log in, see the events assigned to the till,
see that event's categories with their prices, and record the sale. Printing uses the
`tickets[]` array returned by the sale. A fifth call — token refresh — is only needed
when a token is rejected (§3).

```
POST /auth/login/                      -> access token + tenant
GET  /pos/events/                      -> assigned, active events
GET  /pos/events/{id}/categories/      -> categories + server-side prices
POST /pos/sales/                       -> sale + tickets[]  (print these)

POST /auth/refresh/                    -> only when a call answers 401
```

---

## 1. Conventions

| Item | Value |
|---|---|
| Base URL (LAN, phone on the same Wi-Fi) | `http://10.78.54.10:8000/api/v1` |
| Content type | `application/json` |
| Auth header | `Authorization: Bearer <access_token>` |
| `Idempotency-Key` | **Mandatory** on `POST /pos/sales/` — 1–128 chars, unique per basket (§6) |
| Access token life | 365 days — a till signs in once and stays signed in |
| Money | Decimal **string**, 2 dp, e.g. `"499.00"` (never a float) |
| IDs | `event` and `category` are integers; `tickets[].id` is a UUID |
| Timestamps | ISO-8601, e.g. `2026-12-20T13:30:00+00:00` |
| Lists | POS endpoints return **plain arrays**, never paginated |

Every path in this document is written from the host root, so
`POST /api/v1/auth/login/` in full is `http://10.78.54.10:8000/api/v1/auth/login/`.
The app's base constant already ends in `/api/v1`, so client code appends only
`/auth/login/`.

### Error shape (every failure)

```json
{
  "error": {
    "code": "ASSIGNMENT_REQUIRED",
    "message": "You are not assigned to sell tickets for this event."
  }
}
```

If any call returns `401`, try `POST /auth/refresh/` once (§3) and replay the request. If
the refresh also fails, the session is dead — send the user back to the login screen.

---

## 2. `POST /api/v1/auth/login/`

The POS user logs in with the **tenant code** plus their own username and password.

**Headers:** `Content-Type: application/json` (no auth header)

| Field | Type | Required | Notes |
|---|---|---|---|
| `tenant_code` | string | yes | The organisation code, e.g. `EV004` |
| `username` | string | yes | |
| `password` | string | yes | |

```json
{
  "tenant_code": "EV004",
  "username": "ravi.kumar",
  "password": "S3cure-Pass-2026"
}
```

`200 OK`

```json
{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "role": "pos_staff",
  "tenant": {
    "id": 1,
    "code": "EV004",
    "name": "Tixelise Demo Events",
    "timezone": "Asia/Kolkata",
    "currency": "INR"
  }
}
```

Keep both tokens: `access` for every later call, `refresh` for `POST /auth/refresh/` (§3).
The tenant's `currency` is the one shown on prices and on the sale; `timezone` is the
organisation's local time.

Errors:

| Status | Code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | `detail: Invalid credentials.` · `tenant_code: Unknown tenant code.` · `tenant_code: No membership in this organization.` |
| 403 | `TENANT_SUSPENDED` | Organisation suspended by the platform |
| 403 | `TENANT_INACTIVE` | Organisation deactivated |
| 403 | `MEMBERSHIP_INACTIVE` | This user was deactivated, or their staff profile was |
| 403 | `LICENSE_EXPIRED` | Licence check failed for the tenant |

---

## 3. `POST /api/v1/auth/refresh/`

Exchanges the stored refresh token for a new access token. With year-long tokens a till
rarely calls it, but it is the correct answer to a `401` and saves the operator from
typing credentials again mid-shift.

**Headers:** `Content-Type: application/json` — no `Authorization` header; the refresh
token itself is the credential.

| Field | Type | Required | Notes |
|---|---|---|---|
| `refresh` | string | yes | The `refresh` value stored at login |

```json
{ "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." }
```

`200 OK`

```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

The new `access` carries the same role and tenant claims as the original — nothing else
has to change, just replace the stored token.

**The refresh token rotates.** The response carries a brand-new `refresh` — store it and
use it next time. The token you sent keeps working until its own expiry (server-side
blacklisting is off), so a client that forgets to store the new one still gets through; it
simply keeps minting a fresh token from the older one.

### When to call it

Only after another endpoint answers `401`:

```
GET  /pos/events/        -> 401 INVALID_TOKEN
POST /auth/refresh/      -> 200 { access, refresh }   (store both)
GET  /pos/events/        -> retry once with the new access
refresh also fails       -> clear the session, show the login screen
```

Never refresh on `403` or `400` — those are permission or payload problems and a new
token will not fix them.

### Errors

| Status | Code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | `refresh: This field is required.` — empty body |
| 401 | `INVALID_TOKEN` | Expired (older than 365 days), malformed, or signed with an old secret |

---

## 4. `GET /api/v1/pos/events/`

The events this staff member may sell **right now**: the event is `active`, plus there is
an `active` assignment for them that is inside its validity window. No parameters.

**Headers:** `Authorization: Bearer <access_token>`

`200 OK`

```json
[
  {
    "id": 19,
    "code": "EV004",
    "name": "Sunburn Arena Night",
    "venue": "Nehru Stadium",
    "start_at": "2026-12-20T13:30:00+00:00",
    "end_at": "2026-12-20T18:30:00+00:00"
  }
]
```

An empty array (`[]`) is a normal answer — it means nothing is assigned or sellable yet,
so show "No events assigned" instead of an error.

Errors:

| Status | Code | When |
|---|---|---|
| 403 | `permission_denied` | The token is not a POS staff token (e.g. a tenant-admin or platform token) |
| 403 | `FORBIDDEN` | `No active staff profile.` — the profile was deactivated |

---

## 5. `GET /api/v1/pos/events/{event_id}/categories/`

Tapping an event loads its sellable categories **with the price to charge**. Prices are
always resolved on the server; the app never sends a price back.

**Headers:** `Authorization: Bearer <access_token>`

Path parameter: `event_id` — the `id` from step 4.

`200 OK` — `GET /api/v1/pos/events/19/categories/`

```json
[
  { "category": 1, "code": "ADULT", "name": "Adult", "price": "499.00", "currency": "INR" },
  { "category": 2, "code": "CHILD", "name": "Child", "price": "199.00", "currency": "INR" }
]
```

| Field | Meaning |
|---|---|
| `category` | Category id — send **this** value in the sale body |
| `code` / `name` | Labels for the till buttons |
| `price` | Unit price as a string, already formatted to 2 dp |
| `currency` | Currency of the price |

Only `active` categories with an `active` price are returned. If the staff member's
assignment restricts categories, the list is filtered to the allowed ones. An empty array
means nothing can be sold for this event yet.

Errors:

| Status | Code | When |
|---|---|---|
| 403 | `permission_denied` | The token is not a POS staff token |
| 403 | `FORBIDDEN` | `You are not assigned to this event.` · `This assignment is not currently valid.` |

---

## 6. `POST /api/v1/pos/sales/`

Records one sale and issues the tickets. Called once, when the operator confirms payment.

**Headers:**

```
Authorization: Bearer <access_token>
Content-Type: application/json
Idempotency-Key: 6f1b4c2e-9d1a-4b7c-8f3e-2a0d9c8b7a61
```

`Idempotency-Key` is **mandatory** (1–128 chars, any unique string — a UUID per basket is
ideal). If the request times out, retry with the **same** key: the server answers `200`
with the original sale instead of selling twice. A new key means a new sale.

| Field | Type | Required | Notes |
|---|---|---|---|
| `event` | int | yes | Event being sold |
| `items` | array | yes | At least one line |
| `items[].category` | int | yes | `category` id from step 5 |
| `items[].quantity` | int | yes | 1–100 per line |

```json
{
  "event": 19,
  "items": [
    { "category": 1, "quantity": 2 },
    { "category": 2, "quantity": 1 }
  ]
}
```

`201 CREATED` — new sale:

```json
{
  "id": 88,
  "sale_reference": "EV004-S-1A2B3C4D",
  "event": 19,
  "event_code": "EV004",
  "event_name": "Sunburn Arena Night",
  "staff": 5,
  "staff_code": "ST012",
  "staff_name": "Ravi Kumar",
  "status": "completed",
  "gross_total": "1197.00",
  "refund_total": "0.00",
  "currency": "INR",
  "items": [
    {
      "id": 171,
      "category": 1,
      "category_code": "ADULT",
      "category_name": "Adult",
      "quantity": 2,
      "unit_price_snapshot": "499.00",
      "line_total": "998.00"
    },
    {
      "id": 172,
      "category": 2,
      "category_code": "CHILD",
      "category_name": "Child",
      "quantity": 1,
      "unit_price_snapshot": "199.00",
      "line_total": "199.00"
    }
  ],
  "tickets": [
    {
      "id": "0b0f0e2a-6f1b-4c2e-9d1a-6a1f5f0f1c11",
      "ticket_code": "EV004-ST012-EV004-20261101T093000Z-000001",
      "event": 19,
      "event_code": "EV004",
      "staff": 5,
      "staff_code": "ST012",
      "category": 1,
      "category_name": "Adult",
      "sequence_number": 1,
      "status": "issued",
      "issued_at": "2026-11-01T09:30:00Z",
      "reprint_count": 0
    },
    {
      "id": "7c2d4b1a-1d5e-4f3a-8b9c-0e6a7d5c4b32",
      "ticket_code": "EV004-ST012-EV004-20261101T093000Z-000002",
      "event": 19,
      "event_code": "EV004",
      "staff": 5,
      "staff_code": "ST012",
      "category": 1,
      "category_name": "Adult",
      "sequence_number": 2,
      "status": "issued",
      "issued_at": "2026-11-01T09:30:00Z",
      "reprint_count": 0
    },
    {
      "id": "c9a8b7d6-5e4f-4a3b-9c2d-1e0f9a8b7c65",
      "ticket_code": "EV004-ST012-EV004-20261101T093000Z-000003",
      "event": 19,
      "event_code": "EV004",
      "staff": 5,
      "staff_code": "ST012",
      "category": 2,
      "category_name": "Child",
      "sequence_number": 3,
      "status": "issued",
      "issued_at": "2026-11-01T09:30:00Z",
      "reprint_count": 0
    }
  ],
  "created_at": "2026-11-01T09:30:00Z",
  "replayed": false
}
```

`200 OK` — replay of an already-processed key, identical body with `"replayed": true`.
Render it as a normal success; do not create a second sale.

### Printing

`tickets[]` holds **one entry per physical ticket**, in sequence order — 2 adults + 1
child gives 3 tickets. Print each entry, using `ticket_code`, `event_name`,
`category_name` and `issued_at`. The sale is already recorded, so a printer failure must
not trigger a new sale: the ticket can be reprinted later by ticket id.

### What the server validates

| Rule | Failure |
|---|---|
| `Idempotency-Key` present and ≤ 128 chars | `IDEMPOTENCY_KEY_REQUIRED` |
| At least one item | `EMPTY_SALE` |
| Quantity 1–100 | `INVALID_QUANTITY` |
| No repeated category in `items` | `DUPLICATE_CATEGORY` |
| Event exists in this tenant | `NOT_FOUND` |
| Event is `active` | `EVENT_NOT_SELLABLE` |
| Now is inside `sales_start_at` … `sales_end_at` | `SALES_WINDOW_CLOSED` |
| Category exists and is `active` | `NOT_FOUND` / `CATEGORY_NOT_ALLOWED` |
| An active, in-window assignment for this staff + event | `ASSIGNMENT_REQUIRED` |
| Category allowed by the assignment restriction | `CATEGORY_NOT_ALLOWED` |
| An `active` price exists for (event, category) | `PRICE_UNAVAILABLE` |

Full status list:

| Status | Code | What to do in the app |
|---|---|---|
| 400 | `IDEMPOTENCY_KEY_REQUIRED` | Send the header |
| 400 | `EMPTY_SALE` | Nothing selected |
| 400 | `INVALID_QUANTITY` | Clamp quantity to 1–100 |
| 400 | `DUPLICATE_CATEGORY` | Merge the lines into one |
| 400 | `EVENT_NOT_SELLABLE` | Event no longer on sale — go back to the event list |
| 400 | `SALES_WINDOW_CLOSED` | Selling period over |
| 400 | `PRICE_UNAVAILABLE` | No price configured — tell the operator |
| 400 | `SALE_CONFLICT` | Momentary write conflict — retry with the **same** key |
| 403 | `ASSIGNMENT_REQUIRED` | Not assigned / assignment expired |
| 403 | `CATEGORY_NOT_ALLOWED` | This till may not sell that category |
| 403 | `permission_denied` | The token is not a POS staff token |
| 404 | `NOT_FOUND` | Event or category missing |
| 409 | `IDEMPOTENCY_CONFLICT` | Key reused with a different basket — start a new key |

---

## 7. The whole flow, in order

```
1  POST /api/v1/auth/login/
   { "tenant_code": "EV004", "username": "ravi.kumar", "password": "…" }
   -> access + refresh tokens

2  GET  /api/v1/pos/events/
   Authorization: Bearer <access>
   -> [ { "id": 19, "code": "EV004", "name": "Sunburn Arena Night", … } ]

3  GET  /api/v1/pos/events/19/categories/
   Authorization: Bearer <access>
   -> [ { "category": 1, "code": "ADULT", "price": "499.00", … } ]

4  POST /api/v1/pos/sales/
   Authorization: Bearer <access>
   Idempotency-Key: <uuid for this basket>
   { "event": 19, "items": [ { "category": 1, "quantity": 2 } ] }
   -> 201 { "sale_reference": "…", "gross_total": "998.00", "tickets": [ … ] }

5  Print every object in tickets[], then show the confirmation screen.
```

Carry only three ids between steps: the `access` token, the chosen `event.id`, and the
chosen `category` values. Everything else — prices, totals, ticket codes — is produced by
the server.

If any of steps 2–4 answers `401`, call `POST /api/v1/auth/refresh/` once with the stored
`refresh`, replace both tokens, and replay that one request. Anything else means the
session is gone — clear it and show the login screen.
