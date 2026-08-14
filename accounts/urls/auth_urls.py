# accounts/urls/auth_urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from accounts import views

urlpatterns = [
    path('',                              views.login_view,      name='login'),
    path('login/',                        views.login_view,      name='login-alt'),
    path('logout/',                       auth_views.LogoutView.as_view(next_page='/'), name='logout'),
    path('register/',                     views.register,        name='register'),
    path('home/',                         views.home,            name='home'),
    path('settings/',                     views.settings_view,   name='settings'),
    path('accounts/dismiss-welcome/',     views.dismiss_welcome,     name='dismiss_welcome'),
    path('accounts/save-emoji-avatar/',   views.save_emoji_avatar,   name='save_emoji_avatar'),
]
