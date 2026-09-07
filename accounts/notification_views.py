"""
Production-grade notification management views following Django best practices.
Includes structured logging, query optimizations, and standardized JSON error responses.
"""
import logging
import json
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_POST
from .notification_models import Notification

logger = logging.getLogger(__name__)


@login_required
def notifications_list(request):
    """Display all notifications for the current user with pagination/slice."""
    try:
        notifications_qs = Notification.objects.filter(recipient=request.user).select_related('related_user')
        total_count = notifications_qs.count()
        unread_count = Notification.get_unread_count(request.user)
        notifications_slice = list(notifications_qs[:100])
    except Exception as e:
        logger.exception("Error loading notifications list for user %s: %s", request.user.id, e)
        notifications_slice = []
        unread_count = 0
        total_count = 0

    return render(request, 'accounts/messaging/notifications.html', {
        'notifications': notifications_slice,
        'unread_count': unread_count,
        'total_count': total_count
    })


@login_required
@require_http_methods(["POST"])
def mark_notification_read(request, notification_id):
    """Mark a single notification as read."""
    try:
        notification = get_object_or_404(Notification, id=notification_id, recipient=request.user)
        notification.mark_as_read()
        unread_count = Notification.get_unread_count(request.user)
        return JsonResponse({
            'status': 'success',
            'unread_count': unread_count
        })
    except Exception as e:
        logger.exception("Failed to mark notification %s as read for user %s: %s", notification_id, request.user.id, e)
        return JsonResponse({
            'status': 'error',
            'message': 'Failed to update notification status'
        }, status=500)


@login_required
@require_http_methods(["POST"])
def mark_notification_unread(request, notification_id):
    """Mark a single notification as unread."""
    try:
        notification = get_object_or_404(Notification, id=notification_id, recipient=request.user)
        if notification.is_read:
            notification.is_read = False
            notification.save(update_fields=['is_read'])
        unread_count = Notification.get_unread_count(request.user)
        return JsonResponse({
            'status': 'success',
            'unread_count': unread_count
        })
    except Exception as e:
        logger.exception("Failed to mark notification %s as unread for user %s: %s", notification_id, request.user.id, e)
        return JsonResponse({
            'status': 'error',
            'message': 'Failed to update notification status'
        }, status=500)


@login_required
@require_http_methods(["POST"])
def mark_all_notifications_read(request):
    """Mark all notifications as read for the current user."""
    try:
        Notification.mark_all_as_read(request.user)
        return JsonResponse({
            'status': 'success',
            'unread_count': 0
        })
    except Exception as e:
        logger.exception("Failed to mark all notifications as read for user %s: %s", request.user.id, e)
        return JsonResponse({
            'status': 'error',
            'message': 'Failed to mark all notifications as read'
        }, status=500)


@login_required
def get_unread_count(request):
    """Get unread notification count for user (used for polling & initial load)."""
    try:
        count = Notification.get_unread_count(request.user)
        return JsonResponse({
            'status': 'success',
            'count': count
        })
    except Exception as e:
        logger.exception("Error getting unread notification count for user %s: %s", request.user.id, e)
        return JsonResponse({
            'status': 'error',
            'count': 0,
            'message': 'Unable to retrieve notification count'
        }, status=500)


@login_required
def get_recent_notifications(request):
    """Get recent notifications for topbar dropdown menu."""
    try:
        notifications = list(
            Notification.objects.filter(recipient=request.user)
            .select_related('related_user')[:10]
        )
        data = [{
            'id': n.id,
            'type': n.notification_type or 'system',
            'title': n.title or 'Notification',
            'message': n.message or '',
            'link': n.link or '#',
            'is_read': bool(n.is_read),
            'created_at': n.created_at.strftime('%b %d, %I:%M %p') if n.created_at else ''
        } for n in notifications]
        unread_count = Notification.get_unread_count(request.user)
        return JsonResponse({
            'status': 'success',
            'notifications': data,
            'unread_count': unread_count
        })
    except Exception as e:
        logger.exception("Error loading recent notifications for user %s: %s", request.user.id, e)
        return JsonResponse({
            'status': 'error',
            'notifications': [],
            'unread_count': 0,
            'message': 'Unable to retrieve notifications'
        }, status=500)


@login_required
@require_POST
def send_broadcast(request):
    """Send broadcast message to all users (admin only)."""
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized access'}, status=403)

    try:
        data = json.loads(request.body)
        title = data.get('title', 'Broadcast Message').strip()
        message = data.get('message', '').strip()

        if not message:
            return JsonResponse({'status': 'error', 'message': 'Message body cannot be empty'}, status=400)

        count = 0
        for user in User.objects.filter(is_active=True):
            Notification.create_broadcast_notification(
                recipient=user,
                title=title,
                message=message,
                sender=request.user
            )
            count += 1

        return JsonResponse({
            'status': 'success',
            'message': f'Broadcast sent to {count} users',
            'recipient_count': count
        })
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON request payload'}, status=400)
    except Exception as e:
        logger.exception("Broadcast failure by user %s: %s", request.user.id, e)
        return JsonResponse({'status': 'error', 'message': 'Internal server error while broadcasting'}, status=500)


@login_required
@require_http_methods(["POST", "DELETE"])
def delete_notification(request, notification_id):
    """Delete a single notification."""
    try:
        notification = get_object_or_404(Notification, id=notification_id, recipient=request.user)
        notification.delete()
        unread_count = Notification.get_unread_count(request.user)
        total_count = Notification.objects.filter(recipient=request.user).count()
        return JsonResponse({
            'status': 'success',
            'unread_count': unread_count,
            'total_count': total_count
        })
    except Exception as e:
        logger.exception("Failed to delete notification %s for user %s: %s", notification_id, request.user.id, e)
        return JsonResponse({
            'status': 'error',
            'message': 'Failed to delete notification'
        }, status=500)
