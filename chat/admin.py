from django.contrib import admin
from .models import Chat, Message


@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'title', 'model', 'updated_at')
    search_fields = ('title', 'user__email')
    list_filter = ('model',)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'chat', 'role', 'created_at')
    search_fields = ('content',)
    list_filter = ('role',)