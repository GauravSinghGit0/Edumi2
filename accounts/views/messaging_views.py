"""
Messaging views: inbox list, conversation detail, start conversation, send message.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db import models
from django.utils import timezone

from accounts.messaging_models import Conversation, Message

User = get_user_model()


def format_conversation_timestamp(dt):
    if not dt:
        return ""
    from django.utils import timezone
    from datetime import timedelta
    
    try:
        local_dt = timezone.localtime(dt)
        now = timezone.localtime(timezone.now())
    except ValueError:
        local_dt = dt
        from datetime import datetime
        now = datetime.now()
        
    diff = now - local_dt
    seconds = int(diff.total_seconds())
    
    if seconds < 60:
        return "now"
        
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
        
    hours = minutes // 60
    if hours < 24:
        if local_dt.date() == now.date():
            return f"{hours}h"
            
    if local_dt.date() == (now.date() - timedelta(days=1)):
        return "yesterday"
        
    if local_dt.year == now.year:
        return local_dt.strftime("%b %d")
    return local_dt.strftime("%d/%m/%Y")


@login_required
def inbox(request):
    """View all conversations with optional user search."""
    search_query = request.GET.get('q', '').strip()
    conversations = request.user.conversations.all().prefetch_related(
        'participants', 'participants__userprofile', 'messages'
    )
    for conv in conversations:
        conv.other_user = conv.get_other_user(request.user)
        conv.last_msg = conv.get_last_message()
        conv.unread_count = conv.messages.filter(is_read=False).exclude(sender=request.user).count()
        if conv.last_msg:
            conv.formatted_time = format_conversation_timestamp(conv.last_msg.created_at)

    search_results = []
    if search_query:
        search_results = User.objects.filter(
            models.Q(username__icontains=search_query) |
            models.Q(first_name__icontains=search_query) |
            models.Q(last_name__icontains=search_query) |
            models.Q(email__icontains=search_query) |
            models.Q(userprofile__display_name__icontains=search_query)
        ).exclude(id=request.user.id).select_related('userprofile').distinct()[:10]

    return render(request, 'accounts/inbox.html', {
        'conversations': conversations,
        'search_query': search_query,
        'search_results': search_results,
    })


@login_required
def conversation_detail(request, conversation_id):
    """View a specific conversation thread."""
    conversation = get_object_or_404(Conversation, id=conversation_id)
    if request.user not in conversation.participants.all():
        messages.error(request, 'You do not have access to this conversation')
        return redirect('inbox')
    conversation.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)
    other_user = conversation.get_other_user(request.user)
    messages_list = list(conversation.messages.all().select_related('sender').order_by('created_at'))

    from datetime import date, timedelta
    today = date.today()
    yesterday = today - timedelta(days=1)
    prev_date = None
    for msg in messages_list:
        msg_date = msg.created_at.date()
        if msg_date != prev_date:
            msg.show_date_separator = True
            if msg_date == today:
                msg.date_label = 'Today'
            elif msg_date == yesterday:
                msg.date_label = 'Yesterday'
            else:
                msg.date_label = msg.created_at.strftime('%B %d, %Y')
            prev_date = msg_date
        else:
            msg.show_date_separator = False

    # Fetch data for sidebar
    search_query = request.GET.get('q', '').strip()
    conversations = request.user.conversations.all().prefetch_related(
        'participants', 'participants__userprofile', 'messages'
    )
    for conv in conversations:
        conv.other_user = conv.get_other_user(request.user)
        conv.last_msg = conv.get_last_message()
        conv.unread_count = conv.messages.filter(is_read=False).exclude(sender=request.user).count()
        if conv.last_msg:
            conv.formatted_time = format_conversation_timestamp(conv.last_msg.created_at)

    search_results = []
    if search_query:
        search_results = User.objects.filter(
            models.Q(username__icontains=search_query) |
            models.Q(first_name__icontains=search_query) |
            models.Q(last_name__icontains=search_query) |
            models.Q(email__icontains=search_query) |
            models.Q(userprofile__display_name__icontains=search_query)
        ).exclude(id=request.user.id).select_related('userprofile').distinct()[:10]

    return render(request, 'accounts/inbox.html', {
        'conversation': conversation,
        'other_user': other_user,
        'messages': messages_list,
        'conversations': conversations,
        'search_query': search_query,
        'search_results': search_results,
    })


@login_required
def start_conversation(request, username):
    """Start a new (or resume existing) conversation with another user."""
    other_user = get_object_or_404(User, username=username)
    if other_user == request.user:
        messages.error(request, 'You cannot message yourself')
        return redirect('inbox')
    existing_conv = Conversation.objects.filter(participants=request.user).filter(participants=other_user).first()
    if existing_conv:
        return redirect('conversation_detail', conversation_id=existing_conv.id)
    conversation = Conversation.objects.create()
    conversation.participants.add(request.user, other_user)
    return redirect('conversation_detail', conversation_id=conversation.id)


@login_required
def delete_conversation(request, conversation_id):
    """Delete a conversation (chat) from the inbox for the requesting user.
    Only participants can delete; the entire conversation is removed.
    """
    conversation = get_object_or_404(Conversation, id=conversation_id)
    if request.user not in conversation.participants.all():
        messages.error(request, 'You do not have permission to delete this conversation')
        return redirect('inbox')
    conversation.delete()
    messages.success(request, 'Conversation deleted successfully')
    return redirect('inbox')


@login_required
@require_http_methods(["POST"])
def send_message(request, conversation_id):
    """Send a message (text, image, or file) in a conversation, handling uploads correctly."""
    conversation = get_object_or_404(Conversation, id=conversation_id)
    if request.user not in conversation.participants.all():
        return JsonResponse({'status': 'error', 'message': 'Access denied'}, status=403)

    content = request.POST.get('content', '').strip()
    uploaded_image = request.FILES.get('image')
    uploaded_file = request.FILES.get('file')

    # Determine which file field to use, avoiding duplicates
    image_file = None
    generic_file = None
    if uploaded_image:
        if uploaded_image.content_type.startswith('image/'):
            image_file = uploaded_image
        else:
            generic_file = uploaded_image
    elif uploaded_file:
        if uploaded_file.content_type.startswith('image/'):
            image_file = uploaded_file
        else:
            generic_file = uploaded_file

    if not content and not image_file and not generic_file:
        return JsonResponse({'status': 'error', 'message': 'Message cannot be empty'}, status=400)

    message = Message.objects.create(
        conversation=conversation,
        sender=request.user,
        content=content,
        image=image_file,
        file=generic_file,
    )



    from accounts.notification_utils import notify_new_message
    other_user = conversation.get_other_user(request.user)
    local_created_at = timezone.localtime(message.created_at)
    if other_user:
        notify_new_message(
            request.user,
            other_user,
            conversation_id,
            content=content,
            created_at=local_created_at.strftime('%I:%M %p')
        )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'success',
            'message_id': message.id,
            'content': message.content,
            'image_url': message.image.url if message.image else None,
            'file_url': message.file.url if message.file else None,
            'sender': message.sender.username,
            'created_at': local_created_at.strftime('%I:%M %p'),
        })
    return redirect('conversation_detail', conversation_id=conversation_id)


@login_required
def search_users_ajax(request):
    """AJAX endpoint to search for users to message."""
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'users': []})

    matching_users = User.objects.filter(
        models.Q(username__icontains=query) |
        models.Q(first_name__icontains=query) |
        models.Q(last_name__icontains=query) |
        models.Q(email__icontains=query) |
        models.Q(userprofile__display_name__icontains=query)
    ).exclude(id=request.user.id).select_related('userprofile').distinct()[:10]

    users_data = []
    now = timezone.now()
    online_delta = timezone.timedelta(minutes=5)
    for u in matching_users:
        has_conv = Conversation.objects.filter(participants=request.user).filter(participants=u).exists()
        profile = getattr(u, 'userprofile', None)
        # Determine display name safely
        if profile:
            display_name = getattr(profile, 'display_name', '') or u.get_full_name() or u.username
            pfp = profile.get_profile_picture_url()
            last_seen = profile.last_seen
        else:
            display_name = u.get_full_name() or u.username
            pfp = None
            last_seen = None
        is_online = False
        if last_seen:
            is_online = (now - last_seen) <= online_delta
        users_data.append({
            'username': u.username,
            'display_name': display_name,
            'pfp': pfp,
            'user_type': profile.user_type if profile else 'student',
            'has_conv': has_conv,
            'last_seen': last_seen.isoformat() if last_seen else None,
            'is_online': is_online,
        })

    return JsonResponse({'users': users_data})
