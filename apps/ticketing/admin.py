from django.contrib import admin

from .models import Ticket, TicketSequence


admin.site.register([TicketSequence, Ticket])
