import json
import os
from typing import List, Dict

import requests
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest, HttpRequest, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone

from .models import Chat, Message


OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_API_URL = 'https://api.openai.com/v1/chat/completions'
DEFAULT_MODEL = os.getenv('DEFAULT_CHAT_MODEL', 'gpt-4o-mini')


def _generate_title_from_text(text: str) -> str:
    text = (text or '').strip()
    if not text:
        return 'New Chat'
    # First 8 words, max 60 chars
    words = text.split()
    title = ' '.join(words[:8])
    if len(title) > 60:
        title = title[:57] + '...'
    return title


@login_required
def chat_home(request: HttpRequest, chat_id: int | None = None) -> HttpResponse:
    preferred_voice = getattr(request.user, 'preferred_voice', '') or ''
    cloned_voice_ready = bool(getattr(request.user, 'cloned_voice_id', '') and getattr(request.user, 'cloned_voice_provider', ''))
    return render(request, 'chat/chat.html', {
        'initial_chat_id': chat_id or '',
        'preferred_voice': preferred_voice,
        'default_model': DEFAULT_MODEL,
        'cloned_voice_ready': json.dumps(cloned_voice_ready),
    })


@login_required
@require_GET
def list_chats(request: HttpRequest) -> JsonResponse:
    chats = (
        Chat.objects
        .filter(user=request.user)
        .order_by('-updated_at')
        .values('id', 'title', 'model', 'updated_at', 'created_at')
    )
    return JsonResponse({'chats': list(chats)})


@login_required
@require_GET
def get_chat(request: HttpRequest, chat_id: int) -> JsonResponse:
    chat = get_object_or_404(Chat, id=chat_id, user=request.user)
    messages = list(chat.messages.values('role', 'content', 'created_at'))
    return JsonResponse({
        'chat': {
            'id': chat.id,
            'title': chat.title,
            'model': chat.model,
            'created_at': chat.created_at,
            'updated_at': chat.updated_at,
        },
        'messages': messages,
    })


def _build_openai_payload(model: str, messages: List[Dict[str, str]]) -> Dict:
    return {
        'model': model,
        'messages': messages,
        'temperature': 0.5,
    }


@login_required
@require_POST
def create_chat(request: HttpRequest) -> JsonResponse:
    title = _generate_title_from_text(request.POST.get('title', ''))
    model = (request.POST.get('model', '').strip() or DEFAULT_MODEL)
    chat = Chat.objects.create(user=request.user, title=title, model=model)
    return JsonResponse({'chat_id': chat.id, 'title': chat.title, 'model': chat.model})


@login_required
@require_POST
def send_message(request: HttpRequest) -> JsonResponse:
    if not OPENAI_API_KEY:
        return HttpResponseBadRequest('Server missing OPENAI_API_KEY')

    user_text = request.POST.get('message', '').strip()
    chat_id_str = request.POST.get('chat_id', '').strip()
    model = (request.POST.get('model', '').strip() or DEFAULT_MODEL)

    if not user_text:
        return HttpResponseBadRequest('Empty message')

    chat = None
    created = False
    if chat_id_str:
        chat = get_object_or_404(Chat, id=int(chat_id_str), user=request.user)
        if chat.model != model:
            chat.model = model
            chat.save(update_fields=['model', 'updated_at'])
    else:
        title = _generate_title_from_text(user_text)
        chat = Chat.objects.create(user=request.user, title=title, model=model)
        created = True

    Message.objects.create(chat=chat, role='user', content=user_text)

    # Fetch recent context (up to 20 last messages)
    recent_messages = list(
        Message.objects.filter(chat=chat)
        .order_by('-created_at')[:20]
        .values('role', 'content')
    )
    recent_messages.reverse()

    payload = _build_openai_payload(model=model, messages=recent_messages)

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

    # Touch the chat updated_at
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