# Tixelise — Database Tables Reference

> **Source of truth:** the live SQLite database `backend/db.sqlite3`.
> Generated on **2026-10-26** from `PRAGMA table_info`, `PRAGMA foreign_key_list`,
> `PRAGMA index_list`, and the exact `CREATE TABLE` DDL in `sqlite_master`.
>
> **Total tables: 25** — 18 application tables (`tixelise_` prefix) + 7 Django framework tables.
>
> **Revision 2026-11-03:** application tables were renamed from the
> `<app>_<model>_tixelise` suffix form to the `tixelise_<app>_<model>` prefix form.
> Table, index, and foreign-key names below reflect the live database after that
> migration; row counts remain the original 2026-10-26 snapshot.
>
> Notes
> - Types shown are the exact SQLite types stored in the database.
> - SQLite DDL has **no `DEFAULT` clauses**; all defaults are applied by Django in Python
>   before the row is written. The `Default` column below shows the Django model default.
> - SQLite displays foreign keys as `NO ACTION DEFERRABLE INITIALLY DEFERRED`.
>   Real cascade/protect behaviour is enforced by the Django ORM. The Django
>   `on_delete` rule is shown next to each foreign key.
> - Example values are real rows from the current database, except where a table is
>   empty (marked **illustrative**). `password` hashes and `session_data` are masked.
> - Row counts are a point-in-time snapshot.

---

## 1. Table inventory (25 tables)

| # | Table | Owner | Django model | Rows |
|---:|---|---|---|---:|
| 1 | `tixelise_tenancy_tenant` | Application | `tenancy.Tenant` | 4 |
| 2 | `tixelise_accounts_user` | Application | `accounts.User` | 11 |
| 3 | `tixelise_tenancy_tenantmembership` | Application | `tenancy.TenantMembership` | 6 |
| 4 | `tixelise_accounts_user_groups` | Application | `accounts.User.groups` (M2M) | 0 |
| 5 | `tixelise_accounts_user_user_permissions` | Application | `accounts.User.user_permissions` (M2M) | 0 |
| 6 | `tixelise_events_event` | Application | `events.Event` | 6 |
| 7 | `tixelise_catalog_ticketcategory` | Application | `catalog.TicketCategory` | 6 |
| 8 | `tixelise_catalog_eventprice` | Application | `catalog.EventPrice` | 10 |
| 9 | `tixelise_catalog_tickettemplate` | Application | `catalog.TicketTemplate` | 0 |
| 10 | `tixelise_staff_staffprofile` | Application | `staff.StaffProfile` | 3 |
| 11 | `tixelise_assignments_staffeventassignment` | Application | `assignments.StaffEventAssignment` | 6 |
| 12 | `tixelise_assignments_staffeventassignment_allowed_categories` | Application | `StaffEventAssignment.allowed_categories` (M2M) | 0 |
| 13 | `tixelise_sales_sale` | Application | `sales.Sale` | 2 |
| 14 | `tixelise_sales_saleitem` | Application | `sales.SaleItem` | 3 |
| 15 | `tixelise_sales_idempotencyrecord` | Application | `sales.IdempotencyRecord` | 2 |
| 16 | `tixelise_ticketing_ticketsequence` | Application | `ticketing.TicketSequence` | 2 |
| 17 | `tixelise_ticketing_ticket` | Application | `ticketing.Ticket` | 5 |
| 18 | `tixelise_audit_auditlog` | Application | `audit.AuditLog` | 134 |
| 19 | `auth_group` | Django framework | `auth.Group` | 0 |
| 20 | `auth_group_permissions` | Django framework | `auth.Group.permissions` (M2M) | 0 |
| 21 | `auth_permission` | Django framework | `auth.Permission` | 80 |
| 22 | `django_admin_log` | Django framework | `admin.LogEntry` | 0 |
| 23 | `django_content_type` | Django framework | `contenttypes.ContentType` | 20 |
| 24 | `django_migrations` | Django framework | migration history | 36 |
| 25 | `django_session` | Django framework | session store | 2 |

### Foreign-key map (exact links)

```
tixelise_tenancy_tenant (id)
├── tixelise_tenancy_tenantmembership.tenant_id
├── tixelise_events_event.tenant_id
├── tixelise_catalog_ticketcategory.tenant_id
├── tixelise_catalog_eventprice.tenant_id
├── tixelise_catalog_tickettemplate.tenant_id
├── tixelise_staff_staffprofile.tenant_id
├── tixelise_assignments_staffeventassignment.tenant_id
├── tixelise_sales_sale.tenant_id
├── tixelise_sales_idempotencyrecord.tenant_id
├── tixelise_ticketing_ticketsequence.tenant_id
├── tixelise_ticketing_ticket.tenant_id
└── tixelise_audit_auditlog.tenant_id            (nullable)

tixelise_accounts_user (id)
├── tixelise_tenancy_tenantmembership.user_id
├── tixelise_accounts_user_groups.user_id
├── tixelise_accounts_user_user_permissions.user_id
├── tixelise_events_event.created_by_id          (nullable)
├── tixelise_staff_staffprofile.user_id
├── tixelise_staff_staffprofile.created_by_id    (nullable)
├── tixelise_assignments_staffeventassignment.created_by_id (nullable)
├── tixelise_sales_sale.created_by_id            (nullable)
├── tixelise_sales_idempotencyrecord.actor_id
├── tixelise_audit_auditlog.actor_id             (nullable)
└── django_admin_log.user_id

tixelise_events_event (id)
├── tixelise_catalog_eventprice.event_id
├── tixelise_assignments_staffeventassignment.event_id
├── tixelise_sales_sale.event_id
├── tixelise_ticketing_ticketsequence.event_id
└── tixelise_ticketing_ticket.event_id

tixelise_catalog_ticketcategory (id)
├── tixelise_catalog_eventprice.category_id
├── tixelise_assignments_staffeventassignment_allowed_categories.ticketcategory_id
├── tixelise_sales_saleitem.category_id
└── tixelise_ticketing_ticket.category_id

tixelise_staff_staffprofile (id)
├── tixelise_assignments_staffeventassignment.staff_id
├── tixelise_sales_sale.staff_id
└── tixelise_ticketing_ticket.staff_id

tixelise_sales_sale (id)
├── tixelise_sales_saleitem.sale_id
├── tixelise_sales_idempotencyrecord.sale_id     (nullable)
└── tixelise_ticketing_ticket.sale_id

tixelise_assignments_staffeventassignment (id)
└── tixelise_assignments_staffeventassignment_allowed_categories.staffeventassignment_id

auth_group (id)
├── tixelise_accounts_user_groups.group_id
└── auth_group_permissions.group_id

auth_permission (id)
├── tixelise_accounts_user_user_permissions.permission_id
└── auth_group_permissions.permission_id

django_content_type (id)
├── auth_permission.content_type_id
└── django_admin_log.content_type_id             (nullable)

django_migrations / django_session — no foreign keys.
```

---

## 2. Application tables

### 1. `tixelise_tenancy_tenant`

**Django model:** `tenancy.Tenant` — the tenant (organisation) root record.
**Rows:** 4

| Column | SQLite type | Null | Default | Key / constraint | Example (id=1) |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `code` | `varchar(32)` | NO | — | UNIQUE | `DREAMS001` |
| `name` | `varchar(255)` | NO | — | — | `Dreams Events` |
| `status` | `varchar(16)` | NO | `active` (Django) | values: `active`, `suspended`, `inactive`; indexed | `active` |
| `timezone` | `varchar(64)` | NO | `UTC` (Django) | — | `Asia/Kolkata` |
| `currency` | `varchar(8)` | NO | `INR` (Django) | — | `INR` |
| `phone` | `varchar(32)` | NO | `""` (Django) | — | `+91 98765 43210` |
| `settings` | `text` | NO | `{}` (Django) | JSON check: `JSON_VALID(settings) OR settings IS NULL` | `{}` |
| `created_at` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:00:07.951012` |
| `updated_at` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:00:07.951030` |

**Indexes / constraints**
- `sqlite_autoindex_tixelise_tenancy_tenant_1` — UNIQUE (`code`)
- `tenancy_tenant_status_bb1f1bbe` — INDEX (`status`)

**Relationships:** one tenant → many memberships, events, categories, prices, templates, staff profiles, assignments, sales, idempotency records, ticket sequences, tickets, audit logs (see FK map).

**Example row**
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
  "created_at": "2026-10-20 08:00:07.951012",
  "updated_at": "2026-10-20 08:00:07.951030"
}
```

---

### 2. `tixelise_accounts_user`

**Django model:** `accounts.User` (custom `AbstractUser`) — global login identity, not tenant-owned. A tenant deletion removes a row only when it is left with no membership and no staff profile.
**Rows:** 11

| Column | SQLite type | Null | Default | Key / constraint | Example (id=1) |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `password` | `varchar(128)` | NO | — | Django password hash | `<masked django password hash>` |
| `last_login` | `datetime` | YES | `NULL` | — | `2026-10-20 08:28:37.539166` |
| `is_superuser` | `bool` | NO | `0` (Django) | — | `0` |
| `username` | `varchar(150)` | NO | — | UNIQUE | `platform` |
| `first_name` | `varchar(150)` | NO | `""` (Django) | — | `""` |
| `last_name` | `varchar(150)` | NO | `""` (Django) | — | `""` |
| `email` | `varchar(254)` | NO | `""` (Django) | — | `""` |
| `is_staff` | `bool` | NO | `0` (Django) | — | `1` |
| `is_active` | `bool` | NO | `1` (Django) | — | `1` |
| `date_joined` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:00:07.365728` |
| `is_platform_admin` | `bool` | NO | `0` (Django) | — | `1` |

**Indexes / constraints**
- `sqlite_autoindex_tixelise_accounts_user_1` — UNIQUE (`username`)

**Relationships:** one user → many memberships; many staff profiles; created events; created assignments; created sales; idempotency records; audit events; `django_admin_log` entries; M2M to groups and permissions.

**Example row**
```json
{
  "id": 1,
  "password": "<masked django password hash>",
  "last_login": "2026-10-20 08:28:37.539166",
  "is_superuser": 0,
  "username": "platform",
  "first_name": "",
  "last_name": "",
  "email": "",
  "is_staff": 1,
  "is_active": 1,
  "date_joined": "2026-10-20 08:00:07.365728",
  "is_platform_admin": 1
}
```

---

### 3. `tixelise_tenancy_tenantmembership`

**Django model:** `tenancy.TenantMembership` — links a global user to a tenant with a role.
**Rows:** 4

| Column | SQLite type | Null | Default | Key / constraint | Example (id=1) |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `role` | `varchar(32)` | NO | — | values: `tenant_admin`, `pos_staff` | `tenant_admin` |
| `status` | `varchar(16)` | NO | `active` (Django) | values: `active`, `inactive`; indexed | `active` |
| `created_at` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:00:08.619139` |
| `updated_at` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:00:08.619167` |
| `tenant_id` | `bigint` | NO | — | FK → `tixelise_tenancy_tenant.id` (Django `CASCADE`) | `1` |
| `user_id` | `bigint` | NO | — | FK → `tixelise_accounts_user.id` (Django `CASCADE`) | `2` |
| `central_user_id` | `varchar(64)` | NO | `''` | Indexed. Primary key of this user in the central user master; `''` until registered | `"12"` |

**Indexes / constraints**
- `sqlite_autoindex_tixelise_tenancy_tenantmembership_1` — UNIQUE (`tenant_id`, `user_id`) (`uniq_tenant_membership`)
- `tixelise_tenancy_tenantmembership_user_id_002c295a` — INDEX (`user_id`)
- `tixelise_tenancy_tenantmembership_tenant_id_e088e682` — INDEX (`tenant_id`)
- `tixelise_tenancy_tenantmembership_status_88434970` — INDEX (`status`)
- `tixelise_tenancy_tenantmembership_central_user_id_86425d05` — INDEX (`central_user_id`)

**Relationships:** many memberships → one tenant, one user.

**Example row**
```json
{
  "id": 1,
  "role": "tenant_admin",
  "status": "active",
  "created_at": "2026-10-20 08:00:08.619139",
  "updated_at": "2026-10-20 08:00:08.619167",
  "tenant_id": 1,
  "user_id": 2,
  "central_user_id": "12"
}
```

---

### 4. `tixelise_accounts_user_groups`

**Django model:** auto-created M2M table for `accounts.User.groups`.
**Rows:** 0 (illustrative example below)

| Column | SQLite type | Null | Default | Key / constraint | Example |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `user_id` | `bigint` | NO | — | FK → `tixelise_accounts_user.id` (Django `CASCADE`) | `2` |
| `group_id` | `INTEGER` | NO | — | FK → `auth_group.id` (Django `CASCADE`) | `1` |

