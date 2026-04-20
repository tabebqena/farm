from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

User = get_user_model()

PRODUCT_TEMPLATES = [
    # (name, name_ar, nature, default_unit, requires_individual_tag, sub_category)
    # --- ANIMAL ---
    ("Fattening Cattle", "ماشية تسمين", "ANIMAL", "Head", True, "Cattle"),
    ("Dairy Cows", "أبقار حليب", "ANIMAL", "Head", True, "Cattle"),
    ("Breeding Bulls", "فحول تكاثر", "ANIMAL", "Head", True, "Cattle"),
    ("Replacement Heifers", "بكاير / تليعات", "ANIMAL", "Head", True, "Cattle"),
    ("Calves", "عجول", "ANIMAL", "Head", True, "Cattle"),
    ("Fattening Lambs", "خراف تسمين", "ANIMAL", "Head", True, "Sheep"),
    ("Breeding Ewes", "نعاج تكاثر", "ANIMAL", "Head", True, "Sheep"),
    ("Breeding Rams", "كباش تكاثر", "ANIMAL", "Head", True, "Sheep"),
    ("Fattening Kids", "جداء تسمين", "ANIMAL", "Head", True, "Goats"),
    ("Breeding Does", "عنزات تكاثر", "ANIMAL", "Head", True, "Goats"),
    ("Breeding Bucks", "تيوس تكاثر", "ANIMAL", "Head", True, "Goats"),
    ("Fattening Camels (Hashi)", "حاشي تسمين", "ANIMAL", "Head", True, "Camels"),
    ("Breeding / Dairy Camels", "نوق تكاثر / حليب", "ANIMAL", "Head", True, "Camels"),
    ("Stud Camels", "فحول إبل", "ANIMAL", "Head", True, "Camels"),
    ("Horses", "خيول", "ANIMAL", "Head", True, "Equine"),
    ("Donkeys / Mules", "حمير / بغال", "ANIMAL", "Head", True, "Equine"),
    ("Fattening Buffaloes", "جاموس تسمين", "ANIMAL", "Head", True, "Buffalo"),
    ("Dairy Buffaloes", "جاموس حليب", "ANIMAL", "Head", True, "Buffalo"),
    ("Breeding Buffalo Bulls", "فحول جاموس", "ANIMAL", "Head", True, "Buffalo"),
    ("Replacement Buffalo Heifers", "بكاير جاموس", "ANIMAL", "Head", True, "Buffalo"),
    ("Buffalo Calves", "عجول جاموس", "ANIMAL", "Head", True, "Buffalo"),
    ("Broiler Chickens", "دجاج تسمين", "ANIMAL", "Head", False, "Poultry"),
    ("Laying Hens", "دجاج بياض", "ANIMAL", "Head", False, "Poultry"),
    ("Poultry Parent Stock", "أمهات الدواجن", "ANIMAL", "Head", False, "Poultry"),
    ("Fattening Turkeys", "ديوك رومية تسمين", "ANIMAL", "Head", False, "Poultry"),
    ("Breeding Turkeys", "أمهات ديوك رومية", "ANIMAL", "Head", False, "Poultry"),
    ("Fattening Ducks / Geese", "بط / إوز تسمين", "ANIMAL", "Head", False, "Poultry"),
    ("Breeding Ducks / Geese", "أمهات بط وإوز", "ANIMAL", "Head", False, "Poultry"),
    ("Fattening Rabbits", "أرانب تسمين", "ANIMAL", "Head", False, "Rabbits"),
    ("Breeding Rabbits", "أمهات أرانب", "ANIMAL", "Head", False, "Rabbits"),
    ("Quails", "سمان", "ANIMAL", "Head", False, "Poultry"),
    ("Pigeons", "حمام", "ANIMAL", "Head", False, "Poultry"),
    ("Honeybee Colonies", "طوائف نحل", "ANIMAL", "Colony", False, "Apiculture"),
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


class Command(BaseCommand):
    help = "Seed initial data: users, entities, and inventory categories"

    def handle(self, *args, **options):
        with transaction.atomic():
            self._create_users()
            self._create_world_entity()
            self._create_system_entity()
            self._create_product_templates()

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

    def _create_product_templates(self):
        from apps.app_inventory.models import ProductTemplate

        created = 0
        updated = 0
        for name, name_ar, nature, unit, tag, sub_cat in PRODUCT_TEMPLATES:
            template, is_new = ProductTemplate.objects.get_or_create(
                name=name,
                name_ar=name_ar,
                defaults={
                    "nature": nature,
                    "default_unit": unit,
                    "requires_individual_tag": tag,
                    "sub_caytegory": sub_cat,
                },
            )
            if is_new:
                created += 1
            else:
                changed = False
                if template.name_ar != name_ar:
                    template.name_ar = name_ar
                    changed = True
                if template.sub_caytegory != sub_cat:
                    template.sub_caytegory = sub_cat
                    changed = True
                if changed:
                    template.save()
                    updated += 1

        if created or updated:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created {created} categories, updated {updated} categories."
                )
            )
        else:
            self.stdout.write(
                "All categories already exist and are up to date, skipping."
            )
