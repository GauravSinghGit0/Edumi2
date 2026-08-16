"""
accounts/urls/identity_urls.py
URL routing for Centralized Identity API endpoints.
"""

from django.urls import path
from accounts.views import identity_views

urlpatterns = [
    path('me/', identity_views.identity_me_view, name='identity_me'),
    path('user/<int:user_id>/', identity_views.identity_user_view, name='identity_user'),
    path('batch/', identity_views.identity_batch_view, name='identity_batch'),
    path('update/', identity_views.identity_update_view, name='identity_update'),
]
