"""Seed script to create demo data for the CRM CPQ application.

Run this ONCE after setting up the project to populate the database with
realistic demo products, a lead, an account, an opportunity, and a quote
so you can explore the application without entering data manually.

Usage:
    # Activate your virtual environment first, then:
    python scripts/seed_demo.py

Requirements:
    - A .env file with SECRET_KEY set (or SECRET_KEY exported in your shell)
    - Database migrations already applied (python manage.py migrate)
"""
import os
import sys
import django
from decimal import Decimal

# Ensure the project root is on the Python path when running the script directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cpq_project.settings')
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402 (import after setup)
from django.utils import timezone  # noqa: E402
from datetime import timedelta  # noqa: E402

from crm.models import Account, Lead, Opportunity, Product, Quote, QuoteLineItem  # noqa: E402

User = get_user_model()


def run():
    print("Seeding demo data…")

    # ── Products ──────────────────────────────────────────────────────────────
    products_data = [
        {"name": "Sunflower Oil (5L)", "sku": "OIL-SF-5L", "base_price": Decimal("12.50"),
         "description": "Cold-pressed sunflower oil, 5-litre container"},
        {"name": "Wheat Grain (50kg)", "sku": "GRN-WH-50", "base_price": Decimal("28.00"),
         "description": "Premium milling wheat, 50 kg sack"},
        {"name": "Poultry Feed (25kg)", "sku": "FEED-PO-25", "base_price": Decimal("22.00"),
         "description": "Balanced layer pellets, 25 kg bag"},
        {"name": "Rapeseed Oil (20L)", "sku": "OIL-RS-20L", "base_price": Decimal("45.00"),
         "description": "Cold-pressed rapeseed oil, 20-litre drum"},
    ]
    products = []
    for p in products_data:
        obj, created = Product.objects.get_or_create(sku=p["sku"], defaults=p)
        if created:
            print(f"  Created product: {obj}")
        products.append(obj)

    # ── Demo staff user ───────────────────────────────────────────────────────
    staff_user, created = User.objects.get_or_create(
        username="demo_staff",
        defaults={"email": "staff@rawfoods.demo", "is_staff": True}
    )
    if created:
        staff_user.set_password("demo1234")
        staff_user.save()
        print(f"  Created staff user: {staff_user.username} / demo1234")

    # ── Lead ─────────────────────────────────────────────────────────────────
    lead, created = Lead.objects.get_or_create(
        email="buyer@greenplate.demo",
        defaults={
            "company_name": "Green Plate Catering",
            "product_interested": products[0],
            "quantity": 200,
            "status": "Qualified",
            "notes": "Delivery to Dublin 4. Weekly order preferred.",
        }
    )
    if created:
        print(f"  Created lead: {lead}")

    # ── Account ───────────────────────────────────────────────────────────────
    account, created = Account.objects.get_or_create(
        email="buyer@greenplate.demo",
        defaults={
            "company_name": "Green Plate Catering",
            "industry": "Food & Beverage",
            "contact_person_name": "Siobhán Murphy",
            "phone": "+353 1 555 0100",
            "address": "14 Merrion Square, Dublin 4, D04 XK89",
        }
    )
    if created:
        print(f"  Created account: {account}")

    # Mark the lead as converted
    if lead.converted_to_acct_id is None:
        lead.status = "Converted"
        lead.converted_to_acct_id = account
        lead.save()

    # ── Opportunity ───────────────────────────────────────────────────────────
    opp, created = Opportunity.objects.get_or_create(
        account=account,
        name="Green Plate — Q4 Supply",
        defaults={
            "description": "Quarterly supply of sunflower oil and poultry feed.",
            "stage": "Proposal",
            "status": "Open",
            "expected_close_date": (timezone.now().date() + timedelta(days=45)),
        }
    )
    if created:
        print(f"  Created opportunity: {opp}")

    # ── Quote ─────────────────────────────────────────────────────────────────
    if not opp.quotes.exists():
        quote = Quote.objects.create(
            opportunity=opp,
            discount=Decimal("5.00"),
            status="Draft",
            notes="5% early-payment discount applied.",
        )
        QuoteLineItem.objects.create(
            quote=quote, product=products[0],
            quantity=100, unit_price=Decimal("12.50"), discount=Decimal("0")
        )
        QuoteLineItem.objects.create(
            quote=quote, product=products[2],
            quantity=50, unit_price=Decimal("22.00"), discount=Decimal("0")
        )
        print(f"  Created quote: {quote} (total: €{quote.get_total()})")

    print("\nDone! Log in at http://localhost:8000/admin/ with demo_staff / demo1234")
    print("Or use the sales portal at http://localhost:8000/sales/")


if __name__ == "__main__":
    run()
