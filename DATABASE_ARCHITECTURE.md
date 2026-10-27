# Tixelise Database Architecture

## 1. Current table inventory

The current SQLite database contains **25 tables**: **18 application tables**
and **7 Django framework tables**. Application tables use the `_tixelise`
suffix. Django framework table names are unchanged.

| # | Table name | Ownership |
|---:|---|---|
| 1 | `accounts_user_groups_tixelise` | Application |
| 2 | `accounts_user_tixelise` | Application |
| 3 | `accounts_user_user_permissions_tixelise` | Application |
| 4 | `assignments_staffeventassignment_allowed_categories_tixelise` | Application |
| 5 | `assignments_staffeventassignment_tixelise` | Application |
| 6 | `audit_auditlog_tixelise` | Application |
| 7 | `auth_group` | Django framework |
| 8 | `auth_group_permissions` | Django framework |
| 9 | `auth_permission` | Django framework |
| 10 | `catalog_eventprice_tixelise` | Application |
| 11 | `catalog_ticketcategory_tixelise` | Application |
| 12 | `catalog_tickettemplate_tixelise` | Application |
| 13 | `django_admin_log` | Django framework |
| 14 | `django_content_type` | Django framework |
| 15 | `django_migrations` | Django framework |
| 16 | `django_session` | Django framework |
| 17 | `events_event_tixelise` | Application |
| 18 | `sales_idempotencyrecord_tixelise` | Application |
| 19 | `sales_sale_tixelise` | Application |
| 20 | `sales_saleitem_tixelise` | Application |
| 21 | `staff_staffprofile_tixelise` | Application |
| 22 | `tenancy_tenant_tixelise` | Application |
| 23 | `tenancy_tenantmembership_tixelise` | Application |
| 24 | `ticketing_ticket_tixelise` | Application |
| 25 | `ticketing_ticketsequence_tixelise` | Application |

This inventory reflects the checked-in database file and models as of
2026-10-24. The database configured at runtime can differ when `DATABASE_URL`
points to another database.

## 2. Database and application architecture

```text
Browser / frontend
        |
        | HTTP API requests (JSON, JWT)
        v
Django REST Framework backend
        |
        | Django ORM / migrations
        v
One configured database ("default")
  - SQLite: backend/db.sqlite3 by default
  - PostgreSQL: when DATABASE_URL is configured
        |
        +-- Application tables (18, names end in _tixelise)
        +-- Django framework tables (7, standard names)
```

- The frontend communicates with the backend API; it does not connect directly
  to the database.
- Django models and migrations define and access application tables.
- By default, `backend/config/settings/base.py` configures one SQLite database
  at `backend/db.sqlite3`. Setting `DATABASE_URL` switches the default
  connection to the URL-configured database; the application does not create a
  separate database for each tenant.
- All tenants share the same database and tables. Tenant-owned rows are
  associated with `tenancy_tenant_tixelise` using `tenant_id`.
- Tenant identity is resolved by backend authentication and middleware from
  verified JWT claims. Tenant-aware managers scope tenant-owned model
  queries. This is application-level isolation, not a separate schema or
  database per tenant.
- Migrations change the database schema. The table-suffix migrations use
  Django model table alterations to rename application tables; they do not
  rename the Django framework tables.
- Django’s `django_migrations` table records which migrations were applied.

## 3. Entity relationship diagram

The diagram shows the principal foreign-key and many-to-many relationships.
`1` means one referenced record; `0..*` means zero or more related records.

```mermaid
erDiagram
    tenancy_tenant_tixelise ||--o{ tenancy_tenantmembership_tixelise : has
    accounts_user_tixelise ||--o{ tenancy_tenantmembership_tixelise : joins

    tenancy_tenant_tixelise ||--o{ events_event_tixelise : owns
    tenancy_tenant_tixelise ||--o{ catalog_ticketcategory_tixelise : owns
    tenancy_tenant_tixelise ||--o{ catalog_tickettemplate_tixelise : owns
    tenancy_tenant_tixelise ||--o{ catalog_eventprice_tixelise : owns
    tenancy_tenant_tixelise ||--o{ staff_staffprofile_tixelise : owns
    tenancy_tenant_tixelise ||--o{ assignments_staffeventassignment_tixelise : owns
    tenancy_tenant_tixelise ||--o{ sales_sale_tixelise : owns
    tenancy_tenant_tixelise ||--o{ sales_idempotencyrecord_tixelise : owns
    tenancy_tenant_tixelise ||--o{ ticketing_ticket_tixelise : owns
    tenancy_tenant_tixelise ||--o{ ticketing_ticketsequence_tixelise : owns
    tenancy_tenant_tixelise o|--o{ audit_auditlog_tixelise : scopes

    accounts_user_tixelise ||--o{ staff_staffprofile_tixelise : user_profile
    accounts_user_tixelise ||--o{ events_event_tixelise : created_by
    accounts_user_tixelise ||--o{ assignments_staffeventassignment_tixelise : created_by
    accounts_user_tixelise ||--o{ sales_sale_tixelise : created_by
    accounts_user_tixelise ||--o{ sales_idempotencyrecord_tixelise : actor
    accounts_user_tixelise o|--o{ audit_auditlog_tixelise : actor

    events_event_tixelise ||--o{ catalog_eventprice_tixelise : priced_by
    catalog_ticketcategory_tixelise ||--o{ catalog_eventprice_tixelise : priced_category
    events_event_tixelise ||--o{ assignments_staffeventassignment_tixelise : assigned_event
    staff_staffprofile_tixelise ||--o{ assignments_staffeventassignment_tixelise : assigned_staff
    assignments_staffeventassignment_tixelise ||--o{ assignments_staffeventassignment_allowed_categories_tixelise : category_links
    catalog_ticketcategory_tixelise ||--o{ assignments_staffeventassignment_allowed_categories_tixelise : allowed_category

    events_event_tixelise ||--o{ sales_sale_tixelise : sold_at
    staff_staffprofile_tixelise ||--o{ sales_sale_tixelise : sold_by
    sales_sale_tixelise ||--o{ sales_saleitem_tixelise : contains
    catalog_ticketcategory_tixelise ||--o{ sales_saleitem_tixelise : item_category
    sales_sale_tixelise o|--o{ sales_idempotencyrecord_tixelise : retries

    sales_sale_tixelise ||--o{ ticketing_ticket_tixelise : issues
    events_event_tixelise ||--o{ ticketing_ticket_tixelise : for_event
    staff_staffprofile_tixelise ||--o{ ticketing_ticket_tixelise : issued_by
    catalog_ticketcategory_tixelise ||--o{ ticketing_ticket_tixelise : ticket_category
    events_event_tixelise ||--o{ ticketing_ticketsequence_tixelise : sequence_for

    accounts_user_tixelise ||--o{ accounts_user_groups_tixelise : group_links
    auth_group ||--o{ accounts_user_groups_tixelise : user_group
    accounts_user_tixelise ||--o{ accounts_user_user_permissions_tixelise : permission_links
    auth_permission ||--o{ accounts_user_user_permissions_tixelise : user_permission
    auth_group ||--o{ auth_group_permissions : group_permission_links
    auth_permission ||--o{ auth_group_permissions : permission
    django_content_type ||--o{ auth_permission : defines
    accounts_user_tixelise ||--o{ django_admin_log : admin_actions
    django_content_type o|--o{ django_admin_log : logged_object_type
```

`django_session` and `django_migrations` are not connected to application
entities by foreign keys. Django sessions store session payloads, while
migration records describe applied schema changes.

## 4. Application table reference

`id` is the primary key unless specified otherwise. Columns ending in `_id`
are foreign-key columns. `NULL` means a relationship is optional.

### Tenancy and identity

