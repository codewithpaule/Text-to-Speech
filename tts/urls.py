from django.urls import path
from . import views

urlpatterns = [
    path('voices/', views.voices, name='voices'),
    path('speak/', views.speak, name='speak'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('save-voice/', views.save_preferred_voice, name='save_voice'),
]