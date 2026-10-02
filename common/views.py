"""
Common view mixins and base views used across all apps
"""
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.shortcuts import redirect
from django.contrib import messages
from .utils import is_teacher, is_student, get_user_type


class LoginRequiredMixin:
    """
    Mixin that requires the user to be logged in
    """
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class TeacherRequiredMixin(LoginRequiredMixin):
    """
    Mixin that requires the user to be a teacher
    """
    def dispatch(self, request, *args, **kwargs):
        if not is_teacher(request.user) and not request.user.is_superuser:
            messages.error(request, "You don't have permission to access this page.")
            return redirect('home')
        return super().dispatch(request, *args, **kwargs)


class StudentRequiredMixin(LoginRequiredMixin):
    """
    Mixin that requires the user to be a student
    """
    def dispatch(self, request, *args, **kwargs):
        if not is_student(request.user):
            messages.error(request, "You don't have permission to access this page.")
            return redirect('home')
        return super().dispatch(request, *args, **kwargs)


class SuperuserRequiredMixin(LoginRequiredMixin):
    """
    Mixin that requires the user to be a superuser
    """
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, "You don't have permission to access this page.")
            return redirect('home')
        return super().dispatch(request, *args, **kwargs)


class UserTypeContextMixin:
    """
    Adds user_type and common context variables to all views
    """
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context['user_type'] = get_user_type(self.request.user)
            context['is_teacher'] = is_teacher(self.request.user)
            context['is_student'] = is_student(self.request.user)
        return context


import json
from datetime import datetime, timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from .telemetry import get_request_context, write_interaction_log, write_json_audit_log, sanitize_data
from .models import UserActivityLog



@csrf_exempt
@require_POST
def telemetry_events_view(request):
    """
    High-throughput ingestion endpoint for client-side telemetry events (clicks, pageviews, interactions).
    Supports navigator.sendBeacon, keepalive fetch, and XMLHttpRequest from frontend.
    """
    try:
        body = request.body.decode('utf-8') if request.body else ''
        if request.content_type == 'application/json' or body.strip().startswith('{'):
            payload = json.loads(body)
        else:
            raw_data = request.POST.get('payload') or body
            payload = json.loads(raw_data) if raw_data else {}
    except Exception:
        payload = {}

    events = payload.get('events', [])
    if not isinstance(events, list):
        return JsonResponse({'status': 'error', 'message': 'Invalid events payload'}, status=400)

    ctx = get_request_context(request)
    logs_to_create = []

    for evt in events[:50]:  # Limit batch to 50 events max
        event_type = str(evt.get('type') or 'custom')[:50]
        event_name = str(evt.get('name') or evt.get('action') or 'event')[:100]
        page_url = str(evt.get('url') or '')[:500]
        page_title = str(evt.get('title') or '')[:255]
        target_el = str(evt.get('target') or '')[:255]
        target_txt = str(evt.get('text') or '')[:255]
        coords = evt.get('coordinates', {})
        metadata = sanitize_data(evt.get('metadata') or {})
        if coords:
            metadata['coordinates'] = coords
        if evt.get('time_on_page'):
            metadata['time_on_page_ms'] = evt.get('time_on_page')
        if evt.get('viewport'):
            metadata['viewport'] = evt.get('viewport')

        record = {
            'timestamp': evt.get('timestamp') or datetime.now(timezone.utc).isoformat(),
            'event_type': event_type,
            'event_name': event_name,
            'page_url': page_url,
            'page_title': page_title,
            'target_element': target_el,
            'target_text': target_txt,
            'coordinates': coords,
            'metadata': metadata,
            **ctx
        }

        # Write to telemetry log files immediately
        write_interaction_log(record)
        write_json_audit_log(record)

        # Prepare for database bulk insertion
        logs_to_create.append(
            UserActivityLog(
                user=request.user if request.user.is_authenticated else None,
                username=ctx['username'],
                user_role=ctx['user_role'],
                session_key=ctx['session_key'],
                ip_address=ctx['ip_address'],
                user_agent=ctx['user_agent'],
                device_type=ctx['device_type'],
                browser=ctx['browser'],
                os=ctx['os'],
                event_type=event_type,
                event_name=event_name,
                page_url=page_url,
                page_title=page_title,
                target_element=target_el,
                target_text=target_txt,
                metadata=metadata
            )
        )

    if logs_to_create:
        try:
            UserActivityLog.objects.bulk_create(logs_to_create)
        except Exception:
            pass  # Failsafe so DB locks never break telemetry

        try:
            from .telemetry_cache import increment_telemetry_event_counter
            increment_telemetry_event_counter(len(logs_to_create))
        except Exception:
            pass

    return JsonResponse({'status': 'ok', 'processed': len(logs_to_create)})