| Table | Columns and relationships |
|---|---|
| `tenancy_tenant_tixelise` | `id`, `code` (unique), `name`, `status`, `timezone`, `currency`, `settings`, `created_at`, `updated_at`. Root record for a tenant and its tenant-owned data. |
| `accounts_user_tixelise` | `id`, `password` (Django password hash), `last_login`, `is_superuser`, `username` (unique), `first_name`, `last_name`, `email`, `is_staff`, `is_active`, `date_joined`, `is_platform_admin`. Global user identity; not itself tenant-owned. |
| `tenancy_tenantmembership_tixelise` | `id`, `tenant_id` → tenant, `user_id` → user, `role`, `status`, `created_at`, `updated_at`. Unique per `(tenant_id, user_id)`. Connects users to tenants and their roles. |
| `accounts_user_groups_tixelise` | `id`, `user_id` → user, `group_id` → `auth_group`. Many-to-many link between users and Django groups. |
| `accounts_user_user_permissions_tixelise` | `id`, `user_id` → user, `permission_id` → `auth_permission`. Many-to-many link between users and individual permissions. |

### Events, catalog, staff, and assignments

| Table | Columns and relationships |
|---|---|
| `events_event_tixelise` | `id`, `tenant_id` → tenant, `code`, `name`, `description`, `venue`, `address`, `start_at`, `end_at`, `sales_start_at`, `sales_end_at`, `status`, nullable `created_by_id` → user, `created_at`, `updated_at`. Unique per `(tenant_id, code)`; `end_at` must be after `start_at`. |
| `catalog_ticketcategory_tixelise` | `id`, `tenant_id` → tenant, `code`, `name`, `description`, `status`, `created_at`, `updated_at`. Unique per `(tenant_id, code)`. |
| `catalog_eventprice_tixelise` | `id`, `tenant_id` → tenant, `event_id` → event, `category_id` → ticket category, `amount`, `currency`, `effective_from`, `effective_to`, `status`, `created_at`, `updated_at`. Unique per `(tenant_id, event_id, category_id)`; `amount` must be non-negative. |
| `catalog_tickettemplate_tixelise` | `id`, `tenant_id` → tenant, `name`, `config`, `version`, `status`, `created_at`, `updated_at`. Stores tenant-specific ticket layout/configuration data. |
| `staff_staffprofile_tixelise` | `id`, `tenant_id` → tenant, `user_id` → user, `staff_code`, `display_name`, `phone`, `email`, `status`, nullable `created_by_id` → user, `created_at`, `updated_at`, `last_login`. Unique per `(tenant_id, staff_code)` and `(tenant_id, user_id)`. |
| `assignments_staffeventassignment_tixelise` | `id`, `tenant_id` → tenant, `staff_id` → staff profile, `event_id` → event, `status`, `valid_from`, `valid_until`, `restrict_categories`, nullable `created_by_id` → user, `created_at`, `updated_at`. Unique per `(tenant_id, staff_id, event_id)`. |
| `assignments_staffeventassignment_allowed_categories_tixelise` | `id`, `staffeventassignment_id` → assignment, `ticketcategory_id` → ticket category. Many-to-many list of categories allowed by an assignment. |

### Sales, tickets, and audit

| Table | Columns and relationships |
|---|---|
| `sales_sale_tixelise` | `id`, `tenant_id` → tenant, `sale_reference`, `event_id` → event, `staff_id` → staff profile, `status`, `gross_total`, `refund_total`, `currency`, nullable `created_by_id` → user, `created_at`, `updated_at`. Unique per `(tenant_id, sale_reference)`. |
| `sales_saleitem_tixelise` | `id`, `sale_id` → sale, `category_id` → ticket category, `quantity`, `unit_price_snapshot`, `line_total`. Each line belongs to a sale and captures the price at sale time. It has no direct tenant foreign key; tenant ownership is reached through its sale. |
| `sales_idempotencyrecord_tixelise` | `id`, `tenant_id` → tenant, `actor_id` → user, `idempotency_key`, `request_hash`, nullable `sale_id` → sale, `status`, `created_at`, `expires_at`. Unique per `(tenant_id, actor_id, idempotency_key)`. |
| `ticketing_ticketsequence_tixelise` | `id`, `tenant_id` → tenant, `event_id` → event, `last_number`, `updated_at`. Unique per `(tenant_id, event_id)`; stores the next ticket-number state for an event. |
| `ticketing_ticket_tixelise` | UUID `id` (primary key), `tenant_id` → tenant, `ticket_code` (unique), `event_id` → event, `staff_id` → staff profile, `sale_id` → sale, `category_id` → ticket category, `sequence_number`, `status`, `issued_at`, `reprint_count`. Unique per `(tenant_id, event_id, sequence_number)`. |
| `audit_auditlog_tixelise` | `id`, nullable `tenant_id` → tenant, nullable `actor_id` → user, `actor_label`, `action`, `target_type`, `target_id`, `correlation_id`, `metadata`, `created_at`. Nullable tenant and actor allow platform-wide events or records whose related user/tenant is removed. |

