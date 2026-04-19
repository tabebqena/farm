from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

User = get_user_model()

PRODUCT_TEMPLATES = [
    # (name, name_ar, nature, default_unit, requires_individual_tag)
    # --- ANIMAL ---
    ("Fattening Cattle", "ماشية تسمين", "ANIMAL", "Head", True),
    ("Dairy Cows", "أبقار حليب", "ANIMAL", "Head", True),
    ("Breeding Bulls", "فحول تكاثر", "ANIMAL", "Head", True),
    ("Replacement Heifers", "بكاير / تليعات", "ANIMAL", "Head", True),
    ("Calves", "عجول", "ANIMAL", "Head", True),
    ("Fattening Lambs", "خراف تسمين", "ANIMAL", "Head", True),
    ("Breeding Ewes", "نعاج تكاثر", "ANIMAL", "Head", True),
    ("Breeding Rams", "كباش تكاثر", "ANIMAL", "Head", True),
    ("Fattening Kids", "جداء تسمين", "ANIMAL", "Head", True),
    ("Breeding Does", "عنزات تكاثر", "ANIMAL", "Head", True),
    ("Breeding Bucks", "تيوس تكاثر", "ANIMAL", "Head", True),
    ("Fattening Camels (Hashi)", "حاشي تسمين", "ANIMAL", "Head", True),
    ("Breeding / Dairy Camels", "نوق تكاثر / حليب", "ANIMAL", "Head", True),
    ("Stud Camels", "فحول إبل", "ANIMAL", "Head", True),
    ("Horses", "خيول", "ANIMAL", "Head", True),
    ("Donkeys / Mules", "حمير / بغال", "ANIMAL", "Head", True),
    ("Fattening Buffaloes", "جاموس تسمين", "ANIMAL", "Head", True),
    ("Dairy Buffaloes", "جاموس حليب", "ANIMAL", "Head", True),
    ("Breeding Buffalo Bulls", "فحول جاموس", "ANIMAL", "Head", True),
    ("Replacement Buffalo Heifers", "بكاير جاموس", "ANIMAL", "Head", True),
    ("Buffalo Calves", "عجول جاموس", "ANIMAL", "Head", True),
    ("Broiler Chickens", "دجاج تسمين", "ANIMAL", "Head", False),
    ("Laying Hens", "دجاج بياض", "ANIMAL", "Head", False),
    ("Poultry Parent Stock", "أمهات الدواجن", "ANIMAL", "Head", False),
    ("Fattening Turkeys", "ديوك رومية تسمين", "ANIMAL", "Head", False),
    ("Breeding Turkeys", "أمهات ديوك رومية", "ANIMAL", "Head", False),
    ("Fattening Ducks / Geese", "بط / إوز تسمين", "ANIMAL", "Head", False),
    ("Breeding Ducks / Geese", "أمهات بط وإوز", "ANIMAL", "Head", False),
    ("Fattening Rabbits", "أرانب تسمين", "ANIMAL", "Head", False),
    ("Breeding Rabbits", "أمهات أرانب", "ANIMAL", "Head", False),
    ("Quails", "سمان", "ANIMAL", "Head", False),
    ("Pigeons", "حمام", "ANIMAL", "Head", False),
    ("Honeybee Colonies", "طوائف نحل", "ANIMAL", "Colony", False),
    # --- FEED ---
    ("Barley", "شعير", "FEED", "Kg", False),
    ("Corn / Maize", "ذرة", "FEED", "Kg", False),
    ("Wheat Bran", "نخالة القمح", "FEED", "Kg", False),
    ("Soybean Meal", "وجبة فول الصويا", "FEED", "Kg", False),
    ("Concentrated Feed Mix", "خليط علف مركز", "FEED", "Kg", False),
    ("Hay", "تبن", "FEED", "Kg", False),
    ("Straw", "قش", "FEED", "Kg", False),
    ("Silage", "سيلاج", "FEED", "Kg", False),
    ("Green Fodder", "علف أخضر", "FEED", "Kg", False),
    ("Mineral & Salt Blocks", "كتل معدنية وملحية", "FEED", "Kg", False),
    ("Vitamin Premix", "خليط فيتامينات مسبق التحضير", "FEED", "Kg", False),
    ("Alfalfa / Lucerne", "برسيم حجازي", "FEED", "Kg", False),
    ("Molasses", "مولاس", "FEED", "Kg", False),
    ("Cottonseed Meal", "كسب بذور القطن", "FEED", "Kg", False),
    ("Fish Meal", "مسحوق السمك", "FEED", "Kg", False),
    # --- MEDICINE ---
    ("Vaccines", "لقاحات", "MEDICINE", "Dose", False),
    ("Antibiotics", "مضادات حيوية", "MEDICINE", "Unit", False),
    ("Antiparasitics", "مضادات الطفيليات", "MEDICINE", "Unit", False),
    ("Hormones", "هرمونات", "MEDICINE", "Unit", False),
    ("Injectable Vitamins", "فيتامينات قابلة للحقن", "MEDICINE", "Unit", False),
    ("Disinfectants", "مطهرات", "MEDICINE", "Liter", False),
    ("Wound Treatments", "علاجات الجروح", "MEDICINE", "Unit", False),
    ("Growth Promoters", "محفزات النمو", "MEDICINE", "Unit", False),
    ("Antiseptics", "مطهرات ومعقمات", "MEDICINE", "Liter", False),
    ("IV Fluids / Electrolytes", "سوائل وريدية / أملاح", "MEDICINE", "Unit", False),
    # --- PRODUCT ---
    ("Raw Milk", "حليب خام", "PRODUCT", "Liter", False),
    ("Meat (Live Weight)", "لحم (وزن حي)", "PRODUCT", "Kg", False),
    ("Eggs", "بيض", "PRODUCT", "Piece", False),
    ("Wool / Fiber", "صوف / ألياف", "PRODUCT", "Kg", False),
    ("Hides / Leather", "جلود", "PRODUCT", "Piece", False),
    ("Honey", "عسل", "PRODUCT", "Kg", False),
    ("Organic Manure", "سماد عضوي", "PRODUCT", "Ton", False),
    ("Offspring (Weaned)", "ذرية (مفطومة)", "PRODUCT", "Head", False),
    ("Breeding Semen", "سائل منوي للتلقيح", "PRODUCT", "Dose", False),
    ("Beeswax", "شمع النحل", "PRODUCT", "Kg", False),
    ("Propolis / Bee Glue", "عكبر / صمغ النحل", "PRODUCT", "Kg", False),
    ("Royal Jelly", "غذاء ملكات النحل", "PRODUCT", "Gram", False),
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
        for name, name_ar, nature, unit, tag in PRODUCT_TEMPLATES:
            template, is_new = ProductTemplate.objects.get_or_create(
                name=name,
                name_ar=name_ar,
                defaults={
                    "nature": nature,
                    "default_unit": unit,
                    "requires_individual_tag": tag,
                },
            )
            if is_new:
                created += 1
            elif template.name_ar != name_ar:
                template.name_ar = name_ar
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
