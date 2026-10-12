import csv
from decimal import Decimal
from django.conf import settings
from django.core.management.base import BaseCommand
from core.models import Product, Dealer


class Command(BaseCommand):
    help = "Load catalogue.csv and dealers.csv into the database idempotently."

    def handle(self, *args, **options):
        data_dir = settings.DATA_DIR

        # 1. Seed Catalogue
        cat_file = data_dir / "catalogue.csv"
        products_created = 0
        products_updated = 0

        if cat_file.exists():
            with open(cat_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sku = row["sku"].strip()
                    price = Decimal(row["price"].strip())
                    init_stock = int(row["stock"].strip())

                    product = Product.objects.filter(sku=sku).first()
                    if product:
                        product.name = row["name"].strip()
                        product.category = row["category"].strip()
                        product.brand = row["brand"].strip()
                        product.vehicle_fitment = row["vehicle_fitment"].strip()
                        product.price = price
                        product.description = row["description"].strip()
                        product.save()
                        products_updated += 1
                    else:
                        Product.objects.create(
                            sku=sku,
                            name=row["name"].strip(),
                            category=row["category"].strip(),
                            brand=row["brand"].strip(),
                            vehicle_fitment=row["vehicle_fitment"].strip(),
                            price=price,
                            stock=init_stock,
                            description=row["description"].strip(),
                        )
                        products_created += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"Catalogue seeded: {products_created} created, {products_updated} updated (total: {Product.objects.count()})"
                )
            )
        else:
            self.stdout.write(self.style.ERROR(f"File not found: {cat_file}"))

        # 2. Seed Dealers
        dealer_file = data_dir / "dealers.csv"
        dealers_created = 0
        dealers_updated = 0

        if dealer_file.exists():
            with open(dealer_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    code = row["dealer_code"].strip()
                    credit_limit = Decimal(row.get("credit_limit", "0.00").strip() or "0.00")

                    dealer, created = Dealer.objects.update_or_create(
                        dealer_code=code,
                        defaults={
                            "name": row["name"].strip(),
                            "city": row.get("city", "").strip(),
                            "phone": row.get("phone", "").strip(),
                            "email": row.get("email", "").strip(),
                            "gstin": row.get("gstin", "").strip(),
                            "credit_limit": credit_limit,
                        },
                    )
                    if created:
                        dealers_created += 1
                    else:
                        dealers_updated += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"Dealers seeded: {dealers_created} created, {dealers_updated} updated (total: {Dealer.objects.count()})"
                )
            )
        else:
            self.stdout.write(self.style.ERROR(f"File not found: {dealer_file}"))
