from django import forms
from django.utils.translation import gettext_lazy as _

from apps.app_base.form_logging import LoggingFormMixin
from apps.app_entity.models import Entity, EntityType


class PersonForm(LoggingFormMixin, forms.ModelForm):
    """Form for editing a Person entity."""

    class Meta:
        model = Entity
        fields = (
            "name",
            "description",
            "is_worker",
            "is_vendor",
            "is_client",
            "is_shareholder",
            "is_internal",
            "active",
        )
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("Full name")}
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": _("Personal notes"),
                }
            ),
            "is_worker": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_vendor": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_client": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_shareholder": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_internal": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "name": _("Name"),
            "description": _("Private Description"),
            "is_worker": _("Worker"),
            "is_vendor": _("Vendor"),
            "is_client": _("Client"),
            "is_shareholder": _("Shareholder"),
            "is_internal": _("Internal Entity"),
            "active": _("Active"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = True
        self.instance.entity_type = EntityType.PERSON

    def clean_name(self):
        from apps.app_base.debug import DebugContext

        name = self.cleaned_data.get("name")
        DebugContext.log("PersonForm.clean_name()", {
            "name": name[:50] if name else "",
            "is_update": bool(self.instance and self.instance.pk),
        })

        if not name:
            DebugContext.warn("Name is required")
            raise forms.ValidationError(_("Name is required."))

        # Check uniqueness excluding current instance
        existing = Entity.objects.filter(name=name)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)

        if existing.exists():
            DebugContext.warn("Entity with this name already exists", {
                "name": name,
            })
            raise forms.ValidationError(_("An entity with this name already exists."))

        DebugContext.success("Name validation passed", {"name": name[:50] if name else ""})
        return name


class ProjectForm(LoggingFormMixin, forms.ModelForm):
    """Form for editing a Project entity."""

    class Meta:
        model = Entity
        fields = (
            "name",
            "description",
            "is_client",
            "is_vendor",
            "is_internal",
            "active",
        )
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("Project name")}
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": _("Project scope and goals"),
                }
            ),
            "is_client": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_vendor": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_internal": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "name": _("Project Name"),
            "description": _("Description / Scope"),
            "is_client": _("Act as Client (Can receive invoices)"),
            "is_vendor": _("Act as Vendor (Can charge expenses)"),
            "is_internal": _("Internal Project"),
            "active": _("Active"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = True

    def clean_name(self):
        from apps.app_base.debug import DebugContext

        name = self.cleaned_data.get("name")
        DebugContext.log("ProjectForm.clean_name()", {
            "name": name[:50] if name else "",
            "is_update": bool(self.instance and self.instance.pk),
        })

        if not name:
            DebugContext.warn("Project name is required")
            raise forms.ValidationError(_("Project name is required."))

        # Check uniqueness excluding current instance
        existing = Entity.objects.filter(name=name)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)

        if existing.exists():
            DebugContext.warn("Project with this name already exists", {"name": name})
            raise forms.ValidationError(_("A project with this name already exists."))

        DebugContext.success("Project name validation passed", {"name": name[:50] if name else ""})
        return name
