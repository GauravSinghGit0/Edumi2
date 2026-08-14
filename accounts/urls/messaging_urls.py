# accounts/urls/messaging_urls.py
from django.urls import path
from accounts import views

urlpatterns = [
    path('inbox/',                              views.inbox,                name='inbox'),
    path('inbox/<int:conversation_id>/',        views.conversation_detail,  name='conversation_detail'),
    path('inbox/start/<str:username>/',         views.start_conversation,   name='start_conversation'),
    path('inbox/delete/<int:conversation_id>/', views.delete_conversation,  name='delete_conversation'),
    path('inbox/send/<int:conversation_id>/',   views.send_message,         name='send_message'),
    path('inbox/search-users-ajax/',            views.search_users_ajax,    name='search_users_ajax'),
]
