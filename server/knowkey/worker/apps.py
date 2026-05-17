from django.apps import AppConfig


class WorkerConfig(AppConfig):
    name = "knowkey.worker"

    def ready(self):
        from . import signals
