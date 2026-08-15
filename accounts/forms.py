import re
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

User = get_user_model()
USERNAME_REGEX = re.compile(r'^[a-zA-Z0-9_]{3,30}$')


class RegisterForm(UserCreationForm):
    USER_TYPE_CHOICES = (
        ('student', 'Student'),
        ('teacher', 'Teacher'),
    )

    email = forms.EmailField(required=True, help_text='Required. A valid email address.')
    user_type = forms.ChoiceField(choices=USER_TYPE_CHOICES, required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'user_type']

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if not username:
            raise ValidationError("Username is required.")
        if len(username) < 3 or len(username) > 30:
            raise ValidationError("Username must be between 3 and 30 characters long.")
        if ' ' in username:
            raise ValidationError("Username cannot contain spaces.")
        if not USERNAME_REGEX.match(username):
            raise ValidationError("Username can only contain letters, numbers, and underscores.")
        if User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk if self.instance else None).exists():
            raise ValidationError(f'Username "{username}" is already taken.')
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email:
            raise ValidationError("Email address is required.")
        try:
            validate_email(email)
        except ValidationError:
            raise ValidationError("Please enter a valid email address.")
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk if self.instance else None).exists():
            raise ValidationError("An account with this email address already exists.")
        return email
