from django import forms
from django.core.exceptions import ValidationError


class FacePhotoForm(forms.Form):
    """Used when a student uploads a photo for face registration."""
    photo = forms.ImageField(
        label='Face Photo',
        help_text='Upload a clear, front-facing photo.',
        error_messages={
            'required': 'Please select a photo.',
            'invalid_image': 'The file you uploaded is not a valid image.',
        }
    )
    roll_number = forms.CharField(max_length=50, required=True, label="Roll Number")
    branch = forms.CharField(max_length=100, required=True, label="Branch")
    contact_number = forms.CharField(max_length=20, required=True, label="Contact Number")

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo:
            # Limit to 10 MB
            if photo.size > 10 * 1024 * 1024:
                raise ValidationError('Image file is too large (max 10 MB).')
            # Only allow common image formats
            allowed_types = ['image/jpeg', 'image/png', 'image/webp']
            if hasattr(photo, 'content_type') and photo.content_type not in allowed_types:
                raise ValidationError('Only JPEG, PNG, or WebP images are allowed.')
        return photo
