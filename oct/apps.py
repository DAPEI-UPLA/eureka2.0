from django.apps import AppConfig

class OctConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'oct'

    def ready(self):
        import oct.signals