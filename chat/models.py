from django.db import models
from django.conf import settings


class Chat(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chats')
    title = models.CharField(max_length=255)
    model = models.CharField(max_length=100, default='gpt-4o-mini')
    pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.title} ({self.user.email})"

class UserMemory(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memory')
    memory_data = models.JSONField(default=dict)  # store facts like {'name': 'Paul', 'likes': ['pizza', 'coding']}

    def remember(self, key, value):
        self.memory_data[key] = value
        self.save()

    def recall(self, key):
        return self.memory_data.get(key)

class BotProfile(models.Model):
    name = models.CharField(max_length=50)
    personality = models.TextField(default="Friendly, helpful, and intelligent.")

    def __str__(self):
        return self.name


class Message(models.Model):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]

    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self) -> str:
        return f"{self.role} @ {self.created_at:%Y-%m-%d %H:%M}"