from django.urls import path
from . import views

urlpatterns = [
    path('', views.chat_home, name='home'),
    path('<int:chat_id>/', views.chat_home, name='chat_detail'),
    path('list/', views.list_chats, name='list_chats'),
    path('api/chat/<int:chat_id>/', views.get_chat, name='get_chat'),
    path('send/', views.send_message, name='send_message'),
    path('create/', views.create_chat, name='create_chat'),
    path('chat/<int:chat_id>/rename/', views.rename_chat, name='rename_chat'),
    path('chat/<int:chat_id>/delete/', views.delete_chat, name='delete_chat'),
    path('chat/<int:chat_id>/pin/', views.toggle_pin_chat, name='toggle_pin_chat'),
    path('message/<int:message_id>/edit/', views.edit_message, name='edit_message'),
    path('message/<int:message_id>/delete/', views.delete_message, name='delete_message'),
    path('chat/<int:chat_id>/regenerate/', views.regenerate_response, name='regenerate_response'),
]