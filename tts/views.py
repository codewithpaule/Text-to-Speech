import asyncio
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST
from asgiref.sync import sync_to_async
import edge_tts
import os
import requests
import json


@login_required
@require_GET
async def voices(request):
    voices_list = await edge_tts.list_voices()

    # Query params
    young_only = request.GET.get('young', '').lower() in {'1', 'true', 'yes', 'y'}
    gender = request.GET.get('gender', '').strip().lower()  # 'male' | 'female'
    locale = request.GET.get('locale', '').strip().lower()  # e.g., 'en-us'
    limit = int(request.GET.get('limit', '100'))

    def is_young(v: dict) -> bool:
        voice_tag = v.get('VoiceTag') or {}
        blob = (str(voice_tag) + ' ' + v.get('ShortName', '') + ' ' + v.get('DisplayName', '')).lower()
        # Heuristic: look for child/teen keywords
        return any(k in blob for k in ['child', 'kid', 'teen'])

    filtered = []
    for v in voices_list:
        if gender and v.get('Gender', '').lower() != gender:
            continue
        if locale and v.get('Locale', '').lower() != locale:
            continue
        if young_only and not is_young(v):
            continue
        filtered.append(v)

    # Prefer young voices first if not explicitly filtering
    if not young_only:
        filtered.sort(key=lambda x: 0 if is_young(x) else 1)

    simple = [
        {
            'shortName': v.get('ShortName'),
            'gender': v.get('Gender'),
            'locale': v.get('Locale'),
            'voiceTag': v.get('VoiceTag', {}),
        }
        for v in filtered[:limit]
    ]
    return JsonResponse({'voices': simple})


@login_required
@require_POST
async def speak(request):
    text = request.POST.get('text', '').strip()
    voice = request.POST.get('voice', '').strip() or 'en-US-AriaNeural'
    if not text:
        return HttpResponseBadRequest('No text provided')

    communicate = edge_tts.Communicate(text, voice=voice)

    async def streamer():
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]
    response = StreamingHttpResponse(streamer(), content_type='audio/mpeg')
    response['Cache-Control'] = 'no-cache'
    return response


@login_required
def dashboard(request):
    return render(request, 'pages/dashboard.html', {'preferred_voice': request.user.preferred_voice or ''})


@login_required
@require_POST
def save_preferred_voice(request):
    voice = request.POST.get('voice', '').strip()
    if not voice:
        return HttpResponseBadRequest('Missing voice')
    user = request.user
    user.preferred_voice = voice
    user.save(update_fields=['preferred_voice'])
    return JsonResponse({'ok': True, 'preferred_voice': voice})


# === Voice cloning with ElevenLabs (optional) ===
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY', '').strip()
ELEVENLABS_BASE = 'https://api.elevenlabs.io/v1'


@login_required
@require_POST
def upload_voice_sample(request):
    if not ELEVENLABS_API_KEY:
        return HttpResponseBadRequest('Voice cloning not configured')

    audio_file = request.FILES.get('audio')
    voice_name = request.POST.get('name', '').strip() or f"{request.user.full_name or 'User'} Voice"
    if not audio_file:
        return HttpResponseBadRequest('Missing audio file')

    try:
        files = [
            ('files', (audio_file.name, audio_file.read(), audio_file.content_type or 'audio/mpeg'))
        ]
        data = {'name': voice_name}
        headers = {'xi-api-key': ELEVENLABS_API_KEY}
        r = requests.post(f'{ELEVENLABS_BASE}/voices/add', headers=headers, files=files, data=data, timeout=120)
        r.raise_for_status()
        resp = r.json()
        voice_id = resp.get('voice_id') or resp.get('voice', {}).get('voice_id')
        if not voice_id:
            return JsonResponse({'error': 'No voice_id returned'}, status=500)
        user = request.user
        user.cloned_voice_provider = 'elevenlabs'
        user.cloned_voice_id = voice_id
        user.save(update_fields=['cloned_voice_provider', 'cloned_voice_id'])
        return JsonResponse({'ok': True, 'provider': 'elevenlabs', 'voice_id': voice_id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def speak_cloned(request):
    text = request.POST.get('text', '').strip()
    if not text:
        return HttpResponseBadRequest('No text provided')

    user = request.user
    if not (user.cloned_voice_provider and user.cloned_voice_id):
        return HttpResponseBadRequest('No cloned voice set')

    if user.cloned_voice_provider == 'elevenlabs':
        if not ELEVENLABS_API_KEY:
            return HttpResponseBadRequest('Voice cloning not configured')
        try:
            headers = {
                'xi-api-key': ELEVENLABS_API_KEY,
                'accept': 'audio/mpeg',
                'Content-Type': 'application/json',
            }
            payload = {
                'text': text,
                'voice_settings': { 'stability': 0.5, 'similarity_boost': 0.8 },
            }
            r = requests.post(
                f'{ELEVENLABS_BASE}/text-to-speech/{user.cloned_voice_id}',
                headers=headers,
                data=json.dumps(payload),
                stream=True,
                timeout=120,
            )
            r.raise_for_status()

            def gen():
                for chunk in r.iter_content(chunk_size=4096):
                    if chunk:
                        yield chunk
            return StreamingHttpResponse(gen(), content_type='audio/mpeg')
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return HttpResponseBadRequest('Unsupported voice provider')


@login_required
def clone_page(request):
    return render(request, 'pages/custom_voice.html', {
        'cloned_voice_ready': bool(getattr(request.user, 'cloned_voice_id', '') and getattr(request.user, 'cloned_voice_provider', '')),
    })
