from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render

from apps.app_base.debug import DebugContext, debug_view
from apps.app_entity.forms import PersonForm
from apps.app_entity.models import Entity, EntityType


@debug_view
def person_create_view(request):
    """Create a new Person entity."""
    if request.method == "POST":
        with DebugContext.section("Processing person creation request", {
            "user": request.user.username,
            "method": "POST",
        }):
            form = PersonForm(request.POST)
            DebugContext.log("PersonForm instantiated with POST data", {
                "fields_submitted": list(request.POST.keys()),
            })

            if form.is_valid():
                DebugContext.success("Form validation passed")
                try:
                    with DebugContext.section("Creating person entity and associated fund"):
                        with transaction.atomic():
                            entity = Entity.create(
                                entity_type=EntityType.PERSON,
                                **form.cleaned_data,
                            )
                            DebugContext.success("Person created successfully", {
                                "entity_id": entity.id,
                                "entity_name": entity.name,
                                "fund_id": entity.id,
                            })
                            DebugContext.audit(
                                action="person_created",
                                entity_type="Entity",
                                entity_id=entity.id,
                                details={
                                    "name": entity.name,
                                    "entity_type": "PERSON",
                                    "fund_initialized": True,
                                },
                                user=request.user.username
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
                    DebugContext.error("Person creation failed", e, data=error_details)
                    DebugContext.audit(
                        action="person_creation_failed",
                        entity_type="Entity",
                        entity_id=None,
                        details=error_details,
                        user=request.user.username
                    )
                    messages.error(request, f"System Error: {str(e)}")
            else:
                error_details = {
                    "field_errors": {f: list(msgs) for f, msgs in form.errors.items()},
                    "fields_submitted": list(request.POST.keys()),
                }
                DebugContext.warn("Form validation failed", error_details)
                DebugContext.audit(
                    action="person_form_validation_failed",
                    entity_type="Entity",
                    entity_id=None,
                    details=error_details,
                    user=request.user.username
                )
    else:
        DebugContext.log("GET request - initializing empty person form")
        form = PersonForm()

    return render(
        request, "app_entity/person_form.html", context={"edit": False, "form": form}
    )
