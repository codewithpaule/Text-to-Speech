from django.urls import path
from . import views

urlpatterns = [
    path('plans/', views.plan_list, name='plans'),
    path('history/', views.subscription_history, name='history'),
]