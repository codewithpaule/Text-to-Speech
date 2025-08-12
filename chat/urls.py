from django.urls import path
from . import views

urlpatterns = [
    path('', views.chat_home, name='home'),
    path('<int:chat_id>/', views.chat_home, name='chat_detail'),
    path('list/', views.list_chats, name='list_chats'),
    path('api/chat/<int:chat_id>/', views.get_chat, name='get_chat'),
    path('send/', views.send_message, name='send_message'),
]