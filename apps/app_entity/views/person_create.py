from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render

from apps.app_base.logging_utils import audit_logger, logger
from apps.app_entity.forms import PersonForm
from apps.app_entity.models import Entity, EntityType


def person_create_view(request):
    """Create a new Person entity."""
    if request.method == "POST":
        logger.debug(
            f"Processing person creation request | user={request.user.username} | "
            f"method=POST"
        )
        form = PersonForm(request.POST)
        logger.debug(
            f"PersonForm instantiated with POST data | "
            f"fields_submitted={list(request.POST.keys())}"
        )

        if form.is_valid():
            logger.debug("Form validation passed")
            try:
                with transaction.atomic():
                    entity = Entity.create(
                        entity_type=EntityType.PERSON,
                        **form.cleaned_data,
                    )
                    logger.debug(
                        f"Person created successfully | entity_id={entity.id} | "
                        f"entity_name={entity.name} | fund_id={entity.id}"
                    )
                    audit_logger.info(
                        f"person_created | Entity:{entity.id} | "
                        f"user={request.user.username} | name={entity.name} | "
                        f"entity_type=PERSON | fund_initialized=True"
                    )
                    messages.success(
                        request,
                        f"Person {entity.name} created with Fund ID #{entity.id}",
                    )
                    return redirect("entity_detail", pk=entity.pk)

            except Exception as e:
                error_details = {
                    "exception_type": type(e).__name__,
                    "error_message": str(e),
                    "user": request.user.username,
                }
                logger.error(
                    f"Person creation failed | "
                    f"exception_type={error_details['exception_type']} | "
                    f"error_message={error_details['error_message']} | "
                    f"user={request.user.username}"
                )
                audit_logger.error(
                    f"person_creation_failed | Entity:None | "
                    f"user={request.user.username} | error={error_details}"
                )
                messages.error(request, f"System Error: {str(e)}")
        else:
            error_details = {
                "field_errors": {f: list(msgs) for f, msgs in form.errors.items()},
                "fields_submitted": list(request.POST.keys()),
            }
            logger.warning(f"Form validation failed | {error_details}")
            audit_logger.info(
                f"person_form_validation_failed | Entity:None | "
                f"user={request.user.username} | {error_details}"
            )
    else:
        logger.debug("GET request - initializing empty person form")
        form = PersonForm()

    return render(
        request, "app_entity/person_form.html", context={"edit": False, "form": form}
    )
