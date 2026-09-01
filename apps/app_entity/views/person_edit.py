from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.views import View

from apps.app_base.logging_utils import audit_logger, build_error_details, logger
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity, EntityType
from apps.app_entity.forms import PersonForm


class PersonEditView(View):
    """Edit an existing Person entity."""

    def _setup(self, pk):
        """Load and validate the person entity. Returns ``(entity, response)``."""
        logger.debug(f"Fetching person entity | entity_pk={pk}")
        entity = get_object_or_404(
            Entity,
            pk=pk,
            error_message="Person not found or has been deleted."
        )
        logger.debug(
            f"Entity loaded | entity_id={entity.id} | entity_name={entity.name} | "
            f"entity_type={entity.entity_type}"
        )

        if entity.entity_type != EntityType.PERSON:
            error_msg = f"Entity {entity.id} is not a Person (type: {entity.entity_type})"
            logger.warning(error_msg)
            audit_logger.info(
                f"invalid_entity_type_for_person_edit | Entity:{entity.id} | "
                f"user={self.request.user.username} | actual_type={entity.entity_type} | "
                f"expected_type=PERSON"
            )
            messages.error(self.request, "This entity is not a Person.")
            return None, redirect("entity_list")

        self.entity = entity
        return entity, None

    def get(self, request, *args, **kwargs):
        entity, response = self._setup(kwargs["pk"])
        if response is not None:
            return response
        assert entity is not None
        logger.debug(
            f"GET request - initializing person form for editing | "
            f"entity_id={entity.id} | entity_name={entity.name}"
        )
        form = PersonForm(instance=entity)
        context = {"form": form, "entity": entity, "is_edit": True}
        return render(request, "app_entity/person_form.html", context)

    def post(self, request, *args, **kwargs):
        entity, response = self._setup(kwargs["pk"])
        if response is not None:
            return response
        assert entity is not None
        logger.debug(
            f"Processing person update | entity_id={entity.id} | "
            f"user={request.user.username}"
        )
        form = PersonForm(request.POST, instance=entity)
        logger.debug(
            f"PersonForm instantiated with POST data for update | "
            f"fields_submitted={list(request.POST.keys())}"
        )

        if form.is_valid():
            logger.debug("Form validation passed")
            try:
                with transaction.atomic():
                    form.save()
                    logger.debug(
                        f"Person updated successfully | entity_id={entity.id} | "
                        f"entity_name={entity.name}"
                    )
                    audit_logger.info(
                        f"person_updated | Entity:{entity.id} | "
                        f"user={request.user.username} | name={entity.name}"
                    )
                    messages.success(
                        request, f"Identity for {entity.name} updated successfully."
                    )
                    return redirect("entity_detail", pk=entity.pk)
            except Exception as e:
                error_details = build_error_details(
                    e,
                    extra={"entity_id": entity.id},
                    user=request.user,
                )
                logger.error(
                    f"Person update failed | "
                    f"exception_type={error_details['exception_type']} | "
                    f"error_message={error_details['error_message']} | "
                    f"entity_id={entity.id}"
                )
                audit_logger.error(
                    f"person_update_failed | Entity:{entity.id} | "
                    f"user={request.user.username} | error={error_details}"
                )
                messages.error(request, f"Update failed: {str(e)}")
        else:
            error_details = {
                "field_errors": {f: list(msgs) for f, msgs in form.errors.items()},
                "entity_id": entity.id,
                "fields_submitted": list(request.POST.keys()),
            }
            logger.warning(f"Form validation failed | {error_details}")
            audit_logger.info(
                f"person_form_validation_failed | Entity:{entity.id} | "
                f"user={request.user.username} | {error_details}"
            )

        context = {"form": form, "entity": entity, "is_edit": True}
        return render(request, "app_entity/person_form.html", context)