**Indexes / constraints**
- `tixelise_accounts_user_groups_user_id_group_id_36d69fbc_uniq` — UNIQUE (`user_id`, `group_id`)
- `tixelise_accounts_user_groups_group_id_a34f04e7` — INDEX (`group_id`)
- `tixelise_accounts_user_groups_user_id_e6df1151` — INDEX (`user_id`)

**Relationships:** many link rows → one user, one auth group.

**Example row (illustrative)**
```json
{ "id": 1, "user_id": 2, "group_id": 1 }
```

---

### 5. `tixelise_accounts_user_user_permissions`

**Django model:** auto-created M2M table for `accounts.User.user_permissions`.
**Rows:** 0 (illustrative example below)

| Column | SQLite type | Null | Default | Key / constraint | Example |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `user_id` | `bigint` | NO | — | FK → `tixelise_accounts_user.id` (Django `CASCADE`) | `2` |
| `permission_id` | `INTEGER` | NO | — | FK → `auth_permission.id` (Django `CASCADE`) | `1` |

**Indexes / constraints**
- `tixelise_accounts_user_user_permissions_user_id_permission_id_52d51b24_uniq` — UNIQUE (`user_id`, `permission_id`)
- `tixelise_accounts_user_user_permissions_permission_id_ced4dcf3` — INDEX (`permission_id`)
- `tixelise_accounts_user_user_permissions_user_id_35e42cfa` — INDEX (`user_id`)

**Relationships:** many link rows → one user, one permission.

**Example row (illustrative)**
```json
{ "id": 1, "user_id": 2, "permission_id": 1 }
```

---

### 6. `tixelise_events_event`

**Django model:** `events.Event` — an event owned by a tenant.
**Rows:** 6

| Column | SQLite type | Null | Default | Key / constraint | Example (id=1) |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `code` | `varchar(32)` | NO | — | UNIQUE per tenant | `EV004` |
| `name` | `varchar(255)` | NO | — | — | `Music Fest 2026` |
| `description` | `text` | NO | `""` (Django) | — | `""` |
| `venue` | `varchar(255)` | NO | `""` (Django) | — | `Central Auditorium` |
| `address` | `varchar(500)` | NO | `""` (Django) | — | `Kochi, Kerala` |
| `start_at` | `datetime` | NO | — | must be `< end_at` | `2026-10-27 08:00:39.786835` |
| `end_at` | `datetime` | NO | — | CHECK `end_at > start_at` | `2026-10-27 14:00:39.786835` |
| `sales_start_at` | `datetime` | YES | `NULL` | — | `2026-10-20 08:00:39.786835` |
| `sales_end_at` | `datetime` | YES | `NULL` | — | `2026-10-27 08:00:39.786835` |
| `status` | `varchar(16)` | NO | `draft` (Django) | values: `draft`, `active`, `completed`, `cancelled`; indexed | `active` |
| `created_at` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:00:39.788825` |
| `updated_at` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:00:39.854075` |
| `created_by_id` | `bigint` | YES | `NULL` | FK → `tixelise_accounts_user.id` (Django `SET_NULL`) | `2` |
| `tenant_id` | `bigint` | NO | — | FK → `tixelise_tenancy_tenant.id` (Django `PROTECT`) | `1` |

**Indexes / constraints**
- `sqlite_autoindex_tixelise_events_event_1` — UNIQUE (`tenant_id`, `code`) (`uniq_tenant_event_code`)
- `events_event_tenant_id_388ba8e1` — INDEX (`tenant_id`)
- `events_event_created_by_id_2c28ea90` — INDEX (`created_by_id`)
- `events_event_status_a1b46b6a` — INDEX (`status`)
- CHECK `event_end_after_start`: `end_at > start_at`

**Relationships:** many events → one tenant, one creator (nullable); one event → many prices, assignments, sales, ticket sequences, tickets.

**Example row**
```json
{
  "id": 1,
  "code": "EV004",
  "name": "Music Fest 2026",
  "description": "",
  "venue": "Central Auditorium",
  "address": "Kochi, Kerala",
  "start_at": "2026-10-27 08:00:39.786835",
  "end_at": "2026-10-27 14:00:39.786835",
  "sales_start_at": "2026-10-20 08:00:39.786835",
  "sales_end_at": "2026-10-27 08:00:39.786835",
  "status": "active",
  "created_at": "2026-10-20 08:00:39.788825",
  "updated_at": "2026-10-20 08:00:39.854075",
  "created_by_id": 2,
  "tenant_id": 1
}
```

---

### 7. `tixelise_catalog_ticketcategory`

**Django model:** `catalog.TicketCategory` — reusable tenant-level ticket category.
**Rows:** 6

| Column | SQLite type | Null | Default | Key / constraint | Example (id=1) |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `code` | `varchar(32)` | NO | — | UNIQUE per tenant | `ADULT` |
| `name` | `varchar(100)` | NO | — | — | `Adult` |
| `description` | `text` | NO | `""` (Django) | — | `""` |
| `status` | `varchar(16)` | NO | `active` (Django) | values: `active`, `inactive` | `active` |
| `created_at` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:00:39.750043` |
| `updated_at` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:00:39.750065` |
| `tenant_id` | `bigint` | NO | — | FK → `tixelise_tenancy_tenant.id` (Django `PROTECT`) | `1` |

**Indexes / constraints**
- `sqlite_autoindex_tixelise_catalog_ticketcategory_1` — UNIQUE (`tenant_id`, `code`) (`uniq_tenant_category_code`)
- `catalog_ticketcategory_tenant_id_ad8db04c` — INDEX (`tenant_id`)

**Relationships:** many categories → one tenant; one category → many prices, assignment category links, sale items, tickets.

**Example row**
```json
{
  "id": 1,
  "code": "ADULT",
  "name": "Adult",
  "description": "",
  "status": "active",
  "created_at": "2026-10-20 08:00:39.750043",
  "updated_at": "2026-10-20 08:00:39.750065",
  "tenant_id": 1
}
```

---

### 8. `tixelise_catalog_eventprice`

**Django model:** `catalog.EventPrice` — price of one category for one event (effective dates optional).
**Rows:** 10

