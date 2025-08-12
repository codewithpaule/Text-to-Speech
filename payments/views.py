import secrets
from decimal import Decimal
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
import requests

from .models import Payment
from subscriptions.models import Subscription, Plan


@login_required
@require_POST
def initialize_payment(request):
    plan_id = request.POST.get('plan_id')
    try:
        plan = Plan.objects.get(id=plan_id)
    except Plan.DoesNotExist:
        return HttpResponseBadRequest('Invalid plan')

    reference = secrets.token_hex(12)
    amount_kobo = int(Decimal(plan.price) * 100)

    payment = Payment.objects.create(user=request.user, amount=plan.price, reference_number=reference)

    init_url = 'https://api.paystack.co/transaction/initialize'
    headers = {'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}'}
    data = {
        'email': request.user.email,
        'amount': amount_kobo,
        'reference': reference,
        'callback_url': request.build_absolute_uri('/payments/verify/')
    }
    res = requests.post(init_url, json=data, headers=headers, timeout=30)
    try:
        res.raise_for_status()
        auth_url = res.json()['data']['authorization_url']
        return JsonResponse({'authorization_url': auth_url, 'reference': reference})
    except Exception:
        payment.status = 'failed'
        payment.save(update_fields=['status'])
        return HttpResponseBadRequest('Failed to initialize payment')


def verify_payment(request):
    reference = request.GET.get('reference') or request.POST.get('reference')
    if not reference:
        return HttpResponseBadRequest('Missing reference')
    verify_url = f'https://api.paystack.co/transaction/verify/{reference}'
    headers = {'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}'}
    res = requests.get(verify_url, headers=headers, timeout=30)
    try:
        res.raise_for_status()
        data = res.json()['data']
        status = data['status']
        amount_kobo = data['amount']
        payment = Payment.objects.get(reference_number=reference)
        if status == 'success':
            payment.status = 'success'
            payment.save(update_fields=['status'])
            # Create subscription for payment.user
            plan = Plan.objects.filter(price=Decimal(amount_kobo) / 100).first()
            if plan:
                from django.utils import timezone
                start = timezone.now()
                end = start + timezone.timedelta(days=plan.duration_days)
                Subscription.objects.create(user=payment.user, plan=plan, start_date=start, end_date=end, status='active')
            from django.core.mail import send_mail
            send_mail(
                subject='Subscription payment successful',
                message=f'Thank you for your payment. Reference: {reference}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[payment.user.email],
                fail_silently=True,
            )
        else:
            payment.status = 'failed'
            payment.save(update_fields=['status'])
        return JsonResponse({'status': payment.status})
    except Exception:
        return HttpResponseBadRequest('Verification failed')
