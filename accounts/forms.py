from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from .models import UserProfile

User = get_user_model()

class RegisterForm(UserCreationForm):
    USER_TYPE_CHOICES = (
        ('student', 'Student'),
        ('teacher', 'Teacher'),
    )
    
    user_type = forms.ChoiceField(choices=USER_TYPE_CHOICES, required=True)
    
    class Meta:
        model = User
        fields = ['username', 'user_type']
