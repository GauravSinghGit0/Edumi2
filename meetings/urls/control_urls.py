# meetings/urls/control_urls.py
from django.urls import path
from meetings.views import (
    sleep_meeting, unfreeze_meeting, get_meeting_status,
    kick_participant, revoke_ban, get_banned_users, meeting_global_control,
)

urlpatterns = [
    path('sleep/<str:meeting_code>/',                   sleep_meeting,           name='sleep_meeting'),
    path('unfreeze/<str:meeting_code>/',                unfreeze_meeting,        name='unfreeze_meeting'),
    path('status/<str:meeting_code>/',                  get_meeting_status,      name='get_meeting_status'),
    path('kick/<int:meeting_id>/<int:user_id>/',        kick_participant,        name='kick_participant'),
    path('revoke-ban/<int:meeting_id>/<int:user_id>/',  revoke_ban,              name='revoke_ban'),
    path('banned-users/<int:meeting_id>/',              get_banned_users,        name='get_banned_users'),
    path('global-control/<int:meeting_id>/',            meeting_global_control,  name='meeting_global_control'),
]
