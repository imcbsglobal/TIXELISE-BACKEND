from django.contrib import admin

from .models import EventPrice, TicketCategory, TicketTemplate


admin.site.register([TicketCategory, EventPrice, TicketTemplate])
