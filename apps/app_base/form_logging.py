"""
Form logging mixin using standard logging.
"""

from apps.app_base.logging_utils import audit_logger, logger


class LoggingFormMixin:
    """Mixin for Django forms that adds concise validation/save logging."""

    def clean(self):
        """Log form validation."""
        form_name = self.__class__.__name__
        instance = getattr(self, "instance", None)
        instance_pk = getattr(instance, "pk", None)
        logger.debug(
            f"{form_name}.clean() | form={form_name} | "
            f"has_instance={bool(instance)} | instance_pk={instance_pk}"
        )

        try:
            cleaned_data = super().clean()
            if self.errors:
                error_summary = {f: list(msgs) for f, msgs in self.errors.items()}
                logger.warning(f"{form_name} validation has errors | {error_summary}")
            return cleaned_data
        except Exception as e:
            logger.error(f"{form_name} validation failed | {e}")
            raise

    def clean_field(self, field_name: str):
        """Helper to log individual field validation."""
        field = self.fields.get(field_name)
        if not field:
            return

        value = self.cleaned_data.get(field_name)
        logger.debug(
            f"Validating {self.__class__.__name__}.{field_name} | "
            f"has_value={value is not None and value != ''} | "
            f"value_type={type(value).__name__}"
        )

    def save(self, commit=True):
        """Log form save operations and audit commits."""
        form_name = self.__class__.__name__
        is_new = not self.instance or not self.instance.pk
        action = "create" if is_new else "update"

        try:
            instance = super().save(commit=commit)
            logger.debug(
                f"{form_name} saved | action={action} | "
                f"instance_pk={getattr(instance, 'pk', None)}"
            )

            if commit:
                entity_type = (
                    self._meta.model.__name__
                    if hasattr(self, "_meta") and self._meta
                    else "Unknown"
                )
                audit_logger.info(
                    f"form_{action} | {entity_type}:{getattr(instance, 'pk', None)} | "
                    f"user=system | form={form_name}"
                )

            return instance
        except Exception as e:
            logger.error(f"{form_name} save failed | {e}")
            raise
