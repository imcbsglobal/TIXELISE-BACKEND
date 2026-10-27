from django.contrib import admin

from .models import IdempotencyRecord, Sale, SaleItem


admin.site.register([Sale, SaleItem, IdempotencyRecord])
