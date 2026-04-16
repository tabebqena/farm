from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

User = get_user_model()

CATEGORIES = [
    # (name, name_ar, nature, default_unit, requires_individual_tag)
    # --- ANIMAL ---
    ("Fattening Cattle", "ماشية التسمين", "ANIMAL", "Head", True),
    ("Dairy Cows", "أبقار الحليب", "ANIMAL", "Head", True),
    ("Breeding Bulls", "ثيران التكاثر", "ANIMAL", "Head", True),
    ("Calves", "عجول", "ANIMAL", "Head", True),
    ("Fattening Sheep", "غنم التسمين", "ANIMAL", "Head", True),
    ("Breeding Ewes", "نعاج التكاثر", "ANIMAL", "Head", True),
    ("Fattening Goats", "ماعز التسمين", "ANIMAL", "Head", True),
    ("Breeding Does", "إناث الماعز التكاثر", "ANIMAL", "Head", True),
    ("Camels", "جمال", "ANIMAL", "Head", True),
    ("Horses", "خيول", "ANIMAL", "Head", True),
    ("Donkeys / Mules", "حمير / بغال", "ANIMAL", "Head", True),
    ("Buffaloes", "جاموس", "ANIMAL", "Head", True),
    ("Broiler Chickens", "دجاج التسمين", "ANIMAL", "Head", False),
    ("Laying Hens", "دجاج البيض", "ANIMAL", "Head", False),
    ("Turkeys", "ديوك رومية", "ANIMAL", "Head", False),
    ("Ducks / Geese", "بط / إوز", "ANIMAL", "Head", False),
    ("Rabbits", "أرانب", "ANIMAL", "Head", False),
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
    # --- MEDICINE ---
    ("Vaccines", "لقاحات", "MEDICINE", "Dose", False),
    ("Antibiotics", "مضادات حيوية", "MEDICINE", "Unit", False),
    ("Antiparasitics", "مضادات الطفيليات", "MEDICINE", "Unit", False),
    ("Hormones", "هرمونات", "MEDICINE", "Unit", False),
    ("Injectable Vitamins", "فيتامينات قابلة للحقن", "MEDICINE", "Unit", False),
    ("Disinfectants", "مطهرات", "MEDICINE", "Liter", False),
    ("Wound Treatments", "علاجات الجروح", "MEDICINE", "Unit", False),
    ("Growth Promoters", "محفزات النمو", "MEDICINE", "Unit", False),
    # --- PRODUCT ---
    ("Raw Milk", "حليب خام", "PRODUCT", "Liter", False),
    ("Meat (Live Weight)", "لحم (وزن حي)", "PRODUCT", "Kg", False),
    ("Eggs", "بيض", "PRODUCT", "Piece", False),
    ("Wool / Fiber", "صوف / ألياف", "PRODUCT", "Kg", False),
    ("Hides / Leather", "جلود", "PRODUCT", "Piece", False),
    ("Honey", "عسل", "PRODUCT", "Kg", False),
    ("Organic Manure", "سماد عضوي", "PRODUCT", "Ton", False),
    ("Offspring (Weaned)", "ذرية (مفطومة)", "PRODUCT", "Head", False),
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
        from apps.app_entity.models import Entity

        if Entity.objects.filter(is_world=True).exists():
            self.stdout.write("World entity already exists, skipping.")
            return

        Entity.create(is_world=True, active=True, fund_active=True)
        self.stdout.write(self.style.SUCCESS("Created world entity with active fund."))

    def _create_system_entity(self):
        from apps.app_entity.models import Entity

        if Entity.objects.filter(is_system=True).exists():
            self.stdout.write("System entity already exists, skipping.")
            return

        Entity.create(is_system=True, active=True, fund_active=True)
        self.stdout.write(self.style.SUCCESS("Created system entity with active fund."))

    def _create_product_templates(self):
        from apps.app_inventory.models import ProductTemplate

        created = 0
        updated = 0
        for name, name_ar, nature, unit, tag in CATEGORIES:
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
