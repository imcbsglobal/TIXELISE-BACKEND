# Tixelise — Backend API (Phase 1–3)

Multi-tenant ticketing platform backend: tenant isolation, JWT auth, role-based
permissions, event/catalog/staff masters, transactional ticket issuance with
idempotency, audit trail, and daily reporting.

Implements the backend & admin scope from `../tixelise_multitenant_backend_admin_overview.md`
(phases 1–3, plus dashboard/reports/audit). SQLite by default; PostgreSQL-ready.
Application-owned database tables use the `_tixelise` suffix. Django framework
tables keep their standard names; run the migrations below to rename existing
application tables without recreating them.

See [DATABASE_ARCHITECTURE.md](DATABASE_ARCHITECTURE.md) for the current table
inventory, database configuration, and entity relationships.

## Quick start

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python manage.py migrate
.venv\Scripts\python scripts\seed_demo.py
.venv\Scripts\python manage.py runserver
```

### Demo credentials (after seeding)

| Role | Username | Password | Tenant code |
|---|---|---|---|
| Platform admin | `platform` | `Platform@123` | *(omit)* |
| Tenant admin | `admin` | `Admin@123` | `DREAMS001` |
| POS staff | `ravi` | `Staff@123` | `DREAMS001` |

## Running tests

```powershell
.venv\Scripts\python manage.py test tests --noinput
```

52 tests: tenant isolation, authorization, auth lifecycle, sale/ticket
engine, idempotency, threaded concurrency, reporting, platform lifecycle.

## Switching to PostgreSQL

1. `pip install "psycopg[binary]"` (already in requirements).
2. Create the DB and set in `backend/.env`:
   ```
   DATABASE_URL=postgres://user:password@localhost:5432/tixelise
   ```
3. `python manage.py migrate`

No code changes needed — `config/settings/base.py` parses `DATABASE_URL`
automatically (SQLite only when it is unset). Postgres additionally enables
real `SELECT ... FOR UPDATE` row locking on the ticket sequence.

### Later (Postgres-only hardening, not yet implemented)

- PostgreSQL Row-Level Security policies per tenant table + connection-context
  reset (MD §13.3) — SQLite cannot run RLS.
- Refresh-token blacklisting (`token_blacklist` app) for true server-side
  logout revocation.

## API map (`/api/v1/`)

### Auth
| Method | Path | Who |
|---|---|---|
| POST | `/auth/login/` | `{tenant_code?, username, password}` → `{access, refresh, role, tenant}` |
| POST | `/auth/refresh/` | `{refresh}` → rotated pair (tenant claims preserved) |
| POST | `/auth/logout/` | signed-in |
| GET | `/auth/me/` | identity + memberships |

### Platform (`platform_admin` only)
`GET|POST /platform/tenants/` · `GET|PATCH /platform/tenants/{id}/` ·
`POST /platform/tenants/{id}/activate|suspend|deactivate/`

### Tenant admin (`tenant_admin` only)
| Module | Endpoints |
|---|---|
| Dashboard | `GET /admin/dashboard/` |
| Events | `GET|POST /admin/events/` · `GET|PATCH /admin/events/{id}/` · `POST /admin/events/{id}/active|completed|cancelled/` |
| Categories | `GET|POST /admin/categories/` · `GET|PATCH /admin/categories/{id}/` |
| Prices | `GET|POST /admin/prices/` · `GET|PATCH /admin/prices/{id}/` |
| Templates | `GET|POST /admin/ticket-templates/` · `GET|PATCH /admin/ticket-templates/{id}/` |
| Staff | `GET|POST /admin/staff/` · `GET|PATCH /admin/staff/{id}/` · `POST /admin/staff/{id}/deactivate|reset-password/` |
| Assignments | `GET|POST /admin/assignments/` · `POST /admin/assignments/{id}/revoke/` |
| Sales | `GET /admin/sales/?event=&staff=&date_from=&date_to=` · `GET /admin/sales/{id}/` |
| Tickets | `GET /admin/tickets/` · `GET /admin/tickets/{id}/` · `POST /admin/tickets/{id}/reprint/` |
| Reports | `GET /admin/reports/daily/?date=YYYY-MM-DD` · `GET /admin/reports/staff/?date_from=&date_to=` |
| Audit | `GET /admin/audit-logs/?action=&actor=` |

### POS (`pos_staff` only)
| Method | Path | Notes |
|---|---|---|
| GET | `/pos/events/` | assigned + active only |
| GET | `/pos/events/{id}/categories/` | honors assignment category restrictions |
| POST | `/pos/sales/` | **requires `Idempotency-Key` header** |
| GET | `/pos/sales/history/` | own sales |
| GET | `/pos/tickets/{id}/` | own tickets only |
| POST | `/pos/tickets/{id}/reprint/` | records reprint, never re-issues |

Example sale:

```powershell
POST /api/v1/pos/sales/
Headers: Authorization: Bearer <access>, Idempotency-Key: <uuid>
{
  "event": 1,
  "items": [{"category": 1, "quantity": 2}]
}
```

Ticket code format (server-generated, DB-unique):

```
DREAMS001-ST012-EV004-20261020T103025Z-000001
└tenant─┘└staff┘└event┘└────UTC stamp────┘└seq─┘
```

Sequence scope: one counter per `(tenant, event)`, locked with
`SELECT ... FOR UPDATE` inside the sale transaction. The uniqueness is
enforced by database constraints, not application checks.

## Security model

- Tenant context comes **only from verified JWT claims** (never request body).
- Every request re-validates tenant status + membership status + role match,
  so suspension/revocation takes effect immediately — old tokens cannot
  bypass it.
- `TenantManager` auto-scopes every queryset to the current tenant
  (defense in depth); cross-tenant detail access returns 404.
- Prices are calculated server-side; sale items store unit-price snapshots
  so later price edits never rewrite history.
- Assignments are re-checked on **every** sale, not just at login.
- All errors return `{"error": {"code", "message"}}` with a correlation id
  echoed in `X-Correlation-ID` and stored on audit records.
- Audit log covers login, tenant/staff/event/price/assignment changes, sales
  and reprints; never records passwords or tokens.

## Project layout

```
backend/
├── config/            settings (base/development/production), urls, wsgi
├── apps/
│   ├── core/          tenant context, auth, permissions, error contract, middleware
│   ├── tenancy/       Tenant, TenantMembership
│   ├── accounts/      custom User, JWT login flow
│   ├── platform_admin/ tenant lifecycle API
│   ├── events/        event master + status state machine
│   ├── catalog/       categories, event prices, ticket templates
│   ├── staff/         staff profiles + provisioning
│   ├── assignments/   staff-event assignments (POS security gate)
│   ├── ticketing/     TicketSequence, Ticket, reprint
│   ├── sales/         Sale/SaleItem/IdempotencyRecord + sale service + POS API
│   ├── reporting/     dashboard, daily report (tenant timezone)
│   └── audit/         AuditLog + record_audit service
├── tests/             52 tests incl. threaded concurrency
└── scripts/           seed_demo.py
```

## Deferred (documented scope)

Refunds/voids, CSV/XLSX exports, React admin panel, offline POS ranges,
QR validation, devices, RLS, refresh-token blacklist, tenant billing.
