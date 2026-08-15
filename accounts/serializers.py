"""
Registration Serializer / Validator for Edumi2 LMS.
Provides industry-standard field-level validation, Django built-in password validators,
regex format checks, and structured field-specific error messaging.
"""
import re
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction

from accounts.models import UserProfile

User = get_user_model()

USERNAME_REGEX = re.compile(r'^[a-zA-Z0-9_]{3,30}$')


class RegistrationSerializer:
    """
    Validates and creates users during registration.
    Produces field-specific errors compatible with standard form views and JSON APIs.
    """

    ALLOWED_ROLES = ('student', 'teacher')

    def __init__(self, data=None):
        self.data = data or {}
        self._errors = {}
        self._cleaned_data = {}
        self._is_validated = False

    @property
    def errors(self):
        return self._errors

    @property
    def cleaned_data(self):
        return self._cleaned_data

    def is_valid(self):
        self._errors = {}
        self._cleaned_data = {}
        self._is_validated = True

        # 1. Validate Username
        raw_username = str(self.data.get('username') or '').strip()
        if not raw_username:
            self._add_error('username', 'Username is required.')
        elif len(raw_username) < 3 or len(raw_username) > 30:
            self._add_error('username', 'Username must be between 3 and 30 characters long.')
        elif ' ' in raw_username:
            self._add_error('username', 'Username cannot contain spaces.')
        elif not USERNAME_REGEX.match(raw_username):
            self._add_error('username', 'Username can only contain alphanumeric characters and underscores.')
        else:
            if User.objects.filter(username__iexact=raw_username).exists():
                self._add_error('username', f'Username "{raw_username}" is already taken.')
            else:
                self._cleaned_data['username'] = raw_username

        # 2. Validate Email
        raw_email = str(self.data.get('email') or '').strip().lower()
        if not raw_email:
            self._add_error('email', 'Email address is required.')
        else:
            try:
                validate_email(raw_email)
                if User.objects.filter(email__iexact=raw_email).exists():
                    self._add_error('email', 'An account with this email address already exists.')
                else:
                    self._cleaned_data['email'] = raw_email
            except ValidationError:
                self._add_error('email', 'Please enter a valid email address.')

        # 3. Validate Role / User Type
        user_type = str(self.data.get('user_type') or '').strip().lower()
        if not user_type:
            self._add_error('user_type', 'Please select your role (Student or Teacher).')
        elif user_type not in self.ALLOWED_ROLES:
            self._add_error('user_type', f'Invalid role selected. Must be one of: {", ".join(self.ALLOWED_ROLES)}.')
        else:
            self._cleaned_data['user_type'] = user_type

        # 4. Validate Passwords
        password1 = str(self.data.get('password1') or '')
        password2 = str(self.data.get('password2') or '')

        if not password1:
            self._add_error('password1', 'Password is required.')
        if not password2:
            self._add_error('password2', 'Please confirm your password.')

        if password1 and password2:
            if password1 != password2:
                self._add_error('password2', 'Passwords do not match.')
            else:
                # Run Django built-in password validators
                temp_user = User(
                    username=self._cleaned_data.get('username', ''),
                    email=self._cleaned_data.get('email', '')
                )
                try:
                    validate_password(password1, user=temp_user)
                    self._cleaned_data['password'] = password1
                except ValidationError as e:
                    for msg in e.messages:
                        self._add_error('password1', msg)

        return len(self._errors) == 0

    def _add_error(self, field, message):
        if field not in self._errors:
            self._errors[field] = []
        if message not in self._errors[field]:
            self._errors[field].append(message)

    def save(self):
        """
        Creates User and UserProfile.
        Returns the created User instance with is_verified=False.
        """
        if not self._is_validated or self._errors:
            raise ValueError(f"Cannot save invalid registration data: {self._errors}")

        username = self._cleaned_data['username']
        email = self._cleaned_data['email']
        password = self._cleaned_data['password']
        user_type = self._cleaned_data['user_type']

        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                is_active=True
            )
            profile, _ = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'user_type': user_type,
                    'is_verified': False,
                    'email_verified_at': None
                }
            )
            if profile.user_type != user_type or profile.is_verified:
                profile.user_type = user_type
                profile.is_verified = False
                profile.email_verified_at = None
                profile.save(update_fields=['user_type', 'is_verified', 'email_verified_at'])

        return user
