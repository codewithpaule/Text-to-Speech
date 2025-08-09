import os
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import openai

# Load environment variables
from dotenv import load_dotenv
load_dotenv()  # This loads the .env file

# Configure OpenAI API key
if not openai.api_key:
    raise ValueError("No OpenAI API key found in environment variables")

@csrf_exempt  # Temporarily for testing, remove in production
def text_to_speech(request):
    if request.method == "POST":
        text = request.POST.get("text", "").strip()
        if not text:
            return JsonResponse({"error": "No text provided"}, status=400)

        try:
            response = openai.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=text,
                response_format="mp3"
            )
            return HttpResponse(response.content, content_type="audio/mpeg")
        except Exception as e:
            print(f"Error in TTS: {str(e)}")
            return JsonResponse({"error": "Failed to generate speech"}, status=500)

    return render(request, "ttsapp/index.html")