from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Plan, Subscription


def plan_list(request):
    plans = Plan.objects.all()
    return render(request, 'pages/pricing.html', {'plans': plans})


@login_required
def subscription_history(request):
    subs = Subscription.objects.filter(user=request.user).order_by('-start_date')
    return render(request, 'subscriptions/history.html', {'subscriptions': subs})