## 5. Django framework table reference

These tables are maintained by Django and keep their standard names.

| Table | Purpose and principal relationships |
|---|---|
| `auth_group` | Django permission groups. Linked to users through `accounts_user_groups_tixelise` and to permissions through `auth_group_permissions`. |
| `auth_group_permissions` | Many-to-many join table: `group_id` → `auth_group`, `permission_id` → `auth_permission`. |
| `auth_permission` | Permission definitions. `content_type_id` → `django_content_type`; linked to groups and users through their join tables. |
| `django_admin_log` | Django admin history. `user_id` → application user; nullable `content_type_id` → `django_content_type`. |
| `django_content_type` | Registry of Django application/model types; used by permissions and admin log entries. |
| `django_migrations` | Applied migration records (`app`, `name`, `applied`). It is schema history, not business data. |
| `django_session` | Server-side Django sessions (`session_key`, `session_data`, `expire_date`). No direct user foreign key. |

## 6. Relationship and tenancy notes

- **Tenant root:** `tenancy_tenant_tixelise` is the ownership root for tenant
  records. Events, catalog records, staff profiles, assignments, sales,
  idempotency records, tickets, and ticket sequences carry a `tenant_id`.
- **Membership:** `tenancy_tenantmembership_tixelise` joins a global user to a
  tenant and stores the user's tenant role and membership status. A user can
  have memberships in multiple tenants.
- **Identity versus staff:** `accounts_user_tixelise` represents a login
  identity. `staff_staffprofile_tixelise` represents that user's staff role in
  a particular tenant. A user can have staff profiles in different tenants.
- **Event/catalog:** Event prices connect a tenant, event, and ticket category.
  Ticket categories can be reused across events within a tenant.
- **Assignment:** An assignment joins one staff profile to one event. Its
  category join table optionally limits which ticket categories the staff
  member may sell for that event.
- **Sale lifecycle:** A sale belongs to a tenant, event, and staff profile.
  Sale items store quantities and price snapshots. Tickets point to their
  sale, event, staff member, ticket category, and tenant.
- **Ticket numbering:** Ticket sequence rows are scoped to a `(tenant, event)`
  pair. Ticket rows enforce uniqueness for `(tenant, event, sequence_number)`.
- **Deletion behavior:** Foreign-key deletion policies are defined in Django
  models (for example `PROTECT`, `CASCADE`, and `SET_NULL`). Consult the
  corresponding model before deleting business records; do not assume every
  relationship cascades.
- **Tenant boundaries:** `tenant_id` relationships establish ownership, while
  request authentication, tenant context, and tenant-scoped queries enforce
  access boundaries. A database foreign key alone does not enforce that two
  referenced records belong to the same tenant.

## 7. Schema maintenance

Use migrations rather than manually renaming or editing database tables:

```powershell
cd backend
.venv\Scripts\python manage.py showmigrations
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py makemigrations --check --dry-run
```

To inspect the current SQLite table names:

```powershell
cd backend
.venv\Scripts\python list_tables2.py
```

The inventory above is a point-in-time reference. When models or migrations
change, update this document and verify the live schema against the migration
state.