| Column | SQLite type | Null | Default | Key / constraint | Example (id=1) |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `amount` | `decimal` | NO | — | CHECK `amount >= 0` | `499` |
| `currency` | `varchar(8)` | NO | `INR` (Django) | — | `INR` |
| `effective_from` | `datetime` | YES | `NULL` | — | `null` |
| `effective_to` | `datetime` | YES | `NULL` | — | `null` |
| `status` | `varchar(16)` | NO | `active` (Django) | values: `active`, `inactive` | `active` |
| `created_at` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:00:39.803221` |
| `updated_at` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:00:39.803265` |
| `event_id` | `bigint` | NO | — | FK → `tixelise_events_event.id` (Django `CASCADE`) | `1` |
| `tenant_id` | `bigint` | NO | — | FK → `tixelise_tenancy_tenant.id` (Django `PROTECT`) | `1` |
| `category_id` | `bigint` | NO | — | FK → `tixelise_catalog_ticketcategory.id` (Django `PROTECT`) | `1` |

**Indexes / constraints**
- `sqlite_autoindex_tixelise_catalog_eventprice_1` — UNIQUE (`tenant_id`, `event_id`, `category_id`) (`uniq_tenant_event_category_price`)
- `catalog_eventprice_category_id_2ed38dd9` — INDEX (`category_id`)
- `catalog_eventprice_tenant_id_98e724af` — INDEX (`tenant_id`)
- `catalog_eventprice_event_id_6ec88793` — INDEX (`event_id`)
- CHECK `price_amount_non_negative`: `amount >= 0`

**Relationships:** many prices → one tenant, one event, one category. The `(tenant, event, category)` triple is unique.

**Example row**
```json
{
  "id": 1,
  "amount": 499,
  "currency": "INR",
  "effective_from": null,
  "effective_to": null,
  "status": "active",
  "created_at": "2026-10-20 08:00:39.803221",
  "updated_at": "2026-10-20 08:00:39.803265",
  "event_id": 1,
  "tenant_id": 1,
  "category_id": 1
}
```

---

### 9. `tixelise_catalog_tickettemplate`

**Django model:** `catalog.TicketTemplate` — tenant ticket layout/configuration.
**Rows:** 0 (illustrative example below)

| Column | SQLite type | Null | Default | Key / constraint | Example |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `name` | `varchar(100)` | NO | — | — | `Default Thermal 80mm` |
| `config` | `text` | NO | `{}` (Django) | JSON check: `JSON_VALID(config) OR config IS NULL` | `{"header": "DREAMS EVENTS", "paper_width": 80}` |
| `version` | `integer unsigned` | NO | `1` (Django) | CHECK `version >= 0` | `1` |
| `status` | `varchar(16)` | NO | `active` (Django) | values: `active`, `inactive` | `active` |
| `created_at` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:08:00` |
| `updated_at` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:08:00` |
| `tenant_id` | `bigint` | NO | — | FK → `tixelise_tenancy_tenant.id` (Django `PROTECT`) | `1` |

**Indexes / constraints**
- `catalog_tickettemplate_tenant_id_e371818b` — INDEX (`tenant_id`)
- CHECK: `JSON_VALID(config) OR config IS NULL`
- CHECK: `version >= 0`

**Relationships:** many templates → one tenant.

**Example row (illustrative)**
```json
{
  "id": 1,
  "name": "Default Thermal 80mm",
  "config": { "header": "DREAMS EVENTS", "paper_width": 80 },
  "version": 1,
  "status": "active",
  "created_at": "2026-10-20 08:08:00",
  "updated_at": "2026-10-20 08:08:00",
  "tenant_id": 1
}
```

---

### 10. `tixelise_staff_staffprofile`

**Django model:** `staff.StaffProfile` — a user's staff identity inside a tenant.
**Rows:** 3

| Column | SQLite type | Null | Default | Key / constraint | Example (id=1) |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `staff_code` | `varchar(32)` | NO | — | UNIQUE per tenant | `ST012` |
| `display_name` | `varchar(255)` | NO | — | — | `Ravi Kumar` |
| `phone` | `varchar(32)` | NO | `""` (Django) | — | `""` |
| `email` | `varchar(254)` | NO | `""` (Django) | — | `""` |
| `status` | `varchar(16)` | NO | `active` (Django) | values: `active`, `inactive` | `active` |
| `created_at` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:00:39.735195` |
| `updated_at` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:00:39.735223` |
| `last_login` | `datetime` | YES | `NULL` | — | `null` |
| `created_by_id` | `bigint` | YES | `NULL` | FK → `tixelise_accounts_user.id` (Django `SET_NULL`) | `2` |
| `tenant_id` | `bigint` | NO | — | FK → `tixelise_tenancy_tenant.id` (Django `PROTECT`) | `1` |
| `user_id` | `bigint` | NO | — | FK → `tixelise_accounts_user.id` (Django `PROTECT`) | `3` |

**Indexes / constraints**
- `sqlite_autoindex_tixelise_staff_staffprofile_2` — UNIQUE (`tenant_id`, `user_id`) (`uniq_tenant_staff_user`)
- `sqlite_autoindex_tixelise_staff_staffprofile_1` — UNIQUE (`tenant_id`, `staff_code`) (`uniq_tenant_staff_code`)
- `staff_staffprofile_user_id_de1feaad` — INDEX (`user_id`)
- `staff_staffprofile_tenant_id_6609cafe` — INDEX (`tenant_id`)
- `staff_staffprofile_created_by_id_d09ceda9` — INDEX (`created_by_id`)

**Relationships:** many staff profiles → one tenant, one user, one creator (nullable); one staff profile → many assignments, sales, tickets.

**Example row**
```json
{
  "id": 1,
  "staff_code": "ST012",
  "display_name": "Ravi Kumar",
  "phone": "",
  "email": "",
  "status": "active",
  "created_at": "2026-10-20 08:00:39.735195",
  "updated_at": "2026-10-20 08:00:39.735223",
  "last_login": null,
  "created_by_id": 2,
  "tenant_id": 1,
  "user_id": 3
}
```

---

### 11. `tixelise_assignments_staffeventassignment`

**Django model:** `assignments.StaffEventAssignment` — the POS security gate linking a staff profile to an event.
**Rows:** 6

