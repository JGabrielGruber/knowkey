from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "knowkey.core"

    def ready(self):
        from . import signals
