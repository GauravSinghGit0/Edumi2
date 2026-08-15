from celery import shared_task
from django.utils import timezone
from .models import Meeting, MeetingChat, MeetingSummary

@shared_task
def generate_meeting_summary(meeting_id):
    """
    AI-powered meeting summarization task.
    In a real production environment, this would call an LLM API (OpenAI/Anthropic).
    """
    try:
        meeting = Meeting.objects.get(id=meeting_id)
        chats = MeetingChat.objects.filter(meeting=meeting).order_by('timestamp')
        
        if not chats.exists():
            return "No chat history found for summary."

        # Build prompt from chat history
        chat_history = []
        for chat in chats:
            chat_history.append(f"{chat.user.username}: {chat.message}")
        
        # Simple extraction logic (Mocking LLM behavior)
        questions = [c.message for c in chats if '?' in c.message]
        participants = set([c.user.username for c in chats])
        
        summary_text = f"The meeting '{meeting.title}' was attended by {len(participants)} active participants. "
        summary_text += f"The discussion covered various educational topics. "
        
        if questions:
            summary_text += f"Key questions were raised regarding the lesson material."
        
        # Key Points extraction
        key_points = [
            f"Meeting titled '{meeting.title}' successfully concluded.",
            f"Active discussion with {len(participants)} students involved.",
            f"Total of {chats.count()} messages exchanged in the session."
        ]
        
        if questions:
            key_points.append(f"Recorded {len(questions)} clarify questions from the audience.")

        # Save or update summary
        summary, created = MeetingSummary.objects.update_or_create(
            meeting=meeting,
            defaults={
                'summary_text': summary_text,
                'key_points': key_points,
                'generated_at': timezone.now()
            }
        )
        
        return f"Summary generated for meeting {meeting_id}"

    except Meeting.DoesNotExist:
        return f"Meeting {meeting_id} not found."
    except Exception as e:
        return f"Error generating summary: {str(e)}"
