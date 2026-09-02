"""View for creating a new Person entity.

:class:`PersonCreateView` renders the person form and, on a valid submission,
creates the Person entity (with its fund) inside an atomic transaction.
"""

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.views import View

from apps.app_base.logging_utils import audit_logger, build_error_details, logger
from apps.app_entity.forms import PersonForm
from apps.app_entity.models import Entity, EntityType


class PersonCreateView(View):
    """Create a new Person entity."""

    def get(self, request, *args, **kwargs):
        logger.debug("GET request - initializing empty person form")
        form = PersonForm()
        return render(
            request, "app_entity/person_form.html", context={"edit": False, "form": form}
        )

    def post(self, request, *args, **kwargs):
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
                error_details = build_error_details(e, user=request.user)
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

        return render(
            request, "app_entity/person_form.html", context={"edit": False, "form": form}
        )
