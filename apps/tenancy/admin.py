from django.contrib import admin

from .models import Tenant, TenantMembership


admin.site.register([Tenant, TenantMembership])
