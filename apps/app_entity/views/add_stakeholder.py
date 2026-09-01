from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render

from apps.app_base.logging_utils import audit_logger, logger
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity, Stakeholder


def add_stakeholder_base(request, parent_entity_id, role_type):
    """Add a stakeholder to a project with role-based validation."""
    logger.debug(
        f"Fetching parent project entity | parent_entity_id={parent_entity_id} | "
        f"role_type={role_type}"
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
            f"user={request.user.username} | reason=not_internal | role_type={role_type}"
        )
        messages.error(request, error_msg)
        raise e

    if request.method == "POST":
        logger.debug(
            f"Processing stakeholder addition | project_id={parent_project.id} | "
            f"role_type={role_type} | user={request.user.username}"
        )
        target_id = request.POST.get("target_entity")
        logger.debug(f"Target entity ID extracted | target_id={target_id}")

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

        # Role-based validation
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
        else:
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
                return render(
                    request,
                    "app_entity/stakeholder_form.html",
                    {
                        "project_entity": parent_project,
                        "entities": [],
                        "role_type": role_type,
                        "role_name": role_type.capitalize(),
                    },
                )

            messages.success(
                request, f"Successfully added {role_type}: {target_entity}"
            )
            return redirect("entity_detail", pk=parent_project.id)

    # Filter available entities based on the role requirements
    logger.debug(f"Building available entities list | role_type={role_type}")
    if role_type == "worker":
        available = Entity.objects.filter(is_worker=True, active=True)
    elif role_type == "shareholder":
        available = Entity.objects.filter(is_shareholder=True, active=True)
    elif role_type == "vendor":
        available = Entity.objects.filter(is_vendor=True, active=True)
    elif role_type == "client":
        available = Entity.objects.filter(is_client=True, active=True)
    else:
        available = Entity.objects.none()

    # Exclude the host itself
    available = available.exclude(id=parent_project.id)
    logger.debug(f"Available entities filtered | count={available.count()} | role_type={role_type}")

    return render(
        request,
        "app_entity/stakeholder_form.html",
        {
            "project_entity": parent_project,
            "entities": available,
            "role_type": role_type,
            "role_name": role_type.capitalize(),
        },
    )


# The four specific views
def add_vendor_view(request, pk):
    """Add a vendor stakeholder."""
    return add_stakeholder_base(request, pk, "vendor")


def add_client_view(request, pk):
    """Add a client stakeholder."""
    return add_stakeholder_base(request, pk, "client")


def add_worker_view(request, pk):
    """Add a worker stakeholder."""
    return add_stakeholder_base(request, pk, "worker")


def add_shareholder_view(request, pk):
    """Add a shareholder stakeholder."""
    return add_stakeholder_base(request, pk, "shareholder")
