from django import forms

from .models import VideoProject


ALLOWED_VIDEO_EXTENSIONS = [".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"]


class VideoUploadForm(forms.ModelForm):
    class Meta:
        model = VideoProject
        fields = ["title", "original_file"]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "text-input",
                "placeholder": "My Video Project",
            }),
        }

    def clean_original_file(self):
        f = self.cleaned_data["original_file"]
        ext = ("." + f.name.rsplit(".", 1)[-1]).lower() if "." in f.name else ""
        if ext not in ALLOWED_VIDEO_EXTENSIONS:
            raise forms.ValidationError(
                f"Unsupported file type '{ext}'. Allowed types: {', '.join(ALLOWED_VIDEO_EXTENSIONS)}"
            )
        max_size = 500 * 1024 * 1024
        if f.size > max_size:
            raise forms.ValidationError("File too large. Maximum upload size is 500MB.")
        return f


class TrimForm(forms.Form):
    start_seconds = forms.FloatField(min_value=0, label="Start (seconds)")
    end_seconds = forms.FloatField(min_value=0, label="End (seconds)")
    trim_mode = forms.ChoiceField(
        choices=[("extract", "Extract"), ("delete", "Delete")],
        initial="extract",
        required=False
    )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_seconds")
        end = cleaned.get("end_seconds")
        if start is not None and end is not None and end <= start:
            raise forms.ValidationError("End time must be after start time.")
        return cleaned


class VolumeForm(forms.Form):
    volume = forms.FloatField(
        min_value=0, max_value=5,
        initial=1.0,
        label="Volume multiplier (0 = silent, 1 = original, 2 = double)",
    )


class MergeForm(forms.Form):
    clip_file = forms.FileField(label="Video clip to append")
    position = forms.ChoiceField(
        choices=[("end", "Add to end"), ("start", "Add to start")],
        initial="end",
    )


class TextOverlayForm(forms.Form):
    text = forms.CharField(max_length=200, widget=forms.TextInput(attrs={
        "class": "text-input", "placeholder": "Your caption here",
    }))
    position = forms.CharField(max_length=100, initial="bottom", widget=forms.Select(choices=[
        ("bottom", "Bottom"), ("top", "Top"), ("center", "Center"),
    ]))
    font_size = forms.IntegerField(min_value=10, max_value=400, initial=80)
    color = forms.ChoiceField(choices=[
        ("white", "White"), ("black", "Black"), ("yellow", "Yellow"),
        ("red", "Red"), ("cyan", "Cyan"),
    ], initial="white")
    start_seconds = forms.FloatField(required=False, min_value=0,
                                      label="Show from (seconds, optional)")
    end_seconds = forms.FloatField(required=False, min_value=0,
                                    label="Show until (seconds, optional)")


class SpeedForm(forms.Form):
    speed_factor = forms.FloatField(
        min_value=0.25, max_value=4.0, initial=1.0,
        label="Speed factor (0.25x - 4x)",
    )


class RotateForm(forms.Form):
    degrees = forms.ChoiceField(choices=[("90", "90°"), ("180", "180°"), ("270", "270°")])


class ResizeForm(forms.Form):
    width = forms.IntegerField(min_value=16, max_value=7680)
    height = forms.IntegerField(min_value=16, max_value=4320)


class FadeForm(forms.Form):
    fade_in_seconds = forms.FloatField(min_value=0, max_value=30, initial=1.0)
    fade_out_seconds = forms.FloatField(min_value=0, max_value=30, initial=1.0)


class BackgroundAudioForm(forms.Form):
    audio_file = forms.FileField(
        label="Audio File (MP3/WAV/AAC)",
        widget=forms.ClearableFileInput(attrs={"class": "file-input"})
    )
    start_seconds = forms.FloatField(
        required=False, min_value=0.0, initial=0.0,
        label="Start playing at (seconds)",
        widget=forms.NumberInput(attrs={"class": "text-input", "step": "0.1", "placeholder": "0.0"})
    )
    end_seconds = forms.FloatField(
        required=False, min_value=0.0,
        label="Stop playing at (seconds, optional)",
        widget=forms.NumberInput(attrs={"class": "text-input", "step": "0.1", "placeholder": "Video end"})
    )
    bg_volume = forms.FloatField(
        min_value=0.0, max_value=2.0, initial=0.5,
        label="Background music volume",
        widget=forms.NumberInput(attrs={"class": "text-input", "step": "0.1"})
    )
    video_volume = forms.FloatField(
        min_value=0.0, max_value=2.0, initial=1.0,
        label="Video original soundtrack volume",
        widget=forms.NumberInput(attrs={"class": "text-input", "step": "0.1"})
    )

    def clean_audio_file(self):
        f = self.cleaned_data["audio_file"]
        ext = ("." + f.name.rsplit(".", 1)[-1]).lower() if "." in f.name else ""
        allowed = [".mp3", ".wav", ".m4a", ".ogg", ".aac"]
        if ext not in allowed:
            raise forms.ValidationError(f"Unsupported audio type '{ext}'. Allowed types: {', '.join(allowed)}")
        return f
