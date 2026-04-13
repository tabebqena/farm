from django.apps import AppConfig


class AppPersonalOperationConfig(AppConfig):
    name = "apps.app_operation"

    def ready(self):
        from apps.app_operation import signals

        signals.register()

