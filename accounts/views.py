import random
from datetime import timedelta
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

from .models import User, OTP


def register(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        if not email or not password:
            return render(request, 'accounts/register.html', {'error': 'Email and password are required'})
        if User.objects.filter(email=email).exists():
            return render(request, 'accounts/register.html', {'error': 'Email already registered'})
        user = User.objects.create_user(email=email, password=password, full_name=full_name)
        # create email verification OTP and send link
        code = f"{random.randint(100000, 999999)}"
        otp = OTP.objects.create(
            user=user,
            code=code,
            type='email_verification',
            expiration_time=timezone.now() + timedelta(hours=1),
        )
        verify_link = request.build_absolute_uri(reverse('accounts:verify_email') + f'?email={email}&code={code}')
        send_mail(
            subject='Verify your account',
            message=f'Welcome {full_name or email}! Verify your account using this link: {verify_link}',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=True,
        )
        return redirect('accounts:login')
    return render(request, 'accounts/register.html')


def verify_email(request: HttpRequest) -> HttpResponse:
    email = request.GET.get('email', '').lower()
    code = request.GET.get('code', '')
    try:
        user = User.objects.get(email=email)
        otp = OTP.objects.filter(user=user, type='email_verification', code=code).latest('created_at')
        if otp.is_expired():
            return render(request, 'accounts/login.html', {'error': 'Verification code expired'})
        user.is_verified = True
        user.save(update_fields=['is_verified'])
        return redirect('accounts:login')
    except (User.DoesNotExist, OTP.DoesNotExist):
        return render(request, 'accounts/login.html', {'error': 'Invalid verification link'})


def login_view(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        user = authenticate(request, email=email, password=password)
        if user is not None:
            if not user.is_verified:
                return render(request, 'accounts/login.html', {'error': 'Please verify your email first'})
            login(request, user)
            return redirect('chat:home')
        return render(request, 'accounts/login.html', {'error': 'Invalid credentials'})
    return render(request, 'accounts/login.html')


def logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect('home')


def forgot_password(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return render(request, 'accounts/forgot_password.html', {'error': 'Email not found'})
        code = f"{random.randint(100000, 999999)}"
        OTP.objects.create(
            user=user,
            code=code,
            type='password_reset',
            expiration_time=timezone.now() + timedelta(minutes=15),
        )
        send_mail(
            subject='Your password reset code',
            message=f'Use this OTP to reset your password: {code}',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=True,
        )
        return redirect(reverse('accounts:verify_otp') + f'?email={email}')
    return render(request, 'accounts/forgot_password.html')


def verify_otp(request: HttpRequest) -> HttpResponse:
    email = request.GET.get('email', '').lower()
    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        try:
            user = User.objects.get(email=email)
            otp = OTP.objects.filter(user=user, type='password_reset', code=code).latest('created_at')
            if otp.is_expired():
                return render(request, 'accounts/verify_otp.html', {'error': 'Code expired', 'email': email})
            return redirect(reverse('accounts:reset_password') + f'?email={email}&code={code}')
        except (User.DoesNotExist, OTP.DoesNotExist):
            return render(request, 'accounts/verify_otp.html', {'error': 'Invalid code', 'email': email})
    return render(request, 'accounts/verify_otp.html', {'email': email})


def reset_password(request: HttpRequest) -> HttpResponse:
    email = request.GET.get('email', '').lower()
    code = request.GET.get('code', '').strip()
    if request.method == 'POST':
        password = request.POST.get('password', '')
        confirm = request.POST.get('confirm', '')
        if password != confirm:
            return render(request, 'accounts/reset_password.html', {'error': 'Passwords do not match', 'email': email, 'code': code})
        try:
            user = User.objects.get(email=email)
            otp = OTP.objects.filter(user=user, type='password_reset', code=code).latest('created_at')
            if otp.is_expired():
                return render(request, 'accounts/reset_password.html', {'error': 'Code expired', 'email': email, 'code': code})
            user.set_password(password)
            user.save(update_fields=['password'])
            return redirect('accounts:login')
        except (User.DoesNotExist, OTP.DoesNotExist):
            return render(request, 'accounts/reset_password.html', {'error': 'Invalid request', 'email': email, 'code': code})
    return render(request, 'accounts/reset_password.html', {'email': email, 'code': code})


@login_required
def profile(request: HttpRequest) -> HttpResponse:
    user = request.user
    if request.method == 'POST':
        user.display_name = request.POST.get('display_name', '').strip()
        user.avatar_url = request.POST.get('avatar_url', '').strip()
        user.theme_mode = request.POST.get('theme_mode', user.theme_mode)
        user.accent_color = request.POST.get('accent_color', user.accent_color)
        user.save(update_fields=['display_name', 'avatar_url', 'theme_mode', 'accent_color', 'updated_at'])
        return redirect('accounts:profile')
    return render(request, 'accounts/profile.html', {'user_obj': user})
