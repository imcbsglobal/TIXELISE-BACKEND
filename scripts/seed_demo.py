"""
Seeds a complete demo world matching the MD flow:

  platform admin -> tenant DREAMS001 -> tenant admin -> staff -> event -> prices -> assignment

Run from the backend/ directory:

    python scripts/seed_demo.py
"""
import os
import sys
from datetime import timedelta
from decimal import Decimal

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from django.utils import timezone  # noqa: E402

from apps.accounts.models import User  # noqa: E402
from apps.assignments.models import StaffEventAssignment  # noqa: E402
from apps.catalog.models import EventPrice, TicketCategory  # noqa: E402
from apps.events.models import Event  # noqa: E402
from apps.staff.models import StaffProfile  # noqa: E402
from apps.tenancy.models import Tenant, TenantMembership  # noqa: E402


def get_or_create(klass, defaults=None, **kwargs):
    obj, created = klass.objects.get_or_create(defaults=defaults or {}, **kwargs)
    label = f"{klass._meta.model_name} #{obj.pk}"
    print(("+ created " if created else "= exists   ") + label)
    return obj


def main():
    # 1. Platform admin (login WITHOUT tenant code)
    platform_user, created = User.objects.get_or_create(
        username="platform",
        defaults={"is_platform_admin": True, "is_staff": True},
    )
    if created:
        platform_user.set_password("Platform@123")
        platform_user.save()
    print(("+ created " if created else "= exists   ") + "platform admin 'platform'")

    # 2. Tenant
    tenant = get_or_create(
        Tenant,
        defaults={
            "name": "Dreams Events",
            "timezone": "Asia/Kolkata",
            "currency": "INR",
        },
        code="DREAMS001",
    )

    # 3. Tenant admin
    admin_user, created = User.objects.get_or_create(
        username="admin",
        defaults={"email": "admin@dreams.example"},
    )
    if created:
        admin_user.set_password("Admin@123")
        admin_user.save()
    get_or_create(
        TenantMembership,
        defaults={"role": "tenant_admin"},
        tenant=tenant,
        user=admin_user,
    )

    # 4. Staff + membership
    staff_user, created = User.objects.get_or_create(
        username="ravi", defaults={"email": "ravi@dreams.example"}
    )
    if created:
        staff_user.set_password("Staff@123")
        staff_user.save()
    get_or_create(
        TenantMembership,
        defaults={"role": "pos_staff"},
        tenant=tenant,
        user=staff_user,
    )
    staff = get_or_create(
        StaffProfile,
        defaults={
            "display_name": "Ravi Kumar",
            "created_by": admin_user,
            "user": staff_user,
        },
        tenant=tenant,
        staff_code="ST012",
    )

    # 5. Categories (tenant-level reusable)
    adult = get_or_create(
        TicketCategory, defaults={"name": "Adult"}, tenant=tenant, code="ADULT"
    )
    child = get_or_create(
        TicketCategory, defaults={"name": "Child"}, tenant=tenant, code="CHILD"
    )
    vip = get_or_create(
        TicketCategory, defaults={"name": "VIP"}, tenant=tenant, code="VIP"
    )

    # 6. Event
    now = timezone.now()
    event, created = Event.objects.get_or_create(
        tenant=tenant,
        code="EV004",
        defaults={
            "name": "Music Fest 2026",
            "venue": "Central Auditorium",
            "address": "Kochi, Kerala",
            "start_at": now + timedelta(days=7),
            "end_at": now + timedelta(days=7, hours=6),
            "sales_start_at": now,
            "sales_end_at": now + timedelta(days=7),
            "status": Event.Status.DRAFT,
            "created_by": admin_user,
        },
    )
    print(("+ created " if created else "= exists   ") + f"event {event.code}")

    # 7. Prices
    for category, amount in [(adult, "499.00"), (child, "199.00"), (vip, "1499.00")]:
        get_or_create(
            EventPrice,
            defaults={"amount": Decimal(amount), "currency": "INR"},
            tenant=tenant,
            event=event,
            category=category,
        )

    # 8. Assignment
    get_or_create(
        StaffEventAssignment,
        defaults={"created_by": admin_user},
        tenant=tenant,
        staff=staff,
        event=event,
    )

    # Activate the event so POS can sell immediately
    if event.status == Event.Status.DRAFT:
        event.status = Event.Status.ACTIVE
        event.save(update_fields=["status", "updated_at"])
        print(f"= event {event.code} activated")

    print(
        """
------------------------------------------------------------------
Demo credentials
  Platform (no tenant code):  platform / Platform@123
  Tenant admin  (DREAMS001):  admin     / Admin@123
  POS staff     (DREAMS001):  ravi      / Staff@123
------------------------------------------------------------------"""
    )


if __name__ == "__main__":
    main()
