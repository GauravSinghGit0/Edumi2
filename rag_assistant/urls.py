from django.urls import path
from .views import (
    rag_workspace_view,
    rag_materials_api,
    rag_chat_api,
    rag_instructor_settings_api,
    rag_sessions_api,
    rag_session_detail_api,
)

urlpatterns = [
    path('',                             rag_workspace_view,          name='rag_workspace'),
    path('api/materials/',               rag_materials_api,          name='rag_materials_api'),
    path('api/chat/',                    rag_chat_api,               name='rag_chat_api'),
    path('api/instructor-settings/',     rag_instructor_settings_api, name='rag_instructor_settings_api'),
    path('api/sessions/',                rag_sessions_api,            name='rag_sessions_api'),
    path('api/sessions/<int:session_id>/', rag_session_detail_api,    name='rag_session_detail_api'),
]

