"""
Views for notification management
"""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .notification_models import Notification


@login_required
def notifications_list(request):
    """Display all notifications for the current user"""
    notifications = Notification.objects.filter(recipient=request.user)[:50]
    unread_count = Notification.get_unread_count(request.user)
    
    return render(request, 'accounts/messaging/notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count
    })


@login_required
@require_http_methods(["POST"])
def mark_notification_read(request, notification_id):
    """Mark a single notification as read"""
    notification = get_object_or_404(Notification, id=notification_id, recipient=request.user)
    notification.mark_as_read()
    
    return JsonResponse({'status': 'success'})


@login_required
@require_http_methods(["POST"])
def mark_all_notifications_read(request):
    """Mark all notifications as read for the current user"""
    Notification.mark_all_as_read(request.user)
    
    return JsonResponse({'status': 'success'})


@login_required
def get_unread_count(request):
    """Get unread notification count (for AJAX polling)"""
    count = Notification.get_unread_count(request.user)
    
    return JsonResponse({'count': count})


@login_required
def get_recent_notifications(request):
    """Get recent notifications (for dropdown)"""
    notifications = Notification.objects.filter(recipient=request.user)[:10]
    
    data = [{
        'id': n.id,
        'type': n.notification_type,
        'title': n.title,
        'message': n.message,
        'link': n.link,
        'is_read': n.is_read,
        'created_at': n.created_at.strftime('%b %d, %I:%M %p')
    } for n in notifications]
    
    return JsonResponse({
        'notifications': data,
        'unread_count': Notification.get_unread_count(request.user)
    })


from django.contrib.auth.models import User
from django.views.decorators.http import require_POST

@login_required
@require_POST
def send_broadcast(request):
    """Send broadcast message to all users (admin only)"""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    import json
    try:
        data = json.loads(request.body)
        title = data.get('title', 'Broadcast Message')
        message = data.get('message', '')
        
        if not message.strip():
            return JsonResponse({'error': 'Message cannot be empty'}, status=400)
        
        # Create notification for all users
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
            'success': True,
            'message': f'Broadcast sent to {count} users',
            'recipient_count': count
        })
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_http_methods(["POST", "DELETE"])
def delete_notification(request, notification_id):
    """Delete a single notification"""
    notification = get_object_or_404(Notification, id=notification_id, recipient=request.user)
    notification.delete()
    return JsonResponse({'status': 'success'})
