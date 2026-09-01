from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from apps.app_base.logging_utils import audit_logger, logger
from apps.app_entity.models import Entity, EntityType
from apps.app_entity.forms import ProjectForm


def project_create_view(request):
    """Create a new Project entity."""
    if request.method == "POST":
        logger.debug(
            f"Processing project creation request | user={request.user.username} | "
            f"method=POST"
        )
        form = ProjectForm(request.POST)
        logger.debug(
            f"ProjectForm instantiated with POST data | "
            f"fields_submitted={list(request.POST.keys())}"
        )

        if form.is_valid():
            logger.debug("Form validation passed")
            try:
                with transaction.atomic():
                    entity = Entity.create(
                        entity_type=EntityType.PROJECT,
                        **form.cleaned_data,
                    )
                    logger.debug(
                        f"Project created successfully | entity_id={entity.id} | "
                        f"entity_name={entity.name} | fund_id={entity.id}"
                    )
                    audit_logger.info(
                        f"project_created | Entity:{entity.id} | "
                        f"user={request.user.username} | name={entity.name} | "
                        f"entity_type=PROJECT | fund_initialized=True"
                    )
                    messages.success(
                        request,
                        _("Project '%(name)s' initialized with Fund ID #%(fund_id)s")
                        % {"name": entity.name, "fund_id": entity.id},
                    )
                    return redirect("entity_detail", pk=entity.pk)

            except Exception as e:
                error_details = {
                    "exception_type": type(e).__name__,
                    "error_message": str(e),
                    "user": request.user.username,
                }
                logger.error(
                    f"Project creation failed | "
                    f"exception_type={error_details['exception_type']} | "
                    f"error_message={error_details['error_message']} | "
                    f"user={request.user.username}"
                )
                audit_logger.error(
                    f"project_creation_failed | Entity:None | "
                    f"user={request.user.username} | error={error_details}"
                )
                messages.error(
                    request,
                    _("Failed to initialize project: %(error)s") % {"error": str(e)},
                )
        else:
            error_details = {
                "field_errors": {f: list(msgs) for f, msgs in form.errors.items()},
                "fields_submitted": list(request.POST.keys()),
            }
            logger.warning(f"Form validation failed | {error_details}")
            audit_logger.info(
                f"project_form_validation_failed | Entity:None | "
                f"user={request.user.username} | {error_details}"
            )
    else:
        logger.debug("GET request - initializing empty project form")
        form = ProjectForm()

    return render(request, "app_entity/project_form.html", context={"form": form})
