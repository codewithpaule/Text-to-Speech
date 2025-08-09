import asyncio
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST
from asgiref.sync import sync_to_async
import edge_tts


@login_required
@require_GET
async def voices(request):
    voices_list = await edge_tts.list_voices()
    simple = [
        {
            'shortName': v['ShortName'],
            'gender': v['Gender'],
            'locale': v['Locale'],
        }
        for v in voices_list
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
