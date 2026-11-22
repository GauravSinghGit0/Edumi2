from django.apps import AppConfig


class CourseMaterialsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'course_materials'
    label = 'library'
    verbose_name = 'Digital Library & Course Materials'
