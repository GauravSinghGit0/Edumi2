# accounts/urls/__init__.py
# This is the file Django loads for include('accounts.urls')
#
# Sub-files:
#   auth_urls.py          — login, register, logout, home, settings, welcome, emoji-avatar
#   profile_urls.py       — teacher/student dashboards, profile view/edit, directory, search
#   admin_urls.py         — admin panel, user management, delete user, architecture, list views
#   messaging_urls.py     — inbox, conversations, send message
#   notification_urls.py  — notification list, mark-read, unread count, broadcast

from django.urls import path, include

urlpatterns = [
    path('', include('accounts.urls.auth_urls')),
    path('', include('accounts.urls.profile_urls')),
    path('', include('accounts.urls.admin_urls')),
    path('', include('accounts.urls.messaging_urls')),
    path('', include('accounts.urls.notification_urls')),
]
