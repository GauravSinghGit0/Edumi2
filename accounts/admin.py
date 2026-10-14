from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import UserProfile, UserAchievement, StudentPhoto, EmailVerificationOTP

User = get_user_model()


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name = "Academic & Role Profile"
    verbose_name_plural = "Academic & Role Profile"
    fk_name = "user"
    fields = (
        ('user_type', 'is_verified'),
        ('display_name', 'phone'),
        ('student_id', 'roll_number', 'branch', 'grade'),
        ('employee_id', 'department', 'specialization'),
        ('avatar_url', 'profile_picture'),
        'headline',
        'bio',
        ('created_at', 'last_seen', 'email_verified_at'),
    )
    readonly_fields = ('created_at', 'last_seen', 'email_verified_at')


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = (
        'username',
        'email',
        'get_full_name',
        'get_user_type',
        'get_is_verified',
        'is_staff',
        'is_active',
        'date_joined'
    )
    list_filter = (
        'is_staff',
        'is_superuser',
        'is_active',
        'userprofile__user_type',
        'userprofile__is_verified',
        'date_joined'
    )
    search_fields = (
        'username',
        'email',
        'first_name',
        'last_name',
        'userprofile__student_id',
        'userprofile__employee_id',
        'userprofile__display_name'
    )

    @admin.display(description='Role', ordering='userprofile__user_type')
    def get_user_type(self, obj):
        profile = getattr(obj, 'userprofile', None)
        return profile.user_type.capitalize() if profile and profile.user_type else '-'

    @admin.display(description='Verified', boolean=True, ordering='userprofile__is_verified')
    def get_is_verified(self, obj):
        profile = getattr(obj, 'userprofile', None)
        return bool(profile and profile.is_verified)


# Re-register User with enhanced UserAdmin
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass
admin.site.register(User, UserAdmin)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'get_display_name',
        'user_type',
        'student_id',
        'employee_id',
        'branch',
        'department',
        'is_verified',
        'last_seen'
    )
    list_filter = ('user_type', 'is_verified', 'branch', 'department')
    search_fields = (
        'user__username',
        'user__email',
        'user__first_name',
        'user__last_name',
        'display_name',
        'student_id',
        'employee_id'
    )
    readonly_fields = ('created_at', 'updated_at', 'last_seen', 'email_verified_at')


@admin.register(EmailVerificationOTP)
class EmailVerificationOTPAdmin(admin.ModelAdmin):
    list_display = ('user', 'is_used', 'attempts', 'created_at', 'expires_at')
    list_filter = ('is_used', 'created_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('created_at',)


@admin.register(StudentPhoto)
class StudentPhotoAdmin(admin.ModelAdmin):
    list_display = ('student', 'caption', 'uploaded_at')
    list_filter = ('uploaded_at',)
    search_fields = ('student__username', 'student__email')


@admin.register(UserAchievement)
class UserAchievementAdmin(admin.ModelAdmin):
    list_display = ('profile', 'title', 'icon_type', 'date_str', 'created_at')
    list_filter = ('icon_type', 'created_at')
    search_fields = ('profile__user__username', 'title')

