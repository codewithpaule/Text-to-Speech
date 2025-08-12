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
ELEVENLABS_API_KEY = 'sk_0ac7040051c07fdaa90e9a0fadc81d722327182e155ade89'
ELEVENLABS_BASE = 'https://api.elevenlabs.io/v1'


@login_required
@require_POST
def upload_voice_sample(request):
    if not ELEVENLABS_API_KEY:
        return JsonResponse({'error': 'Voice cloning not configured'}, status=400)

    if 'audio' not in request.FILES:
        return JsonResponse({'error': 'No audio file provided'}, status=400)

    audio_file = request.FILES['audio']
    voice_name = request.POST.get('name', '').strip() or "My Cloned Voice"

    try:
        # Verify file size (max 10MB)
        if audio_file.size > 10 * 1024 * 1024:
            return JsonResponse({'error': 'File too large (max 10MB)'}, status=400)

        # Prepare the request to ElevenLabs
        headers = {
            'xi-api-key': ELEVENLABS_API_KEY,
            'accept': 'application/json'
        }
        
        # Create proper file payload
        file_data = audio_file.read()
        files = {
            'files': ('recording.mp3', file_data, 'audio/mpeg')
        }
        
        data = {
            'name': voice_name,
            'labels': '{"accent": "neutral"}',  # Required field
            'description': 'User-uploaded voice sample'
        }

        # Make the API request
        response = requests.post(
            f'{ELEVENLABS_BASE}/voices/add',
            headers=headers,
            files=files,
            data=data,
            timeout=30
        )
        
        # Debugging - log the response
        print("API Response:", response.status_code, response.text)
        
        response.raise_for_status()
        voice_data = response.json()

        # Save voice ID to user profile
        request.user.cloned_voice_id = voice_data.get('voice_id')
        request.user.cloned_voice_provider = 'elevenlabs'
        request.user.save(update_fields=['cloned_voice_id', 'cloned_voice_provider'])

        return JsonResponse({
            'status': 'success',
            'voice_id': request.user.cloned_voice_id
        })

    except requests.exceptions.RequestException as e:
        error_detail = str(e)
        if hasattr(e, 'response') and e.response:
            try:
                error_detail = e.response.json().get('detail', str(e))
            except:
                error_detail = e.response.text
        return JsonResponse({
            'error': 'Voice cloning failed',
            'detail': error_detail,
            'status_code': getattr(e.response, 'status_code', None)
        }, status=400)

@login_required
@require_POST
def speak_cloned(request):
    text = request.POST.get('text', '').strip()
    if not text:
        return JsonResponse({'error': 'No text provided'}, status=400)

    if not (request.user.cloned_voice_id and request.user.cloned_voice_provider):
        return JsonResponse({'error': 'No cloned voice configured'}, status=400)

    try:
        headers = {
            'xi-api-key': ELEVENLABS_API_KEY,
            'accept': 'audio/mpeg',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'text': text,
            'voice_settings': {
                'stability': 0.5,
                'similarity_boost': 0.8
            }
        }

        response = requests.post(
            f'{ELEVENLABS_BASE}/text-to-speech/{request.user.cloned_voice_id}',
            headers=headers,
            json=payload,
            stream=True,
            timeout=30
        )
        
        response.raise_for_status()

        def generate():
            for chunk in response.iter_content(chunk_size=4096):
                yield chunk

        return StreamingHttpResponse(
            generate(),
            content_type='audio/mpeg',
            status=response.status_code
        )

    except requests.exceptions.RequestException as e:
        error_msg = f"API Error: {str(e)}"
        if hasattr(e, 'response') and e.response:
            try:
                error_msg = e.response.json().get('detail', error_msg)
            except:
                error_msg = e.response.text or error_msg
        return JsonResponse({'error': error_msg}, status=400)
    except Exception as e:
        return JsonResponse({'error': f"Server error: {str(e)}"}, status=500)

@login_required
def clone_page(request):
    return render(request, 'pages/custom_voice.html', {
        'cloned_voice_ready': bool(getattr(request.user, 'cloned_voice_id', '') and getattr(request.user, 'cloned_voice_provider', '')),
    })
