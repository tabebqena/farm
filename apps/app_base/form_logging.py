"""
Form logging mixin for comprehensive validation and field-level logging.
"""

from apps.app_base.debug import DebugContext


class LoggingFormMixin:
    """Mixin for Django forms that adds comprehensive validation logging."""

    def clean(self):
        """Log form validation."""
        form_name = self.__class__.__name__
        instance = getattr(self, "instance", None)
        instance_pk = getattr(instance, "pk", None)
        DebugContext.log(
            f"{form_name}.clean()",
            {
                "form": form_name,
                "has_instance": bool(instance),
                "instance_pk": getattr(instance, "pk", None),
                "is_new": not instance_pk,
            },
        )

        try:
            cleaned_data = super().clean()
            if not self.errors:
                DebugContext.success(
                    f"{form_name} validation passed",
                    {
                        "fields_count": len(self.fields),
                    },
                )
            else:
                error_summary = {f: list(msgs) for f, msgs in self.errors.items()}
                DebugContext.warn(f"{form_name} validation has errors", error_summary)
            return cleaned_data
        except Exception as e:
            DebugContext.error(f"{form_name} validation failed", e)
            raise

    def clean_field(self, field_name: str):
        """Helper to log individual field validation."""
        field = self.fields.get(field_name)
        if not field:
            return

        value = self.cleaned_data.get(field_name)
        DebugContext.log(
            f"Validating {self.__class__.__name__}.{field_name}",
            {
                "field": field_name,
                "has_value": value is not None and value != "",
                "value_type": type(value).__name__,
            },
        )

    def save(self, commit=True):
        """Log form save operations."""
        form_name = self.__class__.__name__
        is_new = not self.instance or not self.instance.pk
        action = "create" if is_new else "update"

        with DebugContext.section(
            f"{form_name}.save() ({action})",
            {
                "form": form_name,
                "is_new": is_new,
                "instance_pk": (
                    self.instance.pk if self.instance and self.instance.pk else None
                ),
                "commit": commit,
            },
        ):
            try:
                instance = super().save(commit=commit)
                DebugContext.success(
                    f"{form_name} saved",
                    {
                        "instance_pk": instance.pk if instance else None,
                        "action": action,
                    },
                )

                if commit:
                    DebugContext.audit(
                        action=f"form_{action}",
                        entity_type=(
                            self._meta.model.__name__
                            if hasattr(self, "_meta") and self._meta
                            else "Unknown"
                        ),
                        entity_id=instance.pk if instance else None,
                        details={"form": form_name},
                        user="system",
                    )

                return instance
            except Exception as e:
                DebugContext.error(f"{form_name} save failed", e)
                raise
