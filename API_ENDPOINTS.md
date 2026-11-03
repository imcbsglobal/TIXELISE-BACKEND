# Tixelise — Complete API Reference

**Backend API documentation for all three roles: Platform Admin, Tenant Admin, and POS Staff.**
Every endpoint lists the method, path, auth role, request body, response body, and error cases — plus the full end-to-end flow.

- **Base URL:** `http://localhost:8000/api/v1/`
- **Format:** JSON in, JSON out (UTF-8)
- **Server:** `python manage.py runserver` from `backend/`

---

## Table of Contents

1. [Conventions](#1-conventions)
2. [End-to-End Flow](#2-end-to-end-flow)
3. [Authentication API (all roles)](#3-authentication-api)
4. [Platform Admin API](#4-platform-admin-api)
5. [Tenant Admin API](#5-tenant-admin-api)
6. [POS Staff API](#6-pos-staff-api)
7. [Error Code Reference](#7-error-code-reference)

---

## 1. Conventions

### Headers

| Header | Required | Value |
|---|---|---|
| `Authorization` | All endpoints except login | `Bearer <access_token>` |
| `Idempotency-Key` | `POST /pos/sales/` only | Unique string (max 128 chars) per sale attempt — reuse it on retries |
| `Content-Type` | All POST/PATCH | `application/json` |
| `X-Correlation-ID` | Optional (request) | Server echoes it back on the response; also generated when absent |

### Response envelope

Success responses return the resource directly (or a pagination object for lists).

Error responses always use this shape:

```json
{
  "error": {
    "code": "ASSIGNMENT_REQUIRED",
    "message": "You are not assigned to sell tickets for this event."
  }
}
```

### Pagination (list endpoints)

All list endpoints that use pagination return:

```json
{
  "count": 57,
  "next": "http://localhost:8000/api/v1/admin/events/?page=3",
  "previous": "http://localhost:8000/api/v1/admin/events/?page=1",
  "results": [ ... ]
}
```

Query params: `?page=2` · `?page_size=50` (max 100).

> POS list endpoints (`/pos/events/`, `/pos/events/{id}/categories/`, `/pos/sales/history/`) return a **plain array** — they are intentionally small and unpaginated.

### Roles and token claims

| Login | Role claim | Access scope |
|---|---|---|
| `tenant_code` omitted + `is_platform_admin` user | `platform_admin` | `/platform/*` only |
| `tenant_code` + tenant-admin membership | `tenant_admin` | `/admin/*` + auth, own tenant only |
| `tenant_code` + POS membership | `pos_staff` | `/pos/*` + auth, assigned events only |

Tenant context comes **only from verified JWT claims**. Every request re-checks tenant status, membership status, and role — suspending a tenant or deactivating staff invalidates existing tokens immediately.

---

## 2. End-to-End Flow

```
 ┌────────────────────────────────────────────────────────────────────────┐
 │ STEP 1 — PLATFORM ADMIN                                               │
 │   POST /auth/login/ (no tenant_code)                                  │
 │   POST /platform/tenants/         → creates tenant DREAMS001           │
 │   (admin_username + admin_password → tenant admin created in same call)│
 │   (tenant suspended/activated later with /suspend/ /activate/)        │
 └────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ STEP 2 — TENANT ADMIN (onboarding)                                    │
 │   POST /auth/login/ (tenant_code=DREAMS001)                           │
 │   POST /admin/categories/        → ADULT, CHILD, VIP                  │
 │   POST /admin/events/            → EV004 (draft)                      │
 │   POST /admin/prices/            → EV004 × ADULT = 499.00             │
 │   POST /admin/staff/             → ST012 ravi (creates login)         │
 │   POST /admin/assignments/       → ST012 → EV004                      │
 │   POST /admin/events/1/active/   → EV004 now sellable                 │
 └────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ STEP 3 — POS STAFF (selling)                                          │
 │   POST /auth/login/ (tenant_code=DREAMS001, ravi)                     │
 │   GET  /pos/events/                → only assigned + active events    │
 │   GET  /pos/events/1/categories/   → sellable categories + prices     │
 │   POST /pos/sales/  (Idempotency-Key)                                 │
 │        → validates assignment → window → price → locks sequence       │
 │        → Sale + Tickets committed → print payload returned            │
 │   POST /pos/tickets/{id}/reprint/  → printer retry (no new ticket)    │
 └────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ STEP 4 — TENANT ADMIN (review)                                        │
 │   GET /admin/dashboard/        → today's totals                       │
 │   GET /admin/sales/?event=1    → sale detail with price snapshots     │
 │   GET /admin/tickets/          → ticket codes, statuses               │
 │   GET /admin/reports/daily/    → event/category/staff breakdowns      │
 │   GET /admin/audit-logs/       → full trace with correlation IDs      │
 └────────────────────────────────────────────────────────────────────────┘
```

Full request/response for every step is shown in the sections below.

---

## 3. Authentication API

> All three roles start here. `authentication_classes = []` — no token needed.

### 3.1 Login

```
POST /api/v1/auth/login/
```

**Request body (tenant user):**

```json
{
  "tenant_code": "DREAMS001",
  "username": "admin",
  "password": "Admin@123"
}
```

**Request body (platform admin — omit `tenant_code`):**

```json
{
  "username": "platform",
  "password": "Platform@123"
}
```

**Response `200 OK`:**

```json
{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "role": "tenant_admin",
  "tenant": {
    "id": 1,
    "code": "DREAMS001",
    "name": "Dreams Events",
    "timezone": "Asia/Kolkata",
    "currency": "INR"
  }
}
```

> Platform login returns the same shape with `"role": "platform_admin"` and `"tenant": null`.

**Errors:**

| Status | Code | Cause |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Wrong username/password (message: `detail: Invalid credentials.`) |
| 400 | `VALIDATION_ERROR` | Missing `tenant_code` for a non-platform user |
| 400 | `VALIDATION_ERROR` | Unknown tenant code / no membership in that tenant |
| 403 | `TENANT_SUSPENDED` | Tenant suspended |
| 403 | `TENANT_INACTIVE` | Tenant deactivated |
| 403 | `MEMBERSHIP_INACTIVE` | Membership deactivated |
| 400 | `VALIDATION_ERROR` (message: `user_inactive`) | User account disabled |

### 3.2 Refresh token

```
POST /api/v1/auth/refresh/
```

**Request:**

```json
{ "refresh": "eyJhbGciOiJIUzI1NiIs..." }
```

**Response `200 OK`** (rotated pair — tenant claims carried into the new access token):

```json
{
  "access": "eyJhbGciOiJIUzI1NiIs...",
  "refresh": "eyJhbGciOiJIUzI1NiIs..."
}
```

### 3.3 Logout

```
POST /api/v1/auth/logout/
Authorization: Bearer <access>
```

**Response `200 OK`:**

```json
{ "detail": "Signed out." }
```

> Phase 1 is stateless: the client discards both tokens. (Server-side refresh blacklisting is a documented follow-up.)

### 3.4 Current identity

```
GET /api/v1/auth/me/
Authorization: Bearer <access>
```

**Response `200 OK`:**

```json
{
  "id": 2,
  "username": "admin",
  "first_name": "",
  "last_name": "",
  "email": "admin@dreams.example",
  "is_platform_admin": false,
  "memberships": [
    {
      "id": 1,
      "tenant": 1,
      "tenant_code": "DREAMS001",
      "tenant_name": "Dreams Events",
      "tenant_status": "active",
      "role": "tenant_admin",
      "status": "active"
    }
  ]
}
```

---

## 4. Platform Admin API

> **Role:** `platform_admin` (login without `tenant_code`).
> Platform access manages **tenant lifecycle only** — it never exposes tenant business data (events, sales, staff).

### 4.1 List / create tenants

```
GET  /api/v1/platform/tenants/
POST /api/v1/platform/tenants/
```

**Create request** — creates the tenant **and its first tenant admin in one transaction** (no seed script needed):

```json
{
  "code": "DREAMS001",
  "name": "Dreams Events",
  "timezone": "Asia/Kolkata",
  "currency": "INR",
  "phone": "+91 98765 43210",
  "settings": {
    "country_code": "IN",
    "country_name": "INDIA",
    "fiscal_year": { "from": "APRIL", "to": "MARCH" }
  },
  "admin_username": "dreams_admin",
  "admin_password": "DreamsAdmin123!",
  "admin_email": "admin@dreams.example",
  "admin_first_name": "John",
  "admin_last_name": "Doe"
}
```

| Field | Required | Notes |
|---|---|---|
| `code` | yes | Unique platform-wide. Becomes `client_id` in both central masters |
| `name` | yes | |
| `timezone`, `currency`, `settings` | no | Defaults: `UTC`, `INR`, `{}` |
| `phone` | **yes** | Tenant contact number, free-form, max 32 chars. Sent as `phone_number` to the user master |
| `admin_username` | **yes** | Must be unused platform-wide |
| `admin_password` | **yes** | Django password validators enforced |
| `admin_email` | **yes** | |
| `admin_first_name`, `admin_last_name` | no | Default `""`. Fall back to the username and `"-"` when sent to the user master |

**Response `201 Created`** (standard tenant shape — admin credentials are never echoed):

```json
{
  "id": 1,
  "code": "DREAMS001",
  "name": "Dreams Events",
  "status": "active",
  "timezone": "Asia/Kolkata",
  "currency": "INR",
  "phone": "+91 98765 43210",
  "settings": {},
  "admin_central_user_id": "",
  "created_at": "2026-10-20T08:00:00Z",
  "updated_at": "2026-10-20T08:00:00Z",
  "currency_registration": {
    "status": "registered",
    "detail": "INR registered for DREAMS001."
  },
  "central_user_registration": {
    "status": "registered",
    "central_user_id": "12",
    "detail": "Registered in the central user master."
  }
}
```

**Central currency registration** — after the tenant + admin are committed, the
backend also POSTs the tenant's currency to the central currency master
(`https://centralmastermanagement.imcbs.com/api/currency-master/currencies/`):

```json
{
  "client_id": "DREAMS001",
  "code": "INR",
  "name": "Indian Rupee",
  "status": "ACTIVE"
}
```

| `currency_registration.status` | Meaning |
|---|---|
| `registered` | New record created in the currency master |
| `skipped` | Tenant code + currency pair already present (checked with a read first), or `CENTRAL_CURRENCY_SYNC_ENABLED=false` |
| `failed` | Master unreachable or returned an error |

> `client_id` is the tenant `code`. `name` comes from a built-in ISO map for the
> seven currencies offered by the tenant form (`AED`, `BHD`, `INR`, `KWD`, `OMR`,
> `QAR`, `SAR`); any other code is sent as its own name. This call is
> **best-effort**: the tenant is already created, so a `failed` status never rolls
> it back — the outcome is surfaced in the response and in the audit log
> (`platform.tenant.currency_registered`).

> The created admin can log in **immediately**: `POST /auth/login/` with `tenant_code: "DREAMS001"`, `admin_username`, and the password you set — role `tenant_admin`. Tenant + user + membership are created atomically; if anything fails, nothing is persisted.

**Central user registration** — after the currency step, the first tenant admin is
also POSTed to the central user master
(`https://centralmastermanagement.imcbs.com/api/user-master/`):

```json
{
  "client_id": "DREAMS001",
  "first_name": "John",
  "last_name": "Doe",
  "username": "dreams_admin",
  "password": "DreamsAdmin123!",
  "email": "admin@dreams.example",
  "phone_number": "+91 9876543210",
  "user_role": "ADMIN",
  "trellisco": false,
  "claudius": false,
  "melone": false,
  "tixelise": true,
  "trellisco_crm": false,
  "melone_stay": false,
  "trellisco_books": false,
  "status": "ACTIVE"
}
```

| `central_user_registration.status` | Meaning |
|---|---|
| `registered` | Account created, or confirmed after a lost response; its `id` was read back and stored on the membership |
| `skipped` | A record for this `client_id` + `username` already existed and its id was adopted, this admin is already linked, or `CENTRAL_USER_SYNC_ENABLED=false` |
| `failed` | Master unreachable, rejected the request, or no password was supplied |

> `client_id` is the tenant `code`. Only `tixelise` is `true`; the other six product
> flags are always sent as `false`. `user_role` is `ADMIN`.
> The stored id (`TenantMembership.central_user_id`, surfaced read-only as
> `admin_central_user_id`) is what makes deletion possible later.
>
> This call is **best-effort** and never rolls the tenant back. A `failed` status is
> returned to the UI together with a retry path (`4.7`) and recorded in the audit
> log as `platform.tenant.central_user_registered`.
>
> **Security note:** the master stores and exposes this password in plaintext over
> an unauthenticated `GET /api/user-master/` list. The password is never logged or
> stored by Tixelise, but it is visible on the master's side.
>
> **Master response contract:** `POST` answers `201 {"message": "User created
> successfully."}` — it does **not** return the new `id`. The id is therefore read
> back from `GET /api/user-master/` by matching `client_id` + `username`. If that
> read-back fails, the account still counts as `registered` but
> `central_user_id` stays empty, so deletion cannot remove it until `4.7` runs.
>
> The master enforces uniqueness **per `client_id`** on `username`, `email` and
> `phone_number` — the tenant `phone` cannot be reused by a second admin of the
> same client. A rejection names the offending field in `detail`, e.g.
> `Central master rejected the request (HTTP 400: {"phone_number": [...]})`.
>
> Central calls allow 20s and retry once on a transport failure. A failed `POST`
> is always followed by a lookup before failure is reported, so a write whose
> response was lost is reported as `registered` rather than as an outage.

**Errors:**

| Status | Code | Cause |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Missing `admin_username`/`admin_password`/`admin_email`/`phone`, duplicate `code`, duplicate username, weak password |

> `status` always starts as `active`; `id/status/created_at/updated_at` are read-only.

**List response `200 OK`** (paginated):

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    { "id": 1, "code": "DREAMS001", "name": "Dreams Events", "status": "active", "...": "..." },
    { "id": 2, "code": "NEXUS002", "name": "Nexus Shows", "status": "suspended", "...": "..." }
  ]
}
```

### 4.2 Tenant detail / update

```
GET   /api/v1/platform/tenants/1/
PATCH /api/v1/platform/tenants/1/
```

**PATCH request:**

```json
{ "name": "Dreams Events Pvt Ltd", "timezone": "Asia/Kolkata" }
```

**Response `200 OK`:** the full tenant object (as in 4.1).

> `status` cannot be changed here — use the action endpoints below.

**Delete tenant:**

```
DELETE /api/v1/platform/tenants/1/
```

Deletes the tenant and all tenant-owned business data (events, categories, prices,
staff, assignments, sales, tickets) in dependency-safe order, then removes the
tenant's accounts from the central user master.

Login identities go too, but only the ones this deletion orphaned: a `User`
survives when it is a platform admin (`is_platform_admin`/`is_superuser`), still
holds a membership in another tenant, or still has a staff profile. Audit history
is always kept (`tenant=NULL`, `actor=NULL`, the username preserved in
`actor_label`), and the `platform.tenant.deleted` audit entry records the
per-account outcome under `central_users` plus the row counts under `deleted`.

**Response `204 No Content`.**

> The central delete happens **after** the local delete and is never fatal: a
> master outage leaves the tenant deleted and the account recorded for manual
> cleanup, rather than blocking the operation. Before deleting, the backend
> re-reads each record and refuses to touch it unless `client_id` matches the
> tenant code **and** `tixelise` is `true`.

### 4.3 Activate tenant

```
POST /api/v1/platform/tenants/1/activate/
```

**Response `200 OK`:**

```json
{ "id": 1, "code": "DREAMS001", "status": "active" }
```

**Error `400`:** `{"error": {"code": "ALREADY_IN_STATE", "message": "Tenant is already active."}}`

### 4.4 Suspend tenant

```
POST /api/v1/platform/tenants/1/suspend/
```

**Response `200 OK`:**

```json
{ "id": 1, "code": "DREAMS001", "status": "suspended" }
```

> Effect: every member's **existing token stops working immediately** (`403 TENANT_SUSPENDED` on any request) and login is blocked until reactivated.

### 4.5 Deactivate tenant

```
POST /api/v1/platform/tenants/1/deactivate/
```

**Response `200 OK`:**

```json
{ "id": 1, "code": "DREAMS001", "status": "inactive" }
```

**Platform errors:** `403 NOT_PLATFORM_ADMIN` if a tenant-scoped token is used; `404 NOT_FOUND` for unknown tenant id.

### 4.6 Tenant currency options

```
GET /api/v1/platform/tenant-currencies/
```

Feeds the currency dropdown on the tenant create/edit forms. The backend proxies
the central financial-year master so the browser never calls a third-party host
(cached for 5 minutes; a built-in list of the same countries is used when the
master cannot be reached).

**Response `200 OK`:**

```json
{
  "source": "remote",
  "results": [
    {
      "country_code": "IN",
      "country_name": "INDIA",
      "currency_code": "INR",
      "fy_from_month": "APRIL",
      "fy_to_month": "MARCH",
      "remark": "Financial year April to March"
    }
  ]
}
```

> `source` is `remote` when the central master answered, `fallback` when the
> built-in list was used. Results are sorted by country name. Selecting an
> option sets `currency` and stores `country_code`/`country_name`/`fiscal_year`
> inside the tenant's `settings` object.

### 4.7 Retry central registration

```
POST /api/v1/platform/tenants/1/sync-central/
```

Re-runs the currency-master and user-master registrations for an existing tenant.
The first attempt during creation is best-effort, and the create form cannot be
submitted twice (duplicate `code`), so this is the only recovery path.

**Request** (both optional — send `password` only when the central account does not
 exist yet):

```json
{ "password": "DreamsAdmin123!" }
```

**Response `200 OK`:**

```json
{
  "currency": { "status": "registered", "detail": "INR registered for DREAMS001." },
  "user": {
    "status": "registered",
    "central_user_id": "12",
    "detail": "Registered in the central user master."
  }
}
```

> Idempotent. If the account already exists in the master it is adopted
> (`status: "skipped"`) instead of duplicated, so calling this repeatedly is
> safe. Without a `password` and with no existing record, `user.status` is
> `failed` and `detail` says a password is required. Audited as
> `platform.tenant.central_sync`.
>
> This is the only path that pre-checks the master list — a fresh create skips
> that lookup because a brand-new username cannot already exist there. Use it to
> recover a `central_user_id` that the create-time read-back could not capture.

**Errors:** `404 NOT_FOUND` for an unknown tenant or missing tenant admin.

---

## 5. Tenant Admin API

> **Role:** `tenant_admin` (login with `tenant_code`).
> Every endpoint below is automatically scoped to the caller's tenant — objects from other tenants return `404`.

### 5.1 Dashboard

```
GET /api/v1/admin/dashboard/
```

**Response `200 OK`:**

```json
{
  "date": "2026-10-20",
  "timezone": "Asia/Kolkata",
  "tickets_sold_today": 14,
  "completed_sales_today": 6,
  "gross_sales_today": "5988.00",
  "refunds_today": "0.00",
  "net_sales_today": "5988.00",
  "active_events": 1,
  "active_staff": 3
}
```

> All date boundaries use the tenant's configured timezone. Money values are strings (Decimal).

---

### 5.2 Events

#### List / create events

```
GET  /api/v1/admin/events/?search=music&status=active
POST /api/v1/admin/events/
```

Query params: `search` (code or name contains), `status` (`draft|active|completed|cancelled`).

**Create request:**

```json
{
  "code": "EV004",
  "name": "Music Fest 2026",
  "description": "Annual music festival",
  "venue": "Central Auditorium",
  "address": "Kochi, Kerala",
  "start_at": "2026-11-01T18:00:00Z",
  "end_at": "2026-11-02T00:00:00Z",
  "sales_start_at": "2026-10-20T00:00:00Z",
  "sales_end_at": "2026-11-01T16:00:00Z"
}
```

**Response `201 Created`:**

```json
{
  "id": 1,
  "code": "EV004",
  "name": "Music Fest 2026",
  "description": "Annual music festival",
  "venue": "Central Auditorium",
  "address": "Kochi, Kerala",
  "start_at": "2026-11-01T18:00:00Z",
  "end_at": "2026-11-02T00:00:00Z",
  "sales_start_at": "2026-10-20T00:00:00Z",
  "sales_end_at": "2026-11-01T16:00:00Z",
  "status": "draft",
  "created_by": 2,
  "created_at": "2026-10-20T08:05:12Z",
  "updated_at": "2026-10-20T08:05:12Z"
}
```

**Errors:** `400 VALIDATION_ERROR` (`end_at` ≤ `start_at`, non-alphanumeric code, duplicate `code` in tenant).

#### Event detail / update

```
GET   /api/v1/admin/events/1/
PATCH /api/v1/admin/events/1/
```

**PATCH request:**

```json
{ "venue": "Grand Palace Grounds", "sales_end_at": "2026-11-01T18:00:00Z" }
```

**Response `200 OK`:** full event object.

> Events with sales history are never hard-deleted — transition them instead.

#### Event status transitions

```
POST /api/v1/admin/events/1/{target}/        target ∈ active | completed | cancelled
```

**Example — activate:**

```
POST /api/v1/admin/events/1/active/
```

**Response `200 OK`:**

```json
{ "id": 1, "status": "active" }
```

**Allowed transitions (state machine):**

| From | To |
|---|---|
| `draft` | `active`, `cancelled` |
| `active` | `completed`, `cancelled` |

**Errors:**

| Status | Code | Cause |
|---|---|---|
| 400 | `INVALID_TRANSITION` | e.g. `draft → completed` |
| 400 | `CONFIGURATION_INCOMPLETE` | activating with zero prices configured |
| 404 | `NOT_FOUND` | unknown event |

---

### 5.3 Ticket categories

#### List / create categories

```
GET  /api/v1/admin/categories/
POST /api/v1/admin/categories/
```

**Create request:**

```json
{ "code": "ADULT", "name": "Adult", "description": "Standard entry" }
```

**Response `201 Created`:**

```json
{
  "id": 1,
  "code": "ADULT",
  "name": "Adult",
  "description": "Standard entry",
  "status": "active",
  "created_at": "2026-10-20T08:06:00Z",
  "updated_at": "2026-10-20T08:06:00Z"
}
```

> Categories are **tenant-level and reusable across events**. `code` is unique per tenant. Deactivating (`PATCH {"status": "inactive"}`) never deletes historical tickets.

#### Category detail / update

```
GET   /api/v1/admin/categories/1/
PATCH /api/v1/admin/categories/1/
```

**PATCH request:** `{ "name": "General Admission", "status": "inactive" }`

---

### 5.4 Event prices

#### List / create prices

```
GET  /api/v1/admin/prices/?event=1
POST /api/v1/admin/prices/
```

**Create request:**

```json
{
  "event": 1,
  "category": 1,
  "amount": "499.00",
  "currency": "INR",
  "effective_from": null,
  "effective_to": null
}
```

**Response `201 Created`:**

```json
{
  "id": 1,
  "event": 1,
  "category": 1,
  "category_code": "ADULT",
  "amount": "499.00",
  "currency": "INR",
  "effective_from": null,
  "effective_to": null,
  "status": "active",
  "created_at": "2026-10-20T08:07:00Z",
  "updated_at": "2026-10-20T08:07:00Z"
}
```

**Errors:** `400 VALIDATION_ERROR` — cross-tenant category/event, inactive category, negative amount, or duplicate `(event, category)` pair.

#### Price detail / update (price edit)

```
GET   /api/v1/admin/prices/1/
PATCH /api/v1/admin/prices/1/
```

**PATCH request:** `{ "amount": "599.00" }`

> **Historical sales are safe:** each sale stores `unit_price_snapshot`, so editing a price never rewrites past transactions (verified by automated test).

---

### 5.5 Ticket templates

```
GET  /api/v1/admin/ticket-templates/
POST /api/v1/admin/ticket-templates/
```

**Create request:**

```json
{
  "name": "Default Thermal 80mm",
  "config": {
    "header": "DREAMS EVENTS",
    "footer": "Thank you!",
    "show_event_name": true,
    "show_venue": true,
    "show_category": true,
    "show_price": true,
    "show_ticket_number": true,
    "datetime_format": "%d %b %Y %H:%M",
    "paper_width": 80,
    "printer_format": "thermal"
  }
}
```

**Response `201 Created`:**

```json
{
  "id": 1,
  "name": "Default Thermal 80mm",
  "config": { "header": "DREAMS EVENTS", "...": "..." },
  "version": 1,
  "status": "active",
  "created_at": "2026-10-20T08:08:00Z",
  "updated_at": "2026-10-20T08:08:00Z"
}
```

**Errors:** `400 VALIDATION_ERROR` for unknown config keys — only whitelisted keys are accepted; the backend never executes tenant template code.

Detail/update: `GET|PATCH /api/v1/admin/ticket-templates/1/`

---

### 5.6 Staff

#### List / create staff

```
GET  /api/v1/admin/staff/
POST /api/v1/admin/staff/
```

**Create request** (creates User + POS membership + StaffProfile in one transaction):
```json
{
  "staff_code": "ST012",
  "display_name": "Ravi Kumar",
  "username": "ravi",
  "email": "ravi@dreams.example",
  "phone": "+919876543210",
  "password": "Staff@123"
}
```

**Response `201 Created`:**

```json
{
  "id": 1,
  "user": 3,
  "staff_code": "ST012",
  "display_name": "Ravi Kumar",
  "phone": "+919876543210",
  "email": "ravi@dreams.example",
  "status": "active",
  "created_by": 2,
  "created_at": "2026-10-20T08:10:00Z",
  "updated_at": "2026-10-20T08:10:00Z",
  "last_login": null,
  "central_user_registration": {
    "status": "registered",
    "central_user_id": "9",
    "detail": "Linked to central user 9."
  }
}
```

**Errors:** `400 VALIDATION_ERROR` — username taken, weak password (Django validators), duplicate `staff_code` in tenant, missing/ invalid `email` or `phone`.

> **Central user registration.** `email` and `phone` are required because the
> staff member is also POSTed to the central user master
> (`https://centralmastermanagement.imcbs.com/api/user-master/`) with
> `user_role: "USER"`, the staff member's own `phone_number`, and `client_id`
> set to the tenant `code`. Everything else matches the tenant-admin payload,
> which uses `user_role: "ADMIN"` — the master accepts only those two values,
> and a POS staff account is a `USER` on its side.
> The master enforces `username`, `email` and `phone_number` uniqueness **per
> `client_id`**, so a second staff member cannot reuse a number already used in
> the same tenant. The call runs after the local transaction commits: an outage
> never blocks or rolls back the staff row — `central_user_registration.status`
> reports `registered`, `skipped` (sync disabled) or `failed`, and the same
> meanings apply as in §4.1. There is no staff-level retry endpoint yet: a
> `failed` staff member is re-registered by running
> `apps.platform_admin.views._register_central_user` for that membership (the
> upstream master is idempotent per `client_id` + `username`).

#### Staff detail / update

```
GET   /api/v1/admin/staff/1/
PATCH /api/v1/admin/staff/1/
```

**PATCH request:** `{ "display_name": "Ravi K.", "phone": "+911111111111" }`

#### Deactivate staff

```
POST /api/v1/admin/staff/1/deactivate/
```

**Response `200 OK`:**

```json
{ "id": 1, "status": "inactive" }
```

> Effect: POS membership is deactivated too — the staff member's **live token stops working on the next request** (`403 MEMBERSHIP_INACTIVE`).

#### Reset password

```
POST /api/v1/admin/staff/1/reset-password/
```

**Request:** `{ "password": "NewStr0ng!Pass" }`

**Response `200 OK`:** `{ "detail": "Password updated." }`

**Errors:** `400 VALIDATION_ERROR` when password missing or fails validators. Password values are never echoed or logged.

---

### 5.7 Staff → Event assignments

> This module is the POS security gate: a sale is rejected unless an **active** assignment exists at sale time.

#### List / create assignments

```
GET  /api/v1/admin/assignments/?staff=1&event=1&status=active
POST /api/v1/admin/assignments/
```

**Create request:**

```json
{
  "staff": 1,
  "event": 1,
  "valid_from": null,
  "valid_until": null,
  "restrict_categories": true,
  "allowed_category_ids": [1, 3]
}
```

**Response `201 Created`:**

```json
{
  "id": 1,
  "staff": 1,
  "staff_code": "ST012",
  "event": 1,
  "event_code": "EV004",
  "status": "active",
  "valid_from": null,
  "valid_until": null,
  "restrict_categories": true,
  "allowed_category_ids": [1, 3],
  "created_by": 2,
  "created_at": "2026-10-20T08:12:00Z",
  "updated_at": "2026-10-20T08:12:00Z"
}
```

**Errors:**

| Status | Code | Cause |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Staff or event belongs to another tenant |
| 400 | `VALIDATION_ERROR` | `valid_until` ≤ `valid_from` |
| 400 | `VALIDATION_ERROR` | duplicate `(staff, event)` pair |

#### Revoke assignment

```
POST /api/v1/admin/assignments/1/revoke/
```

**Response `200 OK`:**

```json
{ "id": 1, "status": "revoked" }
```

**Error `400`:** `{"error": {"code": "ALREADY_REVOKED", ...}}`

> Effect: the assigned staff member **cannot sell on the next request** — even with a still-valid JWT (`403 ASSIGNMENT_REQUIRED`).

---

### 5.8 Sales

#### List sales

```
GET /api/v1/admin/sales/?event=1&staff=1&status=completed&sale_reference=DREAMS001-S-6800898B&date_from=2026-10-01&date_to=2026-10-31
```

(`date_from` / `date_to` optional, `YYYY-MM-DD`, inclusive, resolved in the tenant's timezone.)

**Error `400`:** `{"error": {"code": "VALIDATION_ERROR", "message": "date_from: must be YYYY-MM-DD."}}`

**Response `200 OK`** (paginated):

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "sale_reference": "DREAMS001-S-6800898B",
      "event": 1,
      "event_code": "EV004",
      "event_name": "Music Fest 2026",
      "staff": 1,
      "staff_code": "ST012",
      "staff_name": "Ravi Kumar",
      "status": "completed",
      "gross_total": "998.00",
      "refund_total": "0.00",
      "currency": "INR",
      "items": [
        {
          "id": 1,
          "category": 1,
          "category_code": "ADULT",
          "category_name": "Adult",
          "quantity": 2,
          "unit_price_snapshot": "499.00",
          "line_total": "998.00"
        }
      ],
      "tickets": [
        {
          "id": "6f9619ff-8b86-d011-b42d-00c04fc964ff",
          "ticket_code": "DREAMS001-ST012-EV004-20261020T080128Z-000001",
          "event": 1,
          "event_code": "EV004",
          "staff": 1,
          "staff_code": "ST012",
          "category": 1,
          "category_name": "Adult",
          "sequence_number": 1,
          "status": "issued",
          "issued_at": "2026-10-20T08:01:28Z",
          "reprint_count": 0
        }
      ],
      "created_at": "2026-10-20T08:01:28Z"
    }
  ]
}
```

#### Sale detail

```
GET /api/v1/admin/sales/1/
```

**Response `200 OK`:** the full sale object above (items, tickets, price snapshots included).

> Sales are never deleted — future refund/void flows will be status transitions.

---

### 5.9 Tickets

#### List tickets

```
GET /api/v1/admin/tickets/?event=1&staff=1&status=issued&ticket_code=DREAMS001-ST012-EV004-20261020T080128Z-000001
```

**Response `200 OK`** (paginated):

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "6f9619ff-8b86-d011-b42d-00c04fc964ff",
      "ticket_code": "DREAMS001-ST012-EV004-20261020T080128Z-000001",
      "event": 1,
      "event_code": "EV004",
      "staff": 1,
      "staff_code": "ST012",
      "category": 1,
      "category_name": "Adult",
      "sequence_number": 1,
      "status": "issued",
      "issued_at": "2026-10-20T08:01:28Z",
      "reprint_count": 0
    }
  ]
}
```

> Ticket codes are globally unique (DB constraint). Internal `id` is a UUID kept separate from the printable code.

#### Ticket detail

```
GET /api/v1/admin/tickets/6f9619ff-8b86-d011-b42d-00c04fc964ff/
```

**Response `200 OK`:** single ticket object.

#### Ticket reprint (admin side)

```
POST /api/v1/admin/tickets/6f9619ff-8b86-d011-b42d-00c04fc964ff/reprint/
```

**Response `200 OK`:**

```json
{
  "id": "6f9619ff-8b86-d011-b42d-00c04fc964ff",
  "ticket_code": "DREAMS001-ST012-EV004-20261020T080128Z-000001",
  "reprint_count": 1,
  "print_payload": {
    "ticket_code": "DREAMS001-ST012-EV004-20261020T080128Z-000001",
    "event": { "code": "EV004", "name": "Music Fest 2026", "venue": "Central Auditorium" },
    "category": "Adult",
    "issued_at": "2026-10-20T08:01:28+00:00",
    "sequence_number": 1
  }
}
```

> Reprints **never create a new ticket or sale** — they increment `reprint_count` and write an audit record.

---

### 5.10 Reports

#### Daily report

```
GET /api/v1/admin/reports/daily/?date=2026-10-20
```

(`date` optional, `YYYY-MM-DD`, defaults to *today in tenant timezone*.)

**Response `200 OK`:**

```json
{
  "date": "2026-10-20",
  "timezone": "Asia/Kolkata",
  "tickets_sold": 14,
  "transactions": 6,
  "gross_sales": "5988.00",
  "refunds": "0.00",
  "net_sales": "5988.00",
  "by_event": [
    { "event_id": 1, "event_code": "EV004", "tickets": 14 }
  ],
  "by_category": [
    { "category_id": 1, "category_code": "ADULT", "tickets": 10 },
    { "category_id": 2, "category_code": "CHILD", "tickets": 4 }
  ],
  "by_staff": [
    { "staff_id": 1, "staff_code": "ST012", "tickets": 14 }
  ]
}
```

**Error `400`:** `{"error": {"code": "VALIDATION_ERROR", "message": "date must be YYYY-MM-DD."}}`

**Financial definitions:** `gross` = completed sales before refunds · `net` = gross − recorded refunds · ticket counts ≠ transaction counts.

#### Staff report

```
GET /api/v1/admin/reports/staff/?date_from=2026-10-01&date_to=2026-10-31&event=1
```

(`date_from` / `date_to` optional, `YYYY-MM-DD`, inclusive, default *today in tenant timezone*; `event` optional.)

Every staff member in the tenant is listed, including those with no sales in the range, so the table reconciles against the roster. Money follows the daily report's definition (`gross` counts every sale row regardless of status, `net` = gross − refunds); voided transactions are reported separately.

**Response `200 OK`:**

```json
{
  "date_from": "2026-10-01",
  "date_to": "2026-10-31",
  "timezone": "Asia/Kolkata",
  "currency": "INR",
  "totals": {
    "staff_with_sales": 2,
    "transactions": 46,
    "tickets": 128,
    "gross": "63904.00",
    "refunds": "0.00",
    "net": "63904.00"
  },
  "staff": [
    {
      "staff_id": 1,
      "staff_code": "ST012",
      "display_name": "Ravi Kumar",
      "status": "active",
      "transactions": 40,
      "voided_transactions": 1,
      "tickets": 120,
      "gross": "59880.00",
      "refunds": "0.00",
      "net": "59880.00",
      "avg_ticket_value": "499.00",
      "last_sale_at": "2026-10-30T14:02:11.120000+00:00",
      "by_event": [
        {
          "event_id": 1,
          "event_code": "EV004",
          "event_name": "Music Fest 2026",
          "transactions": 12,
          "tickets": 40,
          "gross": "4796.00",
          "refunds": "0.00"
        }
      ]
    },
    {
      "staff_id": 7,
      "staff_code": "ST020",
      "display_name": "Asha",
      "status": "active",
      "transactions": 0,
      "voided_transactions": 0,
      "tickets": 0,
      "gross": "0.00",
      "refunds": "0.00",
      "net": "0.00",
      "avg_ticket_value": null,
      "last_sale_at": null,
      "by_event": []
    }
  ]
}
```

**Errors `400`:** `date_from must be YYYY-MM-DD.` · `date_from must be on or before date_to.` · `event must be a numeric id.`

> Row order is net-descending, then staff code — staff with no sales fall to the bottom.

---

### 5.11 Audit log

```
GET /api/v1/admin/audit-logs/?action=sale.created&actor=3&target_type=ticket
```

**Response `200 OK`** (paginated):

```json
{
  "count": 42,
  "next": "http://localhost:8000/api/v1/admin/audit-logs/?page=2",
  "previous": null,
  "results": [
    {
      "id": 101,
      "action": "sale.created",
      "actor": "ravi",
      "target_type": "sale",
      "target_id": "1",
      "metadata": {
        "sale_reference": "DREAMS001-S-6800898B",
        "event": "EV004",
        "staff": "ST012",
        "tickets": 2,
        "gross_total": "998.00"
      },
      "correlation_id": "8f14e45f-ea8f-4f0d-9c1a-2b3c4d5e6f70",
      "created_at": "2026-10-20T08:01:28Z"
    },
    {
      "id": 100,
      "action": "assignment.revoked",
      "actor": "admin",
      "target_type": "staff_event_assignment",
      "target_id": "2",
      "metadata": { "staff": "ST008", "event": "EV004" },
      "correlation_id": "3c59dc048e8850243be8079a492b10d1",
      "created_at": "2026-10-20T07:55:10Z"
    }
  ]
}
```

**Recorded actions:** `auth.login` · `platform.tenant.created|updated|activated|suspended|deactivated` · `event.created|updated|active|completed|cancelled` · `category.*` · `price.created|updated` · `template.created` · `staff.created|updated|deactivated|password_reset` · `assignment.created|revoked` · `sale.created` · `ticket.reprint`.

> Passwords and tokens are never written to audit records. Access is restricted to tenant admins of that tenant.

---

## 6. POS Staff API

> **Role:** `pos_staff` (login with `tenant_code`).
> Unlike admin endpoints, these return **plain arrays** (no pagination) because result sets are intentionally small.

### 6.1 My assigned events

```
GET /api/v1/pos/events/
```

**Response `200 OK`:**

```json
[
  {
    "id": 1,
    "code": "EV004",
    "name": "Music Fest 2026",
    "venue": "Central Auditorium",
    "start_at": "2026-11-01T18:00:00Z",
    "end_at": "2026-11-02T00:00:00Z"
  }
]
```

> Only events with a **current active assignment** whose status is `active` appear. A revoked assignment makes the event disappear immediately.

### 6.2 Sellable categories for an event

```
GET /api/v1/pos/events/1/categories/
```

**Response `200 OK`:**

```json
[
  { "category": 1, "code": "ADULT", "name": "Adult", "price": "499.00", "currency": "INR" },
  { "category": 3, "code": "VIP", "name": "VIP", "price": "1499.00", "currency": "INR" }
]
```

> Only categories with an active, currently-effective `EventPrice` are listed, and only those allowed by the assignment when `restrict_categories=true`.

**Errors:** `403 FORBIDDEN` (not assigned), `403 FORBIDDEN` (assignment not yet valid / expired).

### 6.3 Create a sale (the core endpoint)

```
POST /api/v1/pos/sales/
Authorization: Bearer <access>
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
```

**Request:**

```json
{
  "event": 1,
  "items": [
    { "category": 1, "quantity": 2 },
    { "category": 2, "quantity": 1 }
  ]
}
```

**Server-side sequence (single DB transaction):**

1. Derive tenant + staff from the token (never from the body)
2. Check tenant active → assignment active → event `active` + within sales window
3. Load categories + **server-side prices** (client-sent prices are ignored)
4. Idempotency lookup: same key + same payload → return original result; different payload → `409`
5. Lock `TicketSequence(tenant, event)` with `SELECT ... FOR UPDATE` → allocate numbers
6. Create Sale + SaleItems (price snapshots) + Tickets + IdempotencyRecord + audit → **commit**
7. Return the persisted sale — only now may the POS print

**Response `201 Created` (first attempt):**

```json
{
  "id": 1,
  "sale_reference": "DREAMS001-S-6800898B",
  "event": 1,
  "event_code": "EV004",
  "event_name": "Music Fest 2026",
  "staff": 1,
  "staff_code": "ST012",
  "staff_name": "Ravi Kumar",
  "status": "completed",
  "gross_total": "1197.00",
  "refund_total": "0.00",
  "currency": "INR",
  "items": [
    { "id": 1, "category": 1, "category_code": "ADULT", "category_name": "Adult",
      "quantity": 2, "unit_price_snapshot": "499.00", "line_total": "998.00" },
    { "id": 2, "category": 2, "category_code": "CHILD", "category_name": "Child",
      "quantity": 1, "unit_price_snapshot": "199.00", "line_total": "199.00" }
  ],
  "tickets": [
    { "id": "11111111-...", "ticket_code": "DREAMS001-ST012-EV004-20261020T080128Z-000001",
      "sequence_number": 1, "status": "issued", "category_name": "Adult",
      "event_code": "EV004", "staff_code": "ST012",
      "issued_at": "2026-10-20T08:01:28Z", "reprint_count": 0,
      "event": 1, "staff": 1, "category": 1 },
    { "id": "22222222-...", "ticket_code": "DREAMS001-ST012-EV004-20261020T080128Z-000002",
      "sequence_number": 2, "status": "issued", "category_name": "Adult",
      "event_code": "EV004", "staff_code": "ST012",
      "issued_at": "2026-10-20T08:01:28Z", "reprint_count": 0,
      "event": 1, "staff": 1, "category": 1 },
    { "id": "33333333-...", "ticket_code": "DREAMS001-ST012-EV004-20261020T080128Z-000003",
      "sequence_number": 3, "status": "issued", "category_name": "Child",
      "event_code": "EV004", "staff_code": "ST012",
      "issued_at": "2026-10-20T08:01:28Z", "reprint_count": 0,
      "event": 1, "staff": 1, "category": 2 }
  ],
  "created_at": "2026-10-20T08:01:28Z",
  "replayed": false
}
```

**Response `200 OK` (idempotent replay — network retry):** identical body with `"replayed": true`. **No new sale, no new tickets, no new revenue.**

**Ticket code anatomy:**

```
DREAMS001-ST012-EV004-20261020T080128Z-000001
└─tenant─┘└staff┘└event┘└─── UTC stamp ───┘└seq┘
```

Sequence scope = one counter per `(tenant, event)` shared by all staff. Uniqueness is enforced by database constraints, not application checks.

**Errors:**

| Status | Code | Cause |
|---|---|---|
| 400 | `IDEMPOTENCY_KEY_REQUIRED` | `Idempotency-Key` header missing/too long |
| 409 | `IDEMPOTENCY_CONFLICT` | Same key reused with a **different** payload |
| 403 | `ASSIGNMENT_REQUIRED` | No current assignment, revoked, or expired |
| 403 | `CATEGORY_NOT_ALLOWED` | Category not in `allowed_category_ids` / inactive |
| 400 | `EVENT_NOT_SELLABLE` | Event is `draft`, `completed`, or `cancelled` |
| 400 | `SALES_WINDOW_CLOSED` | Now outside `sales_start_at`…`sales_end_at` |
| 400 | `PRICE_UNAVAILABLE` | No active/effective price for a category |
| 400 | `INVALID_QUANTITY` | Quantity outside 1–100 |
| 400 | `DUPLICATE_CATEGORY` | Same category twice in one request |
| 400 | `VALIDATION_ERROR` | Missing/invalid `event` or `items` |
| 404 | `NOT_FOUND` | Event or category not in this tenant |

### 6.4 My sales history

```
GET /api/v1/pos/sales/history/
```

**Response `200 OK`** (plain array, latest 50 own sales — same sale shape as 6.3 minus `replayed`):

```json
[
  {
    "id": 1,
    "sale_reference": "DREAMS001-S-6800898B",
    "event_code": "EV004",
    "event_name": "Music Fest 2026",
    "staff_code": "ST012",
    "status": "completed",
    "gross_total": "1197.00",
    "refund_total": "0.00",
    "currency": "INR",
    "items": [ "..." ],
    "tickets": [ "..." ],
    "created_at": "2026-10-20T08:01:28Z"
  }
]
```

### 6.5 My ticket detail

```
GET /api/v1/pos/tickets/6f9619ff-8b86-d011-b42d-00c04fc964ff/
```

**Response `200 OK`:** ticket object (as in 5.9).

**Error `403 FORBIDDEN`:** tickets belonging to other staff are inaccessible (`You may only view your own tickets.`).

### 6.6 Reprint a ticket (printer failure recovery)

```
POST /api/v1/pos/tickets/6f9619ff-8b86-d011-b42d-00c04fc964ff/reprint/
```

**Response `200 OK`:**

```json
{
  "id": "6f9619ff-8b86-d011-b42d-00c04fc964ff",
  "ticket_code": "DREAMS001-ST012-EV004-20261020T080128Z-000001",
  "reprint_count": 1,
  "print_payload": {
    "ticket_code": "DREAMS001-ST012-EV004-20261020T080128Z-000001",
    "event": { "code": "EV004", "name": "Music Fest 2026", "venue": "Central Auditorium" },
    "category": "Adult",
    "issued_at": "2026-10-20T08:01:28+00:00",
    "sequence_number": 1
  }
}
```

> **Golden rule:** a printer failure triggers a *reprint of the existing ticket*, never ticket regeneration.

---

## 7. Error Code Reference

| HTTP | Code | Meaning |
|---:|---|---|
| 400 | `VALIDATION_ERROR` | Field-level validation failed (message contains field details) |
| 400 | `BAD_REQUEST` | Generic bad request |
| 400 | `INVALID_TRANSITION` | Event status transition not allowed |
| 400 | `CONFIGURATION_INCOMPLETE` | Activating an event with no prices |
| 400 | `EVENT_NOT_SELLABLE` | Event not in `active` status |
| 400 | `SALES_WINDOW_CLOSED` | Outside the configured selling window |
| 400 | `PRICE_UNAVAILABLE` | No active/effective price for the category |
| 400 | `INVALID_QUANTITY` | Quantity outside 1–100 |
| 400 | `DUPLICATE_CATEGORY` | Category repeated in one sale |
| 400 | `IDEMPOTENCY_KEY_REQUIRED` | Missing `Idempotency-Key` header |
| 400 | `SALE_CONFLICT` | Transaction could not complete under concurrency — retry the same request |
| 400 | `ALREADY_IN_STATE` / `ALREADY_REVOKED` | Action already applied |
| 401 | `UNAUTHORIZED` | No/invalid token |
| 401 | `INVALID_TOKEN` | Malformed token, tenant gone, role mismatch |
| 403 | `TENANT_SUSPENDED` / `TENANT_INACTIVE` | Tenant frozen by platform |
| 403 | `MEMBERSHIP_INACTIVE` | Membership or staff deactivated |
| 403 | `NOT_TENANT_ADMIN` / `NOT_POS_STAFF` / `NOT_PLATFORM_ADMIN` | Wrong role for the endpoint |
| 403 | `ASSIGNMENT_REQUIRED` | No active staff→event assignment at sale time |
| 403 | `CATEGORY_NOT_ALLOWED` | Category restricted for this assignment |
| 404 | `NOT_FOUND` | Object missing **or belongs to another tenant** |
| 409 | `IDEMPOTENCY_CONFLICT` | Same key, different payload |
| 500 | `INTERNAL_ERROR` | Unexpected server error (check `X-Correlation-ID` in server logs) |
| 501 | `NOT_IMPLEMENTED` | Endpoint reserved (e.g. future exports) |

---

### Quick cURL walkthrough (copy-paste)

```bash
BASE=http://localhost:8000/api/v1

# 1. Platform creates a tenant
TOKEN=$(curl -s $BASE/auth/login/ -H "Content-Type: application/json" \
  -d '{"username":"platform","password":"Platform@123"}' | python -c "import sys,json;print(json.load(sys.stdin)['access'])")
curl -s $BASE/platform/tenants/ -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"code":"DREAMS001","name":"Dreams Events","timezone":"Asia/Kolkata","currency":"INR","admin_username":"admin","admin_password":"Admin@123"}'

# 2. Tenant admin onboards
ATOKEN=$(curl -s $BASE/auth/login/ -H "Content-Type: application/json" \
  -d '{"tenant_code":"DREAMS001","username":"admin","password":"Admin@123"}' | python -c "import sys,json;print(json.load(sys.stdin)['access'])")
curl -s $BASE/admin/categories/ -H "Authorization: Bearer $ATOKEN" \
  -H "Content-Type: application/json" -d '{"code":"ADULT","name":"Adult"}'
curl -s $BASE/admin/events/ -H "Authorization: Bearer $ATOKEN" \
  -H "Content-Type: application/json" \
  -d '{"code":"EV004","name":"Music Fest","start_at":"2026-11-01T18:00:00Z","end_at":"2026-11-02T00:00:00Z"}'
curl -s $BASE/admin/prices/ -H "Authorization: Bearer $ATOKEN" \
  -H "Content-Type: application/json" -d '{"event":1,"category":1,"amount":"499.00"}'
curl -s $BASE/admin/staff/ -H "Authorization: Bearer $ATOKEN" \
  -H "Content-Type: application/json" \
  -d '{"staff_code":"ST012","display_name":"Ravi","username":"ravi","password":"Staff@123"}'
curl -s $BASE/admin/assignments/ -H "Authorization: Bearer $ATOKEN" \
  -H "Content-Type: application/json" -d '{"staff":1,"event":1}'
curl -s $BASE/admin/events/1/active/ -X POST -H "Authorization: Bearer $ATOKEN"

# 3. POS sells
STOKEN=$(curl -s $BASE/auth/login/ -H "Content-Type: application/json" \
  -d '{"tenant_code":"DREAMS001","username":"ravi","password":"Staff@123"}' | python -c "import sys,json;print(json.load(sys.stdin)['access'])")
curl -s $BASE/pos/sales/ -H "Authorization: Bearer $STOKEN" \
  -H "Content-Type: application/json" -H "Idempotency-Key: demo-1" \
  -d '{"event":1,"items":[{"category":1,"quantity":2}]}'

# 4. Admin reviews
curl -s $BASE/admin/dashboard/ -H "Authorization: Bearer $ATOKEN"
curl -s "$BASE/admin/reports/daily/" -H "Authorization: Bearer $ATOKEN"
```
