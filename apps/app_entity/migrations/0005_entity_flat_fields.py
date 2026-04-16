from django.db import migrations, models


# def populate_entity_type_and_name(apps, schema_editor):
#     Entity = apps.get_model("app_entity", "Entity")
#     print(Entity)
#     for e in Entity.objects.select_related("person", "project").all():
#         if e.is_system:
#             e.entity_type = "system"
#             e.name = e.name or "System"
#         elif e.is_world:
#             e.entity_type = "world"
#             e.name = e.name or "World"
#         elif e.person_id:
#             e.entity_type = "person"
#             e.name = e.person.name
#             e.description = e.person.description or ""
#         elif e.project_id:
#             e.entity_type = "project"
#             e.name = e.project.name
#             e.description = e.project.description or ""
#         else:
#             e.entity_type = "person"  # fallback
#         e.save()


class Migration(migrations.Migration):

    dependencies = [
        ("app_entity", "0004_rename_private_description_person_description_and_more"),
    ]

    operations = [
        # 1. Add new flat fields (nullable/blank to allow data migration)
        migrations.AddField(
            model_name="entity",
            name="entity_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("person", "Person"),
                    ("project", "Project"),
                    ("system", "System"),
                    ("world", "World"),
                ],
                max_length=10,
                verbose_name="entity type",
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="name",
            field=models.CharField(blank=True, max_length=255, verbose_name="name"),
        ),
        migrations.AddField(
            model_name="entity",
            name="description",
            field=models.TextField(blank=True, verbose_name="description"),
        ),
        migrations.AddField(
            model_name="entity",
            name="feasibility_study",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="",
                verbose_name="feasibility study",
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="start_date",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="start date"
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="end_date",
            field=models.DateTimeField(blank=True, null=True, verbose_name="end date"),
        ),
        # 2. Populate entity_type and name from existing data
        # migrations.RunPython(
        #     populate_entity_type_and_name,
        #     reverse_code=migrations.RunPython.noop,
        # ),
        # 3. Enforce uniqueness on name now that it's populated
        migrations.AlterField(
            model_name="entity",
            name="name",
            field=models.CharField(
                blank=True, max_length=255, unique=True, verbose_name="name"
            ),
        ),
        # 4. Remove the old boolean flags
        migrations.RemoveField(model_name="entity", name="is_system"),
        migrations.RemoveField(model_name="entity", name="is_world"),
    ]
