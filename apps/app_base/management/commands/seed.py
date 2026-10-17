"""Management command that seeds initial demo data.

Creates users (an ``admin`` superuser and an ``officer``), the World and System
entities, inventory product templates (animal species × stage × gender plus the
output templates they produce) and the default entity categories. The command is
idempotent and safe to run repeatedly.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

User = get_user_model()

# Animal ProductTemplates — species × stage × gender (Cow, Buffalo, Sheep, Goat).
#
# Each entry defines one ProductTemplate:
#   - animal_type    : one of Cow / Buffalo / Sheep / Goat
#   - gender         : FEMALE / MALE (normalized uppercase)
#   - stage          : Adult / Calf → part of the derived template name
#   - gives_birth_to : same-species name for Adult FEMALE templates (resolved to
#                      that species' "Calf Female" template), else None
#   - produces       : output PRODUCT templates (metadata only)
#   - tag_prefix     : prefix for auto-generated individual animal tags
ANIMAL_TEMPLATES = [
    # --- Cow ---
    {"animal_type": "Cow", "gender": "FEMALE", "stage": "Adult", "gives_birth_to": "Cow", "produces": ["Meat (Live Weight)", "Organic Manure"], "tag_prefix": "CAF"},
    {"animal_type": "Cow", "gender": "MALE", "stage": "Adult", "gives_birth_to": None, "produces": ["Meat (Live Weight)", "Organic Manure"], "tag_prefix": "CAM"},
    {"animal_type": "Cow", "gender": "MALE", "stage": "Calf", "gives_birth_to": None, "produces": ["Meat (Live Weight)", "Organic Manure"], "tag_prefix": "CCM"},
    {"animal_type": "Cow", "gender": "FEMALE", "stage": "Calf", "gives_birth_to": None, "produces": ["Meat (Live Weight)", "Organic Manure"], "tag_prefix": "CCF"},
    # --- Buffalo ---
    {"animal_type": "Buffalo", "gender": "FEMALE", "stage": "Adult", "gives_birth_to": "Buffalo", "produces": ["Meat (Live Weight)", "Organic Manure"], "tag_prefix": "BAF"},
    {"animal_type": "Buffalo", "gender": "MALE", "stage": "Adult", "gives_birth_to": None, "produces": ["Meat (Live Weight)", "Organic Manure"], "tag_prefix": "BAM"},
    {"animal_type": "Buffalo", "gender": "MALE", "stage": "Calf", "gives_birth_to": None, "produces": ["Meat (Live Weight)", "Organic Manure"], "tag_prefix": "BCM"},
    {"animal_type": "Buffalo", "gender": "FEMALE", "stage": "Calf", "gives_birth_to": None, "produces": ["Meat (Live Weight)", "Organic Manure"], "tag_prefix": "BCF"},
    # --- Sheep ---
    {"animal_type": "Sheep", "gender": "FEMALE", "stage": "Adult", "gives_birth_to": "Sheep", "produces": ["Meat (Live Weight)", "Organic Manure"], "tag_prefix": "SAF"},
    {"animal_type": "Sheep", "gender": "MALE", "stage": "Adult", "gives_birth_to": None, "produces": ["Meat (Live Weight)", "Organic Manure"], "tag_prefix": "SAM"},
    {"animal_type": "Sheep", "gender": "MALE", "stage": "Calf", "gives_birth_to": None, "produces": ["Meat (Live Weight)", "Organic Manure"], "tag_prefix": "SCM"},
    {"animal_type": "Sheep", "gender": "FEMALE", "stage": "Calf", "gives_birth_to": None, "produces": ["Meat (Live Weight)", "Organic Manure"], "tag_prefix": "SCF"},
    # --- Goat ---
    {"animal_type": "Goat", "gender": "FEMALE", "stage": "Adult", "gives_birth_to": "Goat", "produces": ["Meat (Live Weight)", "Organic Manure"], "tag_prefix": "GAF"},
    {"animal_type": "Goat", "gender": "MALE", "stage": "Adult", "gives_birth_to": None, "produces": ["Meat (Live Weight)", "Organic Manure"], "tag_prefix": "GAM"},
    {"animal_type": "Goat", "gender": "MALE", "stage": "Calf", "gives_birth_to": None, "produces": ["Meat (Live Weight)", "Organic Manure"], "tag_prefix": "GCM"},
    {"animal_type": "Goat", "gender": "FEMALE", "stage": "Calf", "gives_birth_to": None, "produces": ["Meat (Live Weight)", "Organic Manure"], "tag_prefix": "GCF"},
]


PRODUCT_TEMPLATES = [
    # (name, name_ar, nature, default_unit, has_tag, sub_category)
    # --- FEED ---
    ("Date", "بلح", "FEED", "Kg", False, "Consumable"),
    ("Barley", "شعير", "FEED", "Kg", False, "Consumable"),
    ("Wheat", "قمح", "FEED", "Kg", False, "Consumable"),
    ("Corn / Maize", "ذرة", "FEED", "Kg", False, "Consumable"),
    ("Wheat Bran", "نخالة القمح", "FEED", "Kg", False, "Consumable"),
    ("Soybean Meal", "وجبة فول الصويا", "FEED", "Kg", False, "Consumable"),
    ("Concentrated Feed Mix", "خليط علف مركز", "FEED", "Kg", False, "Consumable"),
    ("Hay", "تبن", "FEED", "Kg", False, "Consumable"),
    ("Straw", "قش", "FEED", "Kg", False, "Consumable"),
    ("Silage", "سيلاج", "FEED", "Kg", False, "Consumable"),
    ("Green Fodder", "علف أخضر", "FEED", "Kg", False, "Consumable"),
    ("Mineral & Salt Blocks", "كتل معدنية وملحية", "FEED", "Kg", False, "Consumable"),
    (
        "Vitamin Premix",
        "خليط فيتامينات مسبق التحضير",
        "FEED",
        "Kg",
        False,
        "Consumable",
    ),
    ("Alfalfa / Lucerne", "برسيم حجازي", "FEED", "Kg", False, "Consumable"),
    ("Molasses", "مولاس", "FEED", "Kg", False, "Consumable"),
    ("Cottonseed Meal", "كسب بذور القطن", "FEED", "Kg", False, "Consumable"),
    ("Fish Meal", "مسحوق السمك", "FEED", "Kg", False, "Consumable"),
    # --- MEDICINE ---
    ("Vaccines", "لقاحات", "MEDICINE", "Dose", False, "Biological"),
    ("Antibiotics", "مضادات حيوية", "MEDICINE", "Unit", False, "Biological"),
    ("Antiparasitics", "مضادات الطفيليات", "MEDICINE", "Unit", False, "Biological"),
    ("Hormones", "هرمونات", "MEDICINE", "Unit", False, "Biological"),
    (
        "Injectable Vitamins",
        "فيتامينات قابلة للحقن",
        "MEDICINE",
        "Unit",
        False,
        "Biological",
    ),
    ("Disinfectants", "مطهرات", "MEDICINE", "Liter", False, "Biological"),
    ("Wound Treatments", "علاجات الجروح", "MEDICINE", "Unit", False, "Biological"),
    ("Growth Promoters", "محفزات النمو", "MEDICINE", "Unit", False, "Biological"),
    ("Antiseptics", "مطهرات ومعقمات", "MEDICINE", "Liter", False, "Biological"),
    (
        "IV Fluids / Electrolytes",
        "سوائل وريدية / أملاح",
        "MEDICINE",
        "Unit",
        False,
        "Biological",
    ),
    # --- PRODUCT ---
    ("Raw Milk", "حليب خام", "PRODUCT", "Liter", False, "Output"),
    ("Meat (Live Weight)", "لحم (وزن حي)", "PRODUCT", "Kg", False, "Output"),
    ("Eggs", "بيض", "PRODUCT", "Piece", False, "Output"),
    ("Wool / Fiber", "صوف / ألياف", "PRODUCT", "Kg", False, "Output"),
    ("Hides / Leather", "جلود", "PRODUCT", "Piece", False, "Output"),
    ("Honey", "عسل", "PRODUCT", "Kg", False, "Output"),
    ("Organic Manure", "سماد عضوي", "PRODUCT", "Ton", False, "Output"),
    ("Offspring (Weaned)", "ذرية (مفطومة)", "PRODUCT", "Head", False, "Output"),
    ("Breeding Semen", "سائل منوي للتلقيح", "PRODUCT", "Dose", False, "Output"),
    ("Beeswax", "شمع النحل", "PRODUCT", "Kg", False, "Output"),
    ("Propolis / Bee Glue", "عكبر / صمغ النحل", "PRODUCT", "Kg", False, "Output"),
    ("Royal Jelly", "غذاء ملكات النحل", "PRODUCT", "Gram", False, "Output"),
]

# ─────────────────────────────────────────────────────────────────────────────
# Default Categories
# ─────────────────────────────────────────────────────────────────────────────

default_categories = {
    "Labor & Personnel": [
        {
            "name": "Permanent Staff Salaries",
            "desc": "Labor & Personnel: Monthly wages",
        },
        {
            "name": "Casual/Daily Labor",
            "desc": "Labor & Personnel: One-off help",
        },
        {
            "name": "Security Services",
            "desc": "Labor & Personnel: Security fees",
        },
        {
            "name": "Staff Training & PPE",
            "desc": "Labor & Personnel: Safety gear and training",
        },
        {
            "name": "Workers' Compensation",
            "desc": "Labor & Personnel: Insurance for employees",
        },
    ],
    "Professional Services": [
        {
            "name": "Veterinary Consultation",
            "desc": "Professional Services: Clinical fees",
        },
        {
            "name": "Breeding/AI Technical Fees",
            "desc": "Professional Services: AI fees",
        },
        {
            "name": "Shearing/Hoof Trimming",
            "desc": "Professional Services: Maintenance",
        },
        {
            "name": "Laboratory & Diagnostics",
            "desc": "Professional Services: Testing and lab fees",
        },
        {
            "name": "Pedigree & Registration",
            "desc": "Professional Services: Breed association fees",
        },
    ],
    "Infrastructure & Utilities": [
        {
            "name": "Electricity/Energy",
            "desc": "Utilities: Power & Heating",
        },
        {
            "name": "Water Access Fees",
            "desc": "Utilities: Pumping & Access",
        },
        {
            "name": "Machinery Servicing",
            "desc": "Utilities: Repairs labor",
        },
        {
            "name": "Irrigation Maintenance",
            "desc": "Utilities: Repairs to water systems",
        },
        {
            "name": "Waste & Manure Management",
            "desc": "Environmental: Disposal and treatment",
        },
        {
            "name": "Internet & Communications",
            "desc": "Utilities: Farm connectivity",
        },
    ],
    "Land & Logistics": [
        {
            "name": "Land Lease/Rent",
            "desc": "Fixed: Grazing land lease",
        },
        {
            "name": "Pasture Maintenance",
            "desc": "Land: Fertilizers, seeds, and weed control",
        },
        {
            "name": "Animal Transport",
            "desc": "Logistics: Trucking services",
        },
        {
            "name": "Slaughter Fees",
            "desc": "Logistics: Abattoir service fees",
        },
    ],
    "Maintenance & Fuel": [
        {
            "name": "Fuel (Diesel/Petrol)",
            "desc": "Maintenance: Vehicle and generator fuel",
        },
        {
            "name": "Lubricants & Grease",
            "desc": "Maintenance: Oil and machinery fluids",
        },
        {
            "name": "Fencing & Gate Repairs",
            "desc": "Maintenance: Boundary and paddock upkeep",
        },
        {
            "name": "Building & Shed Repairs",
            "desc": "Maintenance: Structures and roofing",
        },
        {
            "name": "Small Tools & Supplies",
            "desc": "Maintenance: Workshop consumables",
        },
    ],
    "Marketing & Sales": [
        {
            "name": "Marketing & Advertising",
            "desc": "Sales: Promoting products/livestock",
        },
        {
            "name": "Sales Commissions",
            "desc": "Sales: Broker or auctioneer fees",
        },
        {
            "name": "Packaging & Branding",
            "desc": "Sales: Labels and design",
        },
    ],
    "Administrative & Finance": [
        {
            "name": "Insurance Premiums",
            "desc": "Admin: Livestock and property coverage",
        },
        {
            "name": "Accounting & Legal",
            "desc": "Admin: Professional consultancy",
        },
        {
            "name": "Licenses & Permits",
            "desc": "Admin: Regulatory compliance fees",
        },
        {
            "name": "Bank Fees & Interest",
            "desc": "Admin: Transaction and loan costs",
        },
        {
            "name": "Stationery & Office",
            "desc": "Admin: Printing and office supplies",
        },
    ],
}


class Command(BaseCommand):
    help = "Seed initial data: users, entities, and inventory categories"

    def handle(self, *args, **options):
        with transaction.atomic():
            self._create_users()
            self._create_world_entity()
            self._create_system_entity()
            self._create_product_templates()
            self._create_default_categories()

    def _create_users(self):
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser(
                username="admin", password="admin", email="", is_staff=True
            )
            self.stdout.write(self.style.SUCCESS("Created superuser: admin"))
        else:
            self.stdout.write("Superuser 'admin' already exists, skipping.")

        self._create_officer()

    def _create_officer(self):
        if User.objects.filter(username="officer").exists():
            self.stdout.write("User 'officer' already exists, skipping.")
            return

        User.objects.create_user(
            username="officer", password="123456", email="", is_staff=True
        )
        self.stdout.write(self.style.SUCCESS("Created officer user (is_staff=True)."))

    def _create_world_entity(self):
        from apps.app_entity.models import Entity, EntityType

        if Entity.objects.filter(entity_type=EntityType.WORLD).exists():
            self.stdout.write("World entity already exists, skipping.")
            return

        Entity.create(EntityType.WORLD, active=True)
        self.stdout.write(self.style.SUCCESS("Created world entity with active fund."))

    def _create_system_entity(self):
        from apps.app_entity.models import Entity, EntityType

        if Entity.objects.filter(entity_type=EntityType.SYSTEM).exists():
            self.stdout.write("System entity already exists, skipping.")
            return

        Entity.create(EntityType.SYSTEM, active=True)
        self.stdout.write(self.style.SUCCESS("Created system entity with active fund."))

    SPECIES_SUB_CATEGORY = {
        "Cow": "Cattle",
        "Buffalo": "Buffalo",
        "Sheep": "Sheep",
        "Goat": "Goats",
    }

    @staticmethod
    def _animal_template_name(entry):
        """Derive the ProductTemplate name from an ANIMAL_TEMPLATES entry."""
        return f"{entry['animal_type']} {entry['stage']} {entry['gender'].title()}"

    def _template_defaults(self, nature, unit, tag, sub_cat):
        """Build the defaults dict for a non-animal (FEED/MEDICINE/PRODUCT)
        template."""
        from apps.app_inventory.models import ProductTemplate

        # Derive minimum_quantity from nature
        if nature == "ANIMAL" or nature == "PRODUCT":
            min_qty = Decimal("1")
        else:  # FEED or MEDICINE
            min_qty = Decimal("0.01")

        tracking_mode = (
            ProductTemplate.TrackingMode.INDIVIDUAL
            if nature == "ANIMAL"
            else ProductTemplate.TrackingMode.COMMODITY
        )
        return {
            "nature": nature,
            "default_unit": unit,
            "has_tag": tag,
            "sub_category": sub_cat,
            "minimum_quantity": min_qty,
            "tracking_mode": tracking_mode,
            "tag_prefix": "",
            "animal_type": "",
            "gender": ProductTemplate.Gender.NA,
            "can_die": nature == "ANIMAL",
            "can_be_consumed": nature != "ANIMAL",
        }

    def _animal_template_defaults(self, entry):
        """Build the defaults dict for an ANIMAL_TEMPLATES entry."""
        from apps.app_inventory.models import ProductTemplate

        return {
            "name_ar": "",
            "nature": ProductTemplate.Nature.ANIMAL,
            "sub_category": self.SPECIES_SUB_CATEGORY[entry["animal_type"]],
            "default_unit": "Head",
            "has_tag": True,
            "tag_prefix": entry.get("tag_prefix", ""),
            "minimum_quantity": Decimal("1"),
            "tracking_mode": ProductTemplate.TrackingMode.INDIVIDUAL,
            "animal_type": entry["animal_type"],
            "gender": entry["gender"],
            "can_die": True,
            "can_be_consumed": False,
        }

    def _upsert_template(
        self, template, is_new, defaults, update_fields=None, extra_values=None
    ):
        """Persist *template* from *defaults*, returning ``(created, updated)``
        increments (one of them is 1, the other 0).

        On an existing template, the fields named in ``update_fields``
        (defaults to every ``defaults`` key) are compared and written only when
        they differ. ``extra_values`` provides additional field→value pairs not
        present in ``defaults`` (e.g. the non-animal ``name_ar`` get-or-create
        argument). This preserves the historical field-compare behavior: the
        non-animal path updates only its explicit subset (excluding
        ``nature``/``default_unit``/``has_tag``), while the animal path updates
        every ``defaults`` key.
        """
        if is_new:
            return 1, 0

        fields = update_fields if update_fields is not None else list(defaults.keys())
        values = dict(defaults)
        if extra_values:
            values.update(extra_values)

        changed = False
        for field in fields:
            value = values[field]
            if getattr(template, field) != value:
                setattr(template, field, value)
                changed = True
        if changed:
            template.save()
            return 0, 1
        return 0, 0

    def _create_product_templates(self):
        from apps.app_inventory.models import ProductTemplate

        created = 0
        updated = 0

        # ── Non-animal templates (FEED / MEDICINE / PRODUCT) ──────────────
        for name, name_ar, nature, unit, tag, sub_cat in PRODUCT_TEMPLATES:
            defaults = self._template_defaults(nature, unit, tag, sub_cat)
            template, is_new = ProductTemplate.objects.get_or_create(
                name=name,
                name_ar=name_ar,
                defaults=defaults,
            )
            c, u = self._upsert_template(
                template,
                is_new,
                defaults,
                update_fields=[
                    "sub_category",
                    "minimum_quantity",
                    "tracking_mode",
                    "tag_prefix",
                    "animal_type",
                    "gender",
                    "can_die",
                    "can_be_consumed",
                ],
                extra_values={"name_ar": name_ar},
            )
            created += c
            updated += u

        # ── Animal templates (Cow / Buffalo / Sheep / Goat) ───────────────
        for entry in ANIMAL_TEMPLATES:
            name = self._animal_template_name(entry)
            defaults = self._animal_template_defaults(entry)
            template, is_new = ProductTemplate.objects.get_or_create(
                name=name,
                defaults=defaults,
            )
            c, u = self._upsert_template(template, is_new, defaults)
            created += c
            updated += u

        # ── Relationship resolution (after all templates exist) ───────────
        for entry in ANIMAL_TEMPLATES:
            name = self._animal_template_name(entry)
            try:
                template = ProductTemplate.objects.get(name=name)
            except ProductTemplate.DoesNotExist:
                continue

            # produces — M2M to output PRODUCT templates (metadata only).
            wanted = ProductTemplate.objects.filter(name__in=entry.get("produces", []))
            template.produces.set(wanted)

            # gives_birth_to — only Adult FEMALE templates give birth, to the
            # same-species "Calf Female" template. The birth flow still lets the
            # user choose the newborn gender and override the newborn template.
            target = None
            gbt = entry.get("gives_birth_to")
            if gbt and entry["stage"] == "Adult" and entry["gender"] == "FEMALE":
                target = ProductTemplate.objects.get(
                    name=f"{entry['animal_type']} Calf Female"
                )
            if template.gives_birth_to_id != (target.pk if target else None):
                template.gives_birth_to = target
                template.save()  # full_clean() validates ANIMAL target + FEMALE source

        if created or updated:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created {created} product templates, updated {updated} product templates."
                )
            )
        else:
            self.stdout.write(
                "All product templates already exist and are up to date, skipping."
            )

    def _create_default_categories(self):
        from apps.app_entity.models.category import FinancialCategory

        created = 0
        for aspect, items in default_categories.items():
            for item in items:
                _, is_new = FinancialCategory.objects.get_or_create(
                    aspect=aspect,
                    name=item["name"],
                    defaults={"description": item["desc"]},
                )
                if is_new:
                    created += 1

        if created:
            self.stdout.write(
                self.style.SUCCESS(f"Created {created} default financial categories.")
            )
        else:
            self.stdout.write("Default financial categories already exist, skipping.")
