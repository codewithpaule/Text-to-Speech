from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'reference_number', 'status', 'date')
    search_fields = ('reference_number', 'user__email')
    list_filter = ('status',)
