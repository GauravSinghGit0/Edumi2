from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class Conversation(models.Model):
    """Represents a conversation between two users"""
    participants = models.ManyToManyField(User, related_name='conversations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
    
    def get_other_user(self, current_user):
        """Get the other participant in the conversation"""
        return self.participants.exclude(id=current_user.id).first()
    
    def get_last_message(self):
        """Get the most recent message"""
        return self.messages.order_by('-created_at').first()
    
    def __str__(self):
        users = list(self.participants.all()[:2])
        if len(users) == 2:
            return f"{users[0].username} - {users[1].username}"
        return f"Conversation {self.id}"

class Message(models.Model):
    """Represents a message in a conversation"""
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    content = models.TextField(blank=True)
    image = models.ImageField(upload_to='chat_images/', blank=True, null=True)
    file = models.FileField(upload_to='chat_files/', blank=True, null=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.sender.username}: {self.content[:50]}"
