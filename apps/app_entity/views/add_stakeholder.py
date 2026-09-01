from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.views import View

from apps.app_base.logging_utils import audit_logger, logger
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity, Stakeholder


def _role_filter(role_type):
    """Eligibility queryset filter kwargs for a stakeholder role.

    Returns ``None`` for unknown roles (the caller then renders an empty list).
    """
    if role_type == "worker":
        return {"is_worker": True, "active": True}
    if role_type == "shareholder":
        return {"is_shareholder": True, "active": True}
    if role_type == "vendor":
        return {"is_vendor": True, "active": True}
    if role_type == "client":
        return {"is_client": True, "active": True}
    return None


class AddStakeholderView(View):
    """Add a stakeholder to a project with role-based validation.

    Concrete subclasses set ``role_type`` (e.g. ``"vendor"``, ``"client"``,
    ``"worker"``, ``"shareholder"``).
    """

    role_type: str
    template_name = "app_entity/stakeholder_form.html"

    def _load_parent(self, parent_entity_id):
        """Load the internal parent project, or re-raise the 404 with auditing."""
        logger.debug(
            f"Fetching parent project entity | parent_entity_id={parent_entity_id} | "
            f"role_type={self.role_type}"
        )
        try:
            parent_project = get_object_or_404(
                Entity,
                pk=parent_entity_id,
                is_internal=True,
                error_message="Project not found or is not configured as internal."
            )
            logger.debug(
                f"Parent project loaded | project_id={parent_project.id} | "
                f"project_name={parent_project.name}"
            )
        except Http404 as e:
            error_msg = f"No project match the supplied query pk{parent_entity_id} is_internal:{True}"
            logger.error(error_msg)
            audit_logger.info(
                f"invalid_parent_project_for_stakeholder_add | Entity:{parent_entity_id} | "
                f"user={self.request.user.username} | reason=not_internal | "
                f"role_type={self.role_type}"
            )
            messages.error(self.request, error_msg)
            raise e
        return parent_project

    def _load_target(self, request, target_id):
        """Load the selected target entity (must be active)."""
        target_entity = get_object_or_404(
            Entity,
            pk=target_id,
            active=True,
            error_message="Entity not found or is not active."
        )
        logger.debug(
            f"Target entity loaded | target_id={target_entity.id} | "
            f"target_name={target_entity.name}"
        )
        return target_entity

    def _validate_role_target(self, request, role_type, target_entity):
        """Validate the target against the role's requirements.

        Returns ``(error_msg, validation_details)``. On failure the validation is
        also logged, audited, and surfaced as an error message.
        """
        error_msg = None
        validation_details = {
            "role_type": role_type,
            "target_id": target_entity.id,
            "is_person": target_entity.is_person,
            "is_vendor": target_entity.is_vendor,
            "is_client": target_entity.is_client,
        }

        if role_type == "worker" and not target_entity.is_person:
            error_msg = "Only People can be assigned as Workers."
            validation_details["error_reason"] = "not_a_person"
        elif role_type == "shareholder" and not target_entity.is_person:
            error_msg = "Only People can be assigned as Shareholders."
            validation_details["error_reason"] = "not_a_person"
        elif role_type == "vendor" and not target_entity.is_vendor:
            error_msg = f"{target_entity} is not configured as a Vendor."
            validation_details["error_reason"] = "not_configured_as_vendor"
        elif role_type == "client" and not target_entity.is_client:
            error_msg = f"{target_entity} is not configured as a Client."
            validation_details["error_reason"] = "not_configured_as_client"

        if error_msg:
            logger.warning(f"Stakeholder validation failed | {validation_details}")
            audit_logger.info(
                f"stakeholder_validation_failed | Stakeholder:None | "
                f"user={request.user.username} | {validation_details}"
            )
            messages.error(request, f"Configuration Error: {error_msg}")
        return error_msg, validation_details

    def _create_stakeholder(self, request, parent_project, target_entity, role_type):
        """Create (or fetch) the stakeholder link.

        Returns the success redirect on success, ``None`` when creation failed
        (the caller re-renders the error form).
        """
        try:
            stakeholder, created = Stakeholder.objects.get_or_create(
                parent=parent_project,
                target=target_entity,
                role=role_type,
            )
            created_status = "created" if created else "already_exists"
            logger.debug(
                f"Stakeholder {created_status} | stakeholder_id={stakeholder.id} | "
                f"project_id={parent_project.id} | target_id={target_entity.id} | "
                f"role={role_type}"
            )
            audit_logger.info(
                f"stakeholder_{created_status} | Stakeholder:{stakeholder.id} | "
                f"user={request.user.username} | project_id={parent_project.id} | "
                f"target_id={target_entity.id} | role={role_type}"
            )
        except Exception as e:
            error_details = {
                "exception_type": type(e).__name__,
                "error_message": str(e),
                "project_id": parent_project.id,
                "target_id": target_entity.id,
                "role_type": role_type,
                "user": request.user.username,
            }
            logger.error(
                f"Stakeholder creation failed | "
                f"exception_type={error_details['exception_type']} | "
                f"error_message={error_details['error_message']} | "
                f"project_id={parent_project.id}"
            )
            audit_logger.error(
                f"stakeholder_creation_failed | Stakeholder:None | "
                f"user={request.user.username} | error={error_details}"
            )
            messages.error(request, f"Error creating stakeholder: {str(e)}")
            return None

        messages.success(
            request, f"Successfully added {role_type}: {target_entity}"
        )
        return redirect("entity_detail", pk=parent_project.id)

    def _render_form(self, parent_project, available_entities, role_type):
        return render(
            self.request,
            self.template_name,
            {
                "project_entity": parent_project,
                "entities": available_entities,
                "role_type": role_type,
                "role_name": role_type.capitalize(),
            },
        )

    def _render_error(self, parent_project, role_type):
        """Re-render the form with an empty eligible-entity dropdown."""
        return self._render_form(parent_project, Entity.objects.none(), role_type)

    def get(self, request, *args, **kwargs):
        parent_project = self._load_parent(kwargs["pk"])
        role_type = self.role_type

        # Filter available entities based on the role requirements
        logger.debug(f"Building available entities list | role_type={role_type}")
        filter_kwargs = _role_filter(role_type)
        available = (
            Entity.objects.filter(**filter_kwargs).exclude(id=parent_project.id)
            if filter_kwargs
            else Entity.objects.none()
        )
        logger.debug(
            f"Available entities filtered | count={available.count()} | role_type={role_type}"
        )

        return self._render_form(parent_project, available, role_type)

    def post(self, request, *args, **kwargs):
        parent_project = self._load_parent(kwargs["pk"])
        role_type = self.role_type
        logger.debug(
            f"Processing stakeholder addition | project_id={parent_project.id} | "
            f"role_type={role_type} | user={request.user.username}"
        )
        target_id = request.POST.get("target_entity")
        logger.debug(f"Target entity ID extracted | target_id={target_id}")

        target_entity = self._load_target(request, target_id)

        error_msg, _ = self._validate_role_target(request, role_type, target_entity)
        if error_msg:
            return self._render_error(parent_project, role_type)

        response = self._create_stakeholder(
            request, parent_project, target_entity, role_type
        )
        if response is not None:
            return response
        return self._render_error(parent_project, role_type)


class AddVendorView(AddStakeholderView):
    """Add a vendor stakeholder."""

    role_type = "vendor"


class AddClientView(AddStakeholderView):
    """Add a client stakeholder."""

    role_type = "client"


class AddWorkerView(AddStakeholderView):
    """Add a worker stakeholder."""

    role_type = "worker"


class AddShareholderView(AddStakeholderView):
    """Add a shareholder stakeholder."""

    role_type = "shareholder"
