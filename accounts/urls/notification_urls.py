# accounts/urls/notification_urls.py
from django.urls import path
from accounts import notification_views

urlpatterns = [
    path('notifications/',                              notification_views.notifications_list,           name='notifications_list'),
    path('notifications/mark-read/<int:notification_id>/',   notification_views.mark_notification_read,     name='mark_notification_read'),
    path('notifications/mark-unread/<int:notification_id>/', notification_views.mark_notification_unread,   name='mark_notification_unread'),
    path('notifications/mark-all-read/',                  notification_views.mark_all_notifications_read,   name='mark_all_notifications_read'),
    path('notifications/unread-count/',                 notification_views.get_unread_count,            name='get_unread_count'),
    path('notifications/recent/',                       notification_views.get_recent_notifications,    name='get_recent_notifications'),
    path('notifications/delete/<int:notification_id>/', notification_views.delete_notification,         name='delete_notification'),
    path('notifications/broadcast/',                    notification_views.send_broadcast,              name='send_broadcast'),
]
