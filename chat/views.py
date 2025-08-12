import os
import json
import re
from typing import List, Dict

import requests
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest, HttpRequest, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone

from .models import Chat, Message, UserMemory  # Make sure to add UserMemory model

OPENAI_API_URL = 'https://api.openai.com/v1/chat/completions'
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
DEFAULT_CHAT_MODEL = 'gpt-4o-mini'

# ---------------- MEMORY HELPERS ----------------

def _generate_title_with_ai(text: str) -> str:
    """Generate a short, descriptive chat title from the first user message."""
    if not text.strip():
        return "New Chat"

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a title generator. Create a short, descriptive title (max 6 words) "
                    "based on the provided conversation start. "
                    "Do not use quotes or punctuation at the start or end."
                )
            },
            {"role": "user", "content": text}
        ],
        "temperature": 0.3
    }

    try:
        resp = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        title = resp.json()["choices"][0]["message"]["content"].strip()
        return title if title else "New Chat"
    except Exception as e:
        print(f"Title generation failed: {e}")
        return "New Chat"


def _update_user_memory_from_message(user, message):
    """Use GPT to dynamically extract personal facts from user messages."""
    if not message:
        return

    extraction_prompt = [
        {
            "role": "system",
            "content": (
                "You are a fact extraction assistant. "
                "Given the following user message, extract any personal information they are sharing "
                "(e.g., name, age, location, interests, preferences, dislikes). "
                "Respond only in JSON with key-value pairs, do not include explanations. "
                "If no personal info is found, return an empty JSON object."
            )
        },
        {"role": "user", "content": message}
    ]

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": extraction_prompt,
        "temperature": 0,
    }

    try:
        resp = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=20)
        resp.raise_for_status()
        facts = json.loads(resp.json()["choices"][0]["message"]["content"])

        if not hasattr(user, "memory"):
            memory = UserMemory.objects.create(user=user, memory_data={})
        else:
            memory = user.memory

        updated = False
        for k, v in facts.items():
            if v and memory.memory_data.get(k) != v:
                memory.memory_data[k] = v
                updated = True

        if updated:
            memory.save()

    except Exception as e:
        # Log for debugging
        print(f"Memory extraction failed: {e}")


def _get_memory_text(user):
    """Return a string description of what we know about the user."""
    if hasattr(user, 'memory') and user.memory.memory_data:
        return f"Here is what you know about this user: {json.dumps(user.memory.memory_data)}"
    return "You have no stored personal facts about this user yet."


# ---------------- PAYLOAD BUILDING ----------------

def _build_openai_payload(model: str, messages: List[Dict[str, str]], user) -> Dict:
    """Add stored memory and bot personality to the context before sending to OpenAI."""

    # Default values
    bot_name = "Assistant"
    bot_personality = "Friendly, helpful, remembers previous conversations, understanding and very intelligent."

    # If user has stored bot name, use it
    if hasattr(user, 'memory') and 'bot_name' in user.memory.memory_data:
        bot_name = user.memory.memory_data['bot_name']

    system_message = {
        'role': 'system',
        'content': (
            f"You are {bot_name}, an AI assistant. "
            f"Your personality: {bot_personality}\n"
            f"{_get_memory_text(user)}\n"
        )
    }

    return {
        'model': model,
        'messages': [system_message] + messages,
        'temperature': 0.5,
    }



# ---------------- EXISTING VIEWS ----------------

def _generate_title_from_text(text: str) -> str:
    text = (text or '').strip()
    if not text:
        return 'New Chat'
    words = text.split()
    title = ' '.join(words[:8])
    if len(title) > 60:
        title = title[:57] + '...'
    return title


@login_required
def chat_home(request: HttpRequest, chat_id: int | None = None) -> HttpResponse:
    return render(request, 'chat/chat.html', {
        'initial_chat_id': chat_id or '',
        'default_model': DEFAULT_CHAT_MODEL,
    })


@login_required
@require_GET
def list_chats(request: HttpRequest) -> JsonResponse:
    chats = (
        Chat.objects
        .filter(user=request.user)
        .order_by('-pinned', '-updated_at')
        .values('id', 'title', 'model', 'updated_at', 'created_at', 'pinned')
    )
    return JsonResponse({'chats': list(chats)})


@login_required
@require_GET
def get_chat(request: HttpRequest, chat_id: int) -> JsonResponse:
    chat = get_object_or_404(Chat, id=chat_id, user=request.user)
    messages = list(chat.messages.values('id', 'role', 'content', 'created_at'))
    return JsonResponse({
        'chat': {
            'id': chat.id,
            'title': chat.title,
            'model': chat.model,
            'created_at': chat.created_at,
            'updated_at': chat.updated_at,
            'pinned': chat.pinned,
        },
        'messages': messages,
    })


@login_required
@require_POST
def create_chat(request: HttpRequest) -> JsonResponse:
    title = _generate_title_with_ai(request.POST.get('title', ''))
    model = (request.POST.get('model', '').strip() or DEFAULT_CHAT_MODEL)
    chat = Chat.objects.create(user=request.user, title=title, model=model)
    return JsonResponse({'chat_id': chat.id, 'title': chat.title, 'model': chat.model})


@login_required
@require_POST
def send_message(request: HttpRequest) -> JsonResponse:
    if not OPENAI_API_KEY:
        return HttpResponseBadRequest('Server missing OPENAI_API_KEY')

    user_text = request.POST.get('message', '').strip()
    chat_id_str = request.POST.get('chat_id', '').strip()
    model = (request.POST.get('model', '').strip() or DEFAULT_CHAT_MODEL)

    if not user_text:
        return HttpResponseBadRequest('Empty message')

    # Update memory with new personal info
    _update_user_memory_from_message(request.user, user_text)

    # Get or create chat
    created = False
    if chat_id_str:
        chat = get_object_or_404(Chat, id=int(chat_id_str), user=request.user)
        if chat.model != model:
            chat.model = model
            chat.save(update_fields=['model', 'updated_at'])
    else:
        title = _generate_title_with_ai(user_text)
        chat = Chat.objects.create(user=request.user, title=title, model=model)
        created = True

    # Save user message
    Message.objects.create(chat=chat, role='user', content=user_text)

    # Fetch recent context (last 20 messages from this chat)
    recent_messages = list(
        Message.objects.filter(chat=chat)
        .order_by('-created_at')[:20]
        .values('role', 'content')
    )
    recent_messages.reverse()

    # Build payload with stored memory
    payload = _build_openai_payload(model=model, messages=recent_messages, user=request.user)

    headers = {
        'Authorization': f'Bearer {OPENAI_API_KEY}',
        'Content-Type': 'application/json',
    }

    try:
        resp = requests.post(OPENAI_API_URL, headers=headers, data=json.dumps(payload), timeout=90)
        resp.raise_for_status()
        data = resp.json()
        assistant_text = data['choices'][0]['message']['content']
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    # Save assistant message
    Message.objects.create(chat=chat, role='assistant', content=assistant_text)

    # Update chat timestamp
    Chat.objects.filter(id=chat.id).update(updated_at=timezone.now())

    return JsonResponse({
        'chat_id': chat.id,
        'created': created,
        'title': chat.title,
        'model': chat.model,
        'assistant': {
            'role': 'assistant',
            'content': assistant_text,
        },
    })


@login_required
@require_POST
def rename_chat(request: HttpRequest, chat_id: int) -> JsonResponse:
    chat = get_object_or_404(Chat, id=chat_id, user=request.user)
    title = (request.POST.get('title', '')).strip()
    if not title:
        return HttpResponseBadRequest('Title required')
    chat.title = title
    chat.save(update_fields=['title', 'updated_at'])
    return JsonResponse({'ok': True})

@login_required
@require_POST
def delete_chat(request: HttpRequest, chat_id: int) -> JsonResponse:
    chat = get_object_or_404(Chat, id=chat_id, user=request.user)
    chat.delete()
    return JsonResponse({'ok': True})

@login_required
@require_POST
def toggle_pin_chat(request: HttpRequest, chat_id: int) -> JsonResponse:
    chat = get_object_or_404(Chat, id=chat_id, user=request.user)
    chat.pinned = not chat.pinned
    chat.save(update_fields=['pinned', 'updated_at'])
    return JsonResponse({'pinned': chat.pinned})

@login_required
@require_POST
def edit_message(request: HttpRequest, message_id: int) -> JsonResponse:
    message = get_object_or_404(Message, id=message_id, chat__user=request.user)
    if message.role != 'user':
        return HttpResponseBadRequest('Only user messages can be edited')
    new_content = (request.POST.get('content', '')).strip()
    if not new_content:
        return HttpResponseBadRequest('Content required')
    message.content = new_content
    message.save(update_fields=['content', 'updated_at'])
    # Update chat timestamp
    Chat.objects.filter(id=message.chat_id).update(updated_at=timezone.now())
    return JsonResponse({'ok': True})

@login_required
@require_POST
def delete_message(request: HttpRequest, message_id: int) -> JsonResponse:
    message = get_object_or_404(Message, id=message_id, chat__user=request.user)
    chat_id = message.chat_id
    message.delete()
    Chat.objects.filter(id=chat_id).update(updated_at=timezone.now())
    return JsonResponse({'ok': True})

@login_required
@require_POST
def regenerate_response(request: HttpRequest, chat_id: int) -> JsonResponse:
    if not OPENAI_API_KEY:
        return HttpResponseBadRequest('Server missing OPENAI_API_KEY')
    chat = get_object_or_404(Chat, id=chat_id, user=request.user)
    model = chat.model or DEFAULT_CHAT_MODEL

    # Find the last user message
    last_user_message = (
        Message.objects
        .filter(chat=chat, role='user')
        .order_by('-created_at')
        .first()
    )
    if not last_user_message:
        return HttpResponseBadRequest('No user message to regenerate from')

    # Remove the last assistant message if present so we "replace" it
    last_assistant_message = (
        Message.objects
        .filter(chat=chat, role='assistant')
        .order_by('-created_at')
        .first()
    )
    if last_assistant_message:
        last_assistant_message.delete()

    # Rebuild context and call OpenAI
    recent_messages = list(
        Message.objects.filter(chat=chat)
        .order_by('-created_at')[:20]
        .values('role', 'content')
    )
    recent_messages.reverse()

    payload = _build_openai_payload(model=model, messages=recent_messages, user=request.user)
    headers = {
        'Authorization': f'Bearer {OPENAI_API_KEY}',
        'Content-Type': 'application/json',
    }
    try:
        resp = requests.post(OPENAI_API_URL, headers=headers, data=json.dumps(payload), timeout=90)
        resp.raise_for_status()
        data = resp.json()
        assistant_text = data['choices'][0]['message']['content']
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    Message.objects.create(chat=chat, role='assistant', content=assistant_text)
    Chat.objects.filter(id=chat.id).update(updated_at=timezone.now())

    return JsonResponse({'assistant': {'role': 'assistant', 'content': assistant_text}})