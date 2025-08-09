from django.urls import path
from ttsapp.views import text_to_speech

urlpatterns = [
    path('', text_to_speech, name='text_to_speech'),
]