| Column | SQLite type | Null | Default | Key / constraint | Example (id=1) |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `status` | `varchar(16)` | NO | `active` (Django) | values: `active`, `revoked`, `expired`; indexed | `active` |
| `valid_from` | `datetime` | YES | `NULL` | — | `null` |
| `valid_until` | `datetime` | YES | `NULL` | — | `null` |
| `restrict_categories` | `bool` | NO | `0` (Django) | — | `0` |
| `created_at` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:00:39.842409` |
| `updated_at` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:00:39.842426` |
| `created_by_id` | `bigint` | YES | `NULL` | FK → `tixelise_accounts_user.id` (Django `SET_NULL`) | `2` |
| `event_id` | `bigint` | NO | — | FK → `tixelise_events_event.id` (Django `CASCADE`) | `1` |
| `staff_id` | `bigint` | NO | — | FK → `tixelise_staff_staffprofile.id` (Django `CASCADE`) | `1` |
| `tenant_id` | `bigint` | NO | — | FK → `tixelise_tenancy_tenant.id` (Django `PROTECT`) | `1` |

**Indexes / constraints**
- `sqlite_autoindex_tixelise_assignments_staffeventassignment_1` — UNIQUE (`tenant_id`, `staff_id`, `event_id`) (`uniq_tenant_staff_event`)
- `assignments_staffeventassignment_tenant_id_4fe9ce8b` — INDEX (`tenant_id`)
- `assignments_staffeventassignment_staff_id_ce5bace9` — INDEX (`staff_id`)
- `assignments_staffeventassignment_event_id_4145ad0c` — INDEX (`event_id`)
- `assignments_staffeventassignment_created_by_id_1803c9d8` — INDEX (`created_by_id`)
- `assignments_staffeventassignment_status_34b9ea00` — INDEX (`status`)

**Relationships:** many assignments → one tenant, one staff profile, one event, one creator (nullable); one assignment → many allowed-category link rows.

**Example row**
```json
{
  "id": 1,
  "status": "active",
  "valid_from": null,
  "valid_until": null,
  "restrict_categories": 0,
  "created_at": "2026-10-20 08:00:39.842409",
  "updated_at": "2026-10-20 08:00:39.842426",
  "created_by_id": 2,
  "event_id": 1,
  "staff_id": 1,
  "tenant_id": 1
}
```

---

### 12. `tixelise_assignments_staffeventassignment_allowed_categories`

**Django model:** auto-created M2M table for `StaffEventAssignment.allowed_categories`.
**Rows:** 0 (illustrative example below)

| Column | SQLite type | Null | Default | Key / constraint | Example |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `staffeventassignment_id` | `bigint` | NO | — | FK → `tixelise_assignments_staffeventassignment.id` (Django `CASCADE`) | `1` |
| `ticketcategory_id` | `bigint` | NO | — | FK → `tixelise_catalog_ticketcategory.id` (Django `CASCADE`) | `1` |

**Indexes / constraints**
- `tixelise_assignments_staffeventassignment_allowed_categories_staffeventassignment_id_ticketcategory_id_451963b6_uniq` — UNIQUE (`staffeventassignment_id`, `ticketcategory_id`)
- `tixelise_assignments_staffeventassignment_allowed_categories_ticketcategory_id_b1c07525` — INDEX (`ticketcategory_id`)
- `tixelise_assignments_staffeventassignment_allowed_categories_staffeventassignment_id_0fec310d` — INDEX (`staffeventassignment_id`)

**Relationships:** many link rows → one assignment, one ticket category.

**Example row (illustrative)**
```json
{ "id": 1, "staffeventassignment_id": 1, "ticketcategory_id": 1 }
```

---

### 13. `tixelise_sales_sale`

**Django model:** `sales.Sale` — one completed POS transaction.
**Rows:** 2

| Column | SQLite type | Null | Default | Key / constraint | Example (id=1) |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `sale_reference` | `varchar(64)` | NO | — | UNIQUE per tenant | `DREAMS001-S-6800898B` |
| `status` | `varchar(16)` | NO | `completed` (Django) | values: `completed`, `voided`, `refunded`; indexed | `completed` |
| `gross_total` | `decimal` | NO | — | — | `998` |
| `refund_total` | `decimal` | NO | `0` (Django) | — | `0` |
| `currency` | `varchar(8)` | NO | `INR` (Django) | — | `INR` |
| `created_at` | `datetime` | NO | auto now (Django) | indexed | `2026-10-20 08:01:28.586448` |
| `updated_at` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:01:28.586459` |
| `created_by_id` | `bigint` | YES | `NULL` | FK → `tixelise_accounts_user.id` (Django `SET_NULL`) | `3` |
| `event_id` | `bigint` | NO | — | FK → `tixelise_events_event.id` (Django `PROTECT`) | `1` |
| `staff_id` | `bigint` | NO | — | FK → `tixelise_staff_staffprofile.id` (Django `PROTECT`) | `1` |
| `tenant_id` | `bigint` | NO | — | FK → `tixelise_tenancy_tenant.id` (Django `PROTECT`) | `1` |

**Indexes / constraints**
- `sqlite_autoindex_tixelise_sales_sale_1` — UNIQUE (`tenant_id`, `sale_reference`) (`uniq_tenant_sale_reference`)
- `sales_sale_tenant_id_c7dcc438` — INDEX (`tenant_id`)
- `sales_sale_staff_id_507ba9d1` — INDEX (`staff_id`)
- `sales_sale_event_id_ca8c5974` — INDEX (`event_id`)
- `sales_sale_created_by_id_f6773268` — INDEX (`created_by_id`)
- `sales_sale_created_at_bf202e70` — INDEX (`created_at`)
- `sales_sale_status_7ba038f2` — INDEX (`status`)

**Relationships:** many sales → one tenant, one event, one staff profile, one creator (nullable); one sale → many sale items, tickets, idempotency records.

**Example row**
```json
{
  "id": 1,
  "sale_reference": "DREAMS001-S-6800898B",
  "status": "completed",
  "gross_total": 998,
  "refund_total": 0,
  "currency": "INR",
  "created_at": "2026-10-20 08:01:28.586448",
  "updated_at": "2026-10-20 08:01:28.586459",
  "created_by_id": 3,
  "event_id": 1,
  "staff_id": 1,
  "tenant_id": 1
}
```

---

### 14. `tixelise_sales_saleitem`

**Django model:** `sales.SaleItem` — one line inside a sale, with a price snapshot.
**Rows:** 3

| Column | SQLite type | Null | Default | Key / constraint | Example (id=1) |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `quantity` | `integer unsigned` | NO | — | CHECK `quantity >= 0` | `2` |
| `unit_price_snapshot` | `decimal` | NO | — | price at sale time | `499` |
| `line_total` | `decimal` | NO | — | `unit_price_snapshot × quantity` | `998` |
| `category_id` | `bigint` | NO | — | FK → `tixelise_catalog_ticketcategory.id` (Django `PROTECT`) | `1` |
| `sale_id` | `bigint` | NO | — | FK → `tixelise_sales_sale.id` (Django `CASCADE`) | `1` |

**Indexes / constraints**
- `sales_saleitem_sale_id_56e67045` — INDEX (`sale_id`)
- `sales_saleitem_category_id_7cb49e15` — INDEX (`category_id`)
- CHECK: `quantity >= 0`

**Relationships:** many sale items → one sale, one ticket category. No direct `tenant_id`; tenancy is reached through the parent sale.

**Example row**
```json
{
  "id": 1,
  "quantity": 2,
  "unit_price_snapshot": 499,
  "line_total": 998,
  "category_id": 1,
  "sale_id": 1
}
```

---

### 15. `tixelise_sales_idempotencyrecord`

**Django model:** `sales.IdempotencyRecord` — deduplicates retried sale requests.
**Rows:** 2

| Column | SQLite type | Null | Default | Key / constraint | Example (id=1) |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `idempotency_key` | `varchar(128)` | NO | — | part of tenant+actor unique key | `smoke-1` |
| `request_hash` | `varchar(64)` | NO | — | SHA-256 of canonical request | `3588a50e3d70c5de933de845a5a086507a73f94422aa638791157cc102f23711` |
| `status` | `varchar(16)` | NO | `completed` (Django) | values: `completed` | `completed` |
| `created_at` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:01:28.589209` |
| `expires_at` | `datetime` | NO | — | — | `2026-10-27 08:01:28.581962` |
| `actor_id` | `bigint` | NO | — | FK → `tixelise_accounts_user.id` (Django `CASCADE`) | `3` |
| `tenant_id` | `bigint` | NO | — | FK → `tixelise_tenancy_tenant.id` (Django `PROTECT`) | `1` |
| `sale_id` | `bigint` | YES | `NULL` | FK → `tixelise_sales_sale.id` (Django `SET_NULL`) | `1` |

**Indexes / constraints**
- `sqlite_autoindex_tixelise_sales_idempotencyrecord_1` — UNIQUE (`tenant_id`, `actor_id`, `idempotency_key`) (`uniq_tenant_actor_idempotency_key`)
- `tixelise_sa_tenant__3e03bf_idx` — INDEX (`tenant_id`, `actor_id`, `idempotency_key`)
- `sales_idempotencyrecord_sale_id_8687d39b` — INDEX (`sale_id`)
- `sales_idempotencyrecord_tenant_id_51c5f0f7` — INDEX (`tenant_id`)
- `sales_idempotencyrecord_actor_id_3e682653` — INDEX (`actor_id`)

**Relationships:** many records → one tenant, one actor (user), one sale (nullable).

**Example row**
```json
{
  "id": 1,
  "idempotency_key": "smoke-1",
  "request_hash": "3588a50e3d70c5de933de845a5a086507a73f94422aa638791157cc102f23711",
  "status": "completed",
  "created_at": "2026-10-20 08:01:28.589209",
  "expires_at": "2026-10-27 08:01:28.581962",
  "actor_id": 3,
  "tenant_id": 1,
  "sale_id": 1
}
```

---

### 16. `tixelise_ticketing_ticketsequence`

**Django model:** `ticketing.TicketSequence` — atomic per-`(tenant, event)` ticket counter.
**Rows:** 2

| Column | SQLite type | Null | Default | Key / constraint | Example (id=1) |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `last_number` | `bigint` | NO | `0` (Django) | last allocated sequence number | `2` |
| `updated_at` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:01:28.585821` |
| `event_id` | `bigint` | NO | — | FK → `tixelise_events_event.id` (Django `PROTECT`) | `1` |
| `tenant_id` | `bigint` | NO | — | FK → `tixelise_tenancy_tenant.id` (Django `PROTECT`) | `1` |

**Indexes / constraints**
- `sqlite_autoindex_tixelise_ticketing_ticketsequence_1` — UNIQUE (`tenant_id`, `event_id`) (`uniq_tenant_event_sequence`)
- `ticketing_ticketsequence_tenant_id_30d26159` — INDEX (`tenant_id`)
- `ticketing_ticketsequence_event_id_326b4fb5` — INDEX (`event_id`)

**Relationships:** many sequences → one tenant, one event. Exactly one sequence row per `(tenant, event)`.

**Example row**
```json
{
  "id": 1,
  "last_number": 2,
  "updated_at": "2026-10-20 08:01:28.585821",
  "event_id": 1,
  "tenant_id": 1
}
```

---

### 17. `tixelise_ticketing_ticket`

**Django model:** `ticketing.Ticket` — an issued ticket with a globally unique printable code.
**Rows:** 5

| Column | SQLite type | Null | Default | Key / constraint | Example (id=`4e323af2...`) |
|---|---|---|---|---|---|
| `id` | `char(32)` | NO | UUID (Django) | PRIMARY KEY (UUID hex in SQLite) | `4e323af2f74642149db492de9cb4f9a2` |
| `ticket_code` | `varchar(120)` | NO | — | UNIQUE | `DREAMS001-ST012-EV004-20261020T080128Z-000001` |
| `sequence_number` | `bigint` | NO | — | UNIQUE per `(tenant, event)` | `1` |
| `status` | `varchar(16)` | NO | `issued` (Django) | values: `issued`, `voided`, `refunded` | `issued` |
| `issued_at` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:01:28.588120` |
| `reprint_count` | `integer unsigned` | NO | `0` (Django) | CHECK `reprint_count >= 0` | `0` |
| `category_id` | `bigint` | NO | — | FK → `tixelise_catalog_ticketcategory.id` (Django `PROTECT`) | `1` |
| `event_id` | `bigint` | NO | — | FK → `tixelise_events_event.id` (Django `PROTECT`) | `1` |
| `sale_id` | `bigint` | NO | — | FK → `tixelise_sales_sale.id` (Django `PROTECT`) | `1` |
| `staff_id` | `bigint` | NO | — | FK → `tixelise_staff_staffprofile.id` (Django `PROTECT`) | `1` |
| `tenant_id` | `bigint` | NO | — | FK → `tixelise_tenancy_tenant.id` (Django `PROTECT`) | `1` |

**Indexes / constraints**
- `sqlite_autoindex_tixelise_ticketing_ticket_3` — UNIQUE (`tenant_id`, `event_id`, `sequence_number`) (`uniq_tenant_event_sequence_number`)
- `sqlite_autoindex_tixelise_ticketing_ticket_2` — UNIQUE (`ticket_code`)
- `sqlite_autoindex_tixelise_ticketing_ticket_1` — UNIQUE (`id`) (primary key)
- `ticketing_ticket_tenant_id_2e18404d` — INDEX (`tenant_id`)
- `ticketing_ticket_staff_id_d8681ca8` — INDEX (`staff_id`)
- `ticketing_ticket_sale_id_09a627e2` — INDEX (`sale_id`)
- `ticketing_ticket_event_id_3bec6590` — INDEX (`event_id`)
- `ticketing_ticket_category_id_4a4e72ce` — INDEX (`category_id`)
- CHECK: `reprint_count >= 0`

**Relationships:** many tickets → one tenant, one event, one staff profile, one sale, one ticket category.

**Example row** (Django renders `id` as `4e323af2-f746-4214-9db4-92de9cb4f9a2`)
```json
{
  "id": "4e323af2f74642149db492de9cb4f9a2",
  "ticket_code": "DREAMS001-ST012-EV004-20261020T080128Z-000001",
  "sequence_number": 1,
  "status": "issued",
  "issued_at": "2026-10-20 08:01:28.588120",
  "reprint_count": 0,
  "category_id": 1,
  "event_id": 1,
  "sale_id": 1,
  "staff_id": 1,
  "tenant_id": 1
}
```

---

### 18. `tixelise_audit_auditlog`

**Django model:** `audit.AuditLog` — append-only audit trail (passwords/tokens never recorded).
**Rows:** 134

| Column | SQLite type | Null | Default | Key / constraint | Example (id=2) |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `2` |
| `actor_label` | `varchar(255)` | NO | `""` (Django) | username snapshot | `ravi` |
| `action` | `varchar(100)` | NO | — | indexed | `sale.created` |
| `target_type` | `varchar(100)` | NO | `""` (Django) | — | `sale` |
| `target_id` | `varchar(64)` | NO | `""` (Django) | string id of target | `"1"` |
| `correlation_id` | `varchar(64)` | NO | `""` (Django) | indexed | `c4017ce7-754e-41b7-ba2e-01a0aea65365` |
| `metadata` | `text` | NO | `{}` (Django) | JSON check: `JSON_VALID(metadata) OR metadata IS NULL` | `{"sale_reference": "DREAMS001-S-6800898B", ...}` |
| `created_at` | `datetime` | NO | auto now (Django) | indexed | `2026-10-20 08:01:28.589730` |
| `actor_id` | `bigint` | YES | `NULL` | FK → `tixelise_accounts_user.id` (Django `SET_NULL`) | `3` |
| `tenant_id` | `bigint` | YES | `NULL` | FK → `tixelise_tenancy_tenant.id` (Django `SET_NULL`) | `1` |

**Indexes / constraints**
- `audit_auditlog_tenant_id_6a956a1c` — INDEX (`tenant_id`)
- `audit_auditlog_actor_id_20e70a27` — INDEX (`actor_id`)
- `audit_auditlog_created_at_5c532845` — INDEX (`created_at`)
- `audit_auditlog_correlation_id_9d3c0d74` — INDEX (`correlation_id`)
- `audit_auditlog_action_dc562e21` — INDEX (`action`)
- CHECK: `JSON_VALID(metadata) OR metadata IS NULL`

**Relationships:** many audit rows → one tenant (nullable), one actor (nullable). Nullable on purpose so platform-wide events and deleted users/tenants remain recorded.

**Example row**
```json
{
  "id": 2,
  "actor_label": "ravi",
  "action": "sale.created",
  "target_type": "sale",
  "target_id": "1",
  "correlation_id": "c4017ce7-754e-41b7-ba2e-01a0aea65365",
  "metadata": {
    "sale_reference": "DREAMS001-S-6800898B",
    "event": "EV004",
    "staff": "ST012",
    "tickets": 2,
    "gross_total": "998.00"
  },
  "created_at": "2026-10-20 08:01:28.589730",
  "actor_id": 3,
  "tenant_id": 1
}
```

---

## 3. Django framework tables

These 7 tables are created and maintained by Django. They keep standard names (no `_tixelise` suffix).

### 19. `auth_group`

**Django model:** `auth.Group`.
**Rows:** 0 (illustrative example below)

| Column | SQLite type | Null | Default | Key / constraint | Example |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `name` | `varchar(150)` | NO | — | UNIQUE | `POS Managers` |

**Indexes / constraints**
- `sqlite_autoindex_auth_group_1` — UNIQUE (`name`)

**Relationships:** many groups ↔ many users through `tixelise_accounts_user_groups`; many groups ↔ many permissions through `auth_group_permissions`.

**Example row (illustrative)**
```json
{ "id": 1, "name": "POS Managers" }
```

---

### 20. `auth_group_permissions`

**Django model:** auto-created M2M table for `auth.Group.permissions`.
**Rows:** 0 (illustrative example below)

| Column | SQLite type | Null | Default | Key / constraint | Example |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `group_id` | `INTEGER` | NO | — | FK → `auth_group.id` (Django `CASCADE`) | `1` |
| `permission_id` | `INTEGER` | NO | — | FK → `auth_permission.id` (Django `CASCADE`) | `1` |

**Indexes / constraints**
- `auth_group_permissions_group_id_permission_id_0cd325b0_uniq` — UNIQUE (`group_id`, `permission_id`)
- `auth_group_permissions_permission_id_84c5c92e` — INDEX (`permission_id`)
- `auth_group_permissions_group_id_b120cbf9` — INDEX (`group_id`)

**Relationships:** many link rows → one group, one permission.

**Example row (illustrative)**
```json
{ "id": 1, "group_id": 1, "permission_id": 1 }
```

---

### 21. `auth_permission`

**Django model:** `auth.Permission`.
**Rows:** 80

| Column | SQLite type | Null | Default | Key / constraint | Example (id=1) |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `content_type_id` | `INTEGER` | NO | — | FK → `django_content_type.id` (Django `CASCADE`) | `1` |
| `codename` | `varchar(100)` | NO | — | UNIQUE per content type | `add_logentry` |
| `name` | `varchar(255)` | NO | — | — | `Can add log entry` |

**Indexes / constraints**
- `auth_permission_content_type_id_codename_01ab375a_uniq` — UNIQUE (`content_type_id`, `codename`)
- `auth_permission_content_type_id_2f476e4b` — INDEX (`content_type_id`)

**Relationships:** many permissions → one content type; many permissions ↔ many groups through `auth_group_permissions`; many permissions ↔ many users through `tixelise_accounts_user_user_permissions`.

**Example row**
```json
{
  "id": 1,
  "content_type_id": 1,
  "codename": "add_logentry",
  "name": "Can add log entry"
}
```

---

### 22. `django_admin_log`

**Django model:** `admin.LogEntry`.
**Rows:** 0 (illustrative example below)

| Column | SQLite type | Null | Default | Key / constraint | Example |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `object_id` | `text` | YES | `NULL` | — | `"1"` |
| `object_repr` | `varchar(200)` | NO | — | — | `DREAMS001` |
| `action_flag` | `smallint unsigned` | NO | — | CHECK `action_flag >= 0` | `1` |
| `change_message` | `text` | NO | — | — | `[{"changed": {"fields": ["name"]}}]` |
| `content_type_id` | `INTEGER` | YES | `NULL` | FK → `django_content_type.id` (Django `SET_NULL`) | `1` |
| `user_id` | `bigint` | NO | — | FK → `tixelise_accounts_user.id` (Django `CASCADE`) | `1` |
| `action_time` | `datetime` | NO | auto now (Django) | — | `2026-10-20 08:30:00` |

**Indexes / constraints**
- `django_admin_log_user_id_c564eba6` — INDEX (`user_id`)
- `django_admin_log_content_type_id_c4bce8eb` — INDEX (`content_type_id`)
- CHECK: `action_flag >= 0`

**Relationships:** many log entries → one user (required), one content type (nullable).

**Example row (illustrative)**
```json
{
  "id": 1,
  "object_id": "1",
  "object_repr": "DREAMS001",
  "action_flag": 1,
  "change_message": "[{\"changed\": {\"fields\": [\"name\"]}}]",
  "content_type_id": 1,
  "user_id": 1,
  "action_time": "2026-10-20 08:30:00"
}
```

---

### 23. `django_content_type`

**Django model:** `contenttypes.ContentType`.
**Rows:** 20

| Column | SQLite type | Null | Default | Key / constraint | Example (id=1) |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `app_label` | `varchar(100)` | NO | — | UNIQUE per model | `admin` |
| `model` | `varchar(100)` | NO | — | UNIQUE per app label | `logentry` |

**Indexes / constraints**
- `django_content_type_app_label_model_76bd3d3b_uniq` — UNIQUE (`app_label`, `model`)

**Relationships:** one content type → many permissions; one content type → many admin log entries.

**Example row**
```json
{ "id": 1, "app_label": "admin", "model": "logentry" }
```

---

### 24. `django_migrations`

**Django model:** migration history (schema only, not business data).
**Rows:** 36

| Column | SQLite type | Null | Default | Key / constraint | Example (id=1) |
|---|---|---|---|---|---|
| `id` | `INTEGER` | NO | autoincrement | PRIMARY KEY | `1` |
| `app` | `varchar(255)` | NO | — | — | `contenttypes` |
| `name` | `varchar(255)` | NO | — | — | `0001_initial` |
| `applied` | `datetime` | NO | — | — | `2026-10-20 08:00:05.001099` |

**Indexes / constraints**
- No indexes beyond the primary key.

**Relationships:** none.

**Example row**
```json
{
  "id": 1,
  "app": "contenttypes",
  "name": "0001_initial",
  "applied": "2026-10-20 08:00:05.001099"
}
```

---

### 25. `django_session`

**Django model:** server-side session store.
**Rows:** 2

| Column | SQLite type | Null | Default | Key / constraint | Example |
|---|---|---|---|---|---|
| `session_key` | `varchar(40)` | NO | — | PRIMARY KEY | `ajpsgmi5r3yxmu2yv64kl38ffnj8spv6` |
| `session_data` | `text` | NO | — | encoded session payload | `<masked session payload>` |
| `expire_date` | `datetime` | NO | — | indexed | `2026-11-03 08:30:07.757647` |

**Indexes / constraints**
- `sqlite_autoindex_django_session_1` — UNIQUE (`session_key`) (primary key)
- `django_session_expire_date_a5c62663` — INDEX (`expire_date`)

**Relationships:** no foreign keys; sessions are not linked to a user column.

**Example row**
```json
{
  "session_key": "ajpsgmi5r3yxmu2yv64kl38ffnj8spv6",
  "session_data": "<masked session payload>",
  "expire_date": "2026-11-03 08:30:07.757647"
}
```

---

## 4. Quick integrity summary

| Rule | Tables involved |
|---|---|
| Tenancy root | `tixelise_tenancy_tenant` |
| User ↔ tenant role | `tixelise_tenancy_tenantmembership` (`UNIQUE tenant_id, user_id`) |
| Event code unique per tenant | `tixelise_events_event` (`UNIQUE tenant_id, code`) |
| Category code unique per tenant | `tixelise_catalog_ticketcategory` (`UNIQUE tenant_id, code`) |
| Price unique per event+category | `tixelise_catalog_eventprice` (`UNIQUE tenant_id, event_id, category_id`) |
| Staff code unique per tenant | `tixelise_staff_staffprofile` (`UNIQUE tenant_id, staff_code`) |
| One staff profile per user per tenant | `tixelise_staff_staffprofile` (`UNIQUE tenant_id, user_id`) |
| One assignment per staff+event | `tixelise_assignments_staffeventassignment` (`UNIQUE tenant_id, staff_id, event_id`) |
| Sale reference unique per tenant | `tixelise_sales_sale` (`UNIQUE tenant_id, sale_reference`) |
| Idempotency key unique per tenant+actor | `tixelise_sales_idempotencyrecord` (`UNIQUE tenant_id, actor_id, idempotency_key`) |
| One ticket counter per tenant+event | `tixelise_ticketing_ticketsequence` (`UNIQUE tenant_id, event_id`) |
| Ticket sequence unique per tenant+event | `tixelise_ticketing_ticket` (`UNIQUE tenant_id, event_id, sequence_number`) |
| Ticket code globally unique | `tixelise_ticketing_ticket` (`UNIQUE ticket_code`) |
| Non-negative money/quantity/count | `tixelise_catalog_eventprice`, `tixelise_sales_saleitem`, `tixelise_ticketing_ticket` |
| Valid JSON storage | `tixelise_tenancy_tenant.settings`, `tixelise_catalog_tickettemplate.config`, `tixelise_audit_auditlog.metadata` |
| Event time sanity | `tixelise_events_event` (`end_at > start_at`) |
