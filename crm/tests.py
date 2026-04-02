"""Tests for the CRM application.

Covers core business logic (quote calculations, status state machine)
and basic authentication / authorisation for staff-only views.

Run with:
    python manage.py test crm
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .models import Account, Opportunity, Product, Quote, QuoteLineItem

User = get_user_model()


# ── Quote calculation tests ───────────────────────────────────────────────────

class QuoteCalculationTests(TestCase):
    """Verify quote subtotal, discount, and total calculations."""

    def setUp(self):
        self.product = Product.objects.create(
            name='Test Product', sku='TP-001', base_price=Decimal('100.00')
        )
        self.account = Account.objects.create(
            company_name='ACME', contact_person_name='Alice',
            email='alice@acme.com', phone='123456789'
        )
        self.opp = Opportunity.objects.create(
            account=self.account, name='Deal 1',
            expected_close_date='2099-12-31'
        )
        self.quote = Quote.objects.create(
            opportunity=self.opp, discount=Decimal('10.00')
        )
        # Two line items: 2 × €100, 1 × €50
        QuoteLineItem.objects.create(
            quote=self.quote, product=self.product,
            quantity=2, unit_price=Decimal('100.00'), discount=Decimal('0')
        )
        QuoteLineItem.objects.create(
            quote=self.quote, product=self.product,
            quantity=1, unit_price=Decimal('50.00'), discount=Decimal('0')
        )

    def test_subtotal(self):
        """Subtotal = sum of all line totals."""
        self.assertEqual(self.quote.get_subtotal(), Decimal('250.00'))

    def test_discount_amount(self):
        """10% quote-level discount on €250 subtotal = €25."""
        self.assertEqual(self.quote.get_discount_amount(), Decimal('25.00'))

    def test_total(self):
        """Final total = subtotal − discount."""
        self.assertEqual(self.quote.get_total(), Decimal('225.00'))

    def test_line_item_discount(self):
        """Per-line discount is applied correctly."""
        item = QuoteLineItem.objects.create(
            quote=self.quote, product=self.product,
            quantity=2, unit_price=Decimal('100.00'), discount=Decimal('50.00')
        )
        # 50% off 200 = 100
        self.assertEqual(item.get_line_total(), Decimal('100.00'))


# ── Quote status state machine tests ─────────────────────────────────────────

class QuoteStatusTests(TestCase):
    """Tests for quote status transitions and guard conditions."""

    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user(username='staff', password='pass')
        self.staff.is_staff = True
        self.staff.save()

        self.account = Account.objects.create(
            company_name='Acme', contact_person_name='Bob',
            email='bob@acme.com', phone='1'
        )
        self.opp = Opportunity.objects.create(
            account=self.account, name='Deal',
            expected_close_date='2099-12-31'
        )
        self.product = Product.objects.create(
            name='P', sku='P-1', base_price=Decimal('10.00')
        )
        self.quote = Quote.objects.create(opportunity=self.opp, discount=0)

    def test_submit_without_line_items_is_rejected(self):
        """Submitting a quote with no line items must leave status as Draft."""
        self.client.login(username='staff', password='pass')
        url = reverse('quote_update_status', kwargs={'pk': self.quote.id})
        self.client.post(url, {'status': 'Submitted'})
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.status, 'Draft')

    def test_submit_with_line_items_succeeds(self):
        """Submitting a quote that has at least one line item changes status."""
        QuoteLineItem.objects.create(
            quote=self.quote, product=self.product,
            quantity=1, unit_price=Decimal('10.00'), discount=0
        )
        self.client.login(username='staff', password='pass')
        url = reverse('quote_update_status', kwargs={'pk': self.quote.id})
        self.client.post(url, {'status': 'Submitted'})
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.status, 'Submitted')

    def test_approve_submitted_quote(self):
        """A Submitted quote can be Approved."""
        QuoteLineItem.objects.create(
            quote=self.quote, product=self.product,
            quantity=1, unit_price=Decimal('10.00'), discount=0
        )
        self.client.login(username='staff', password='pass')
        url = reverse('quote_update_status', kwargs={'pk': self.quote.id})
        self.client.post(url, {'status': 'Submitted'})
        self.client.post(url, {'status': 'Approved'})
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.status, 'Approved')

    def test_cannot_revert_to_draft(self):
        """Once a quote leaves Draft it cannot be reverted."""
        QuoteLineItem.objects.create(
            quote=self.quote, product=self.product,
            quantity=1, unit_price=Decimal('10.00'), discount=0
        )
        self.client.login(username='staff', password='pass')
        url = reverse('quote_update_status', kwargs={'pk': self.quote.id})
        self.client.post(url, {'status': 'Submitted'})
        self.client.post(url, {'status': 'Draft'})
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.status, 'Submitted')

    def test_can_edit_only_in_draft(self):
        """can_edit() returns True only when status is Draft."""
        self.assertTrue(self.quote.can_edit())
        self.quote.status = 'Submitted'
        self.quote.save()
        self.assertFalse(self.quote.can_edit())


# ── Auth / access control tests ───────────────────────────────────────────────

class AuthAndAccessTests(TestCase):
    """Staff-only views must be inaccessible to anonymous and regular users."""

    def setUp(self):
        self.client = Client()
        self.regular = User.objects.create_user(username='guest', password='pass')
        self.staff = User.objects.create_user(username='staff', password='pass')
        self.staff.is_staff = True
        self.staff.save()

    def test_sales_dashboard_redirects_anonymous(self):
        """Anonymous user is redirected to login."""
        resp = self.client.get(reverse('sales_dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp['Location'])

    def test_sales_dashboard_blocked_for_non_staff(self):
        """Authenticated non-staff user is redirected."""
        self.client.login(username='guest', password='pass')
        resp = self.client.get(reverse('sales_dashboard'))
        self.assertEqual(resp.status_code, 302)

    def test_sales_dashboard_accessible_for_staff(self):
        """Staff user can access the sales dashboard."""
        self.client.login(username='staff', password='pass')
        resp = self.client.get(reverse('sales_dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_home_is_public(self):
        """Home page is accessible without authentication."""
        resp = self.client.get(reverse('home'))
        self.assertEqual(resp.status_code, 200)

    def test_product_list_is_public(self):
        """Product catalogue is publicly accessible."""
        resp = self.client.get(reverse('product_list'))
        self.assertEqual(resp.status_code, 200)
