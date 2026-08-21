from datetime import datetime, date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db import models
from django.utils import timezone

from accounts.messaging_models import Conversation, Message
from accounts.notification_utils import notify_new_message

User = get_user_model()


def format_conversation_timestamp(dt):
    if not dt:
        return ""
    
    try:
        local_dt = timezone.localtime(dt)
        now = timezone.localtime(timezone.now())
    except ValueError:
        local_dt = dt
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


def get_user_contacts(user):
    """
    Get all relevant contacts for this user:
    1. Joined/taught classrooms (with their conversation IDs).
    2. Classmates and Teachers from those classrooms.
    3. General active directory users for 1-on-1 private messaging.
    """
    from meetings.models import Classroom, ClassroomMembership
    
    # 1. Classrooms
    if hasattr(user, 'userprofile') and user.userprofile.user_type == 'teacher':
        teacher_classrooms = Classroom.objects.filter(teacher=user, is_active=True)
        enrolled_classrooms = Classroom.objects.filter(memberships__student=user, memberships__status='approved', is_active=True)
        classrooms_qs = (teacher_classrooms | enrolled_classrooms).distinct().select_related('teacher')
    else:
        classrooms_qs = Classroom.objects.filter(memberships__student=user, memberships__status='approved', is_active=True).select_related('teacher')

    classroom_list = []
    for c in classrooms_qs:
        conv = getattr(c, 'conversation', None)
        if not conv:
            conv = c.get_or_create_conversation()
        classroom_list.append({
            'id': c.id,
            'title': c.title,
            'class_code': c.class_code,
            'teacher': c.teacher,
            'conversation_id': conv.id if conv else None,
            'member_count': c.get_approved_students().count() + 1,
        })

    # 2. Get students and teachers in those classrooms
    classroom_ids = [c['id'] for c in classroom_list]
    classroom_student_ids = ClassroomMembership.objects.filter(classroom_id__in=classroom_ids, status='approved').values_list('student_id', flat=True)
    classroom_teacher_ids = classrooms_qs.values_list('teacher_id', flat=True)
    contact_user_ids = set(classroom_student_ids).union(set(classroom_teacher_ids))
    contact_user_ids.discard(user.id)

    # Classmates and Teachers
    network_users = User.objects.filter(id__in=contact_user_ids, is_active=True).select_related('userprofile')
    
    # Other users across school
    other_users = User.objects.filter(is_active=True).exclude(id=user.id).exclude(id__in=contact_user_ids).select_related('userprofile')[:20]

    return {
        'joined_classrooms': classroom_list,
        'network_users': network_users,
        'other_users': other_users,
    }


@login_required
def inbox(request):
    """View all conversations with optional user search."""
    search_query = request.GET.get('q', '').strip()
    conversations = request.user.conversations.all().prefetch_related(
        'participants', 'participants__userprofile', 'messages'
    )
    for conv in conversations:
        conv.other_user = conv.get_other_user(request.user)
        conv.display_title = conv.get_display_title(request.user)
        conv.is_classroom = conv.is_classroom_chat()
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

    contacts_data = get_user_contacts(request.user)

    return render(request, 'accounts/messaging/inbox.html', {
        'conversations': conversations,
        'search_query': search_query,
        'search_results': search_results,
        'joined_classrooms': contacts_data['joined_classrooms'],
        'network_users': contacts_data['network_users'],
        'other_users': contacts_data['other_users'],
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
    conversation.display_title = conversation.get_display_title(request.user)
    conversation.is_classroom = conversation.is_classroom_chat()
    messages_list = list(conversation.messages.all().select_related('sender', 'sender__userprofile').order_by('created_at'))

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
        conv.display_title = conv.get_display_title(request.user)
        conv.is_classroom = conv.is_classroom_chat()
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

    contacts_data = get_user_contacts(request.user)

    return render(request, 'accounts/messaging/inbox.html', {
        'conversation': conversation,
        'other_user': other_user,
        'messages': messages_list,
        'conversations': conversations,
        'search_query': search_query,
        'search_results': search_results,
        'joined_classrooms': contacts_data['joined_classrooms'],
        'network_users': contacts_data['network_users'],
        'other_users': contacts_data['other_users'],
    })


@login_required
def start_conversation(request, username):
    """Start a new (or resume existing) 1-on-1 private direct conversation with another user."""
    other_user = get_object_or_404(User, username=username)
    if other_user == request.user:
        messages.error(request, 'You cannot message yourself')
        return redirect('inbox')
    
    # Strictly search for 1-on-1 direct conversations (where classroom is NULL)
    existing_conv = Conversation.objects.filter(
        classroom__isnull=True,
        participants=request.user
    ).filter(
        participants=other_user
    ).first()
    
    if existing_conv:
        return redirect('conversation_detail', conversation_id=existing_conv.id)
    
    # Create brand new 1-on-1 private direct conversation
    conversation = Conversation.objects.create(classroom=None)
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

    local_created_at = timezone.localtime(message.created_at)
    profile = getattr(message.sender, 'userprofile', None)
    sender_display_name = getattr(profile, 'display_name', '') or message.sender.get_full_name() or message.sender.username
    
    is_classroom_teacher = bool(conversation.classroom and conversation.classroom.teacher_id == message.sender_id)
    is_teacher_profile = bool(profile and profile.user_type == 'teacher') or message.sender.is_superuser
    sender_role = 'Teacher' if (is_classroom_teacher or is_teacher_profile) else 'Student'
    
    if profile and hasattr(profile, 'get_profile_picture_url'):
        sender_pfp = profile.get_profile_picture_url()
    else:
        sender_pfp = f"https://ui-avatars.com/api/?name={message.sender.username}&background=6366f1&color=fff"

    image_url = message.image.url if message.image else None
    file_url = message.file.url if message.file else None
    file_name = message.file.name.split('/')[-1] if message.file else None

    # Notify all other participants in the conversation (1-on-1 and classroom group chats)
    for participant in conversation.participants.exclude(id=request.user.id):
        notify_new_message(
            request.user,
            participant,
            conversation_id,
            content=content or ("Sent an attachment" if (image_file or generic_file) else "New message"),
            created_at=local_created_at.strftime('%I:%M %p'),
            sender_name=sender_display_name,
            sender_role=sender_role,
            sender_pfp=sender_pfp,
            message_id=message.id,
            image_url=image_url,
            file_url=file_url,
            file_name=file_name
        )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'success',
            'message_id': message.id,
            'content': message.content,
            'image_url': image_url,
            'file_url': file_url,
            'file_name': file_name,
            'sender': message.sender.username,
            'sender_name': sender_display_name,
            'sender_role': sender_role,
            'sender_pfp': sender_pfp,
            'created_at': local_created_at.strftime('%I:%M %p'),
            'created_date': local_created_at.strftime('%b %d, %Y'),
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
        has_conv = Conversation.objects.filter(classroom__isnull=True, participants=request.user).filter(participants=u).exists()
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
