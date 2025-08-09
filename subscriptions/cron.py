from datetime import timedelta
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from .models import Subscription


def send_renewal_reminders():
    now = timezone.now()
    upcoming = now + timedelta(days=3)
    expiring = Subscription.objects.filter(status='active', end_date__date=upcoming.date())
    for sub in expiring:
        send_mail(
            subject='Your subscription is expiring soon',
            message=f'Hi {sub.user.full_name or sub.user.email}, your {sub.plan.name} plan expires on {sub.end_date.date()}.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[sub.user.email],
            fail_silently=True,
        )