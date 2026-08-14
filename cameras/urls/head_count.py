
from django.urls import path
from .. import views

urlpatterns = [
    path('head-count/', views.head_count_dashboard, name='head_count_dashboard'),
    path('head-count/start/<str:camera_type>/<int:camera_id>/', views.start_head_count, name='start_head_count'),
    path('head-count/stop/<str:camera_type>/<int:camera_id>/', views.stop_head_count, name='stop_head_count'),
    path('head-count/logs/', views.head_count_logs, name='head_count_logs'),
    path('head-count/logs/<int:log_id>/', views.head_count_log_detail, name='head_count_log_detail'),
    path('head-count/sessions/', views.head_count_session_history, name='head_count_session_history'),
    path('head-count/api/<str:camera_type>/<int:camera_id>/', views.head_count_api, name='head_count_api'),
    path('head-count/report/', views.head_count_report, name='head_count_report'),
    path('head-count/export/', views.export_head_count_csv, name='export_head_count_csv'),
]
