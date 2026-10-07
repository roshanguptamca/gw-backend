from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from importlib import import_module
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase, override_settings

from PIL import Image
from pypdf import PdfReader
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.test import APIClient

from apps.marketplace.billing.invoice_service import create_invoice
from apps.marketplace.billing.models import Invoice, InvoiceItem, InvoicePDF, InvoiceSequence
from apps.marketplace.billing.pdf_service import invoice_html, invoice_pdf, snapshot_logo
from apps.marketplace.billing.vat_service import allocate_discount, extract_vat, vat_summary
from apps.marketplace.models import Coupon, Order, OrderItem, Product
from apps.marketplace.services import (
    _create_order_atomic,
    create_seller_with_shop,
    link_guest_orders_to_user,
    send_buyer_confirmation_email,
)

User = get_user_model()


class VATTests(TestCase):
    def test_extract_inclusive_vat(self):
        self.assertEqual(extract_vat(Decimal("10.00"), Decimal("9")), (Decimal("9.17"), Decimal("0.83")))

    def test_round_half_up_at_cent_boundary(self):
        self.assertEqual(extract_vat(Decimal("0.03"), Decimal("20")), (Decimal("0.03"), Decimal("0.00")))

    def test_zero_rate_and_invalid_rate(self):
        self.assertEqual(extract_vat(Decimal("10"), Decimal("0")), (Decimal("10.00"), Decimal("0.00")))
        for rate in (Decimal("-1"), Decimal("101")):
            with self.assertRaises(ValueError):
                extract_vat(Decimal("10"), rate)

    def test_discount_allocation_conserves_cents_and_is_stable(self):
        self.assertEqual(
            allocate_discount(Decimal("0.02"), [Decimal("1.00")] * 3),
            [Decimal("0.01"), Decimal("0.01"), Decimal("0.00")],
        )
        self.assertEqual(allocate_discount(Decimal("0"), [Decimal("0")]), [Decimal("0.00")])
        with self.assertRaises(ValueError):
            allocate_discount(Decimal("2"), [Decimal("1")])


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class BillingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.buyer = User.objects.create_user(username="billing-buyer", email="buyer@example.com")
        self.other_buyer = User.objects.create_user(username="other-billing-buyer")
        self.admin = User.objects.create_superuser(username="billing-admin", email="admin@example.com", password="test")
        self.seller, _, self.shop = create_seller_with_shop(
            email="billing-seller@example.com",
            password="test",
            first_name="Seller",
            last_name="One",
            business_name="Billing Shop",
            address="Seller Lane 1",
            city="Amsterdam",
        )
        self.other_seller, _, self.other_shop = create_seller_with_shop(
            email="billing-seller-two@example.com",
            password="test",
            first_name="Seller",
            last_name="Two",
            business_name="Other Shop",
        )
        for shop in (self.shop, self.other_shop):
            shop.is_approved = True
            shop.delivery_available = True
            shop.save()
        settings = self.shop.settings
        settings.invoice_prefix = "RK"
        settings.vat_number = "1111111111"
        settings.invoice_iban = "ABNAXXXXXXXXX"
        settings.default_vat_rate = Decimal("9")
        settings.local_delivery_fee = Decimal("2.50")
        settings.save()
        self.product = Product.objects.create(
            shop=self.shop,
            name="Product One",
            slug="product-one",
            price=Decimal("10.00"),
            sku="BILL-1",
            stock_quantity=100,
            is_approved=True,
        )
        self.product_two = Product.objects.create(
            shop=self.shop,
            name="Product Two",
            slug="product-two",
            price=Decimal("12.10"),
            vat_rate=Decimal("21"),
            stock_quantity=100,
            is_approved=True,
        )
        self.other_product = Product.objects.create(
            shop=self.other_shop,
            name="Other Product",
            slug="other-product",
            price=Decimal("5"),
            stock_quantity=100,
            is_approved=True,
        )

    def order(self, *, shop=None, product=None, user=None, **overrides):
        shop = shop or self.shop
        product = product or self.product
        payload = {
            "shop_id": shop.pk,
            "customer_name": "Buyer Snapshot",
            "customer_email": "buyer@example.com",
            "customer_phone": "1234",
            "terms_accepted": True,
            "payment_method": "cash",
            "order_type": "pickup",
            "items": [{"product_id": product.pk, "quantity": 2}],
        }
        payload.update(overrides)
        return _create_order_atomic(payload, user=user)

    def test_single_shop_snapshot_and_invoice_totals(self):
        order = self.order(user=self.buyer, billing_address="Buyer Lane 2")
        invoice = order.invoices.get()
        self.assertEqual(invoice.customer, self.buyer)
        self.assertEqual(invoice.customer_snapshot["address"], "Buyer Lane 2")
        self.assertEqual(invoice.customer_snapshot["name"], "Buyer Snapshot")
        self.assertEqual(invoice.customer_snapshot["email"], "buyer@example.com")
        self.assertEqual(invoice.seller_snapshot["address_line1"], "Seller Lane 1")
        self.assertEqual(invoice.seller_snapshot["vat_number"], "1111111111")
        self.assertEqual(invoice.total_inc_vat, order.total)
        self.assertEqual(invoice.subtotal_ex_vat + invoice.vat_total, order.total)
        item = invoice.items.get()
        self.assertEqual(item.sku, "BILL-1")
        self.assertEqual(item.vat_rate, Decimal("9"))
        self.assertEqual(item.vat_amount, Decimal("1.65"))

    def test_multi_shop_cart_preserves_separate_orders_invoices_and_emails(self):
        first = self.order(user=self.buyer)
        second = self.order(shop=self.other_shop, product=self.other_product, user=self.buyer)
        send_buyer_confirmation_email(first)
        send_buyer_confirmation_email(second)
        self.assertEqual(Invoice.objects.count(), 2)
        self.assertEqual(len(mail.outbox), 2)
        for order, email in zip((first, second), mail.outbox):
            invoice = order.invoices.get()
            self.assertEqual(invoice.shop, order.shop)
            self.assertEqual(invoice.total_inc_vat, order.total)
            self.assertEqual(len(email.attachments), 1)
            self.assertEqual(email.attachments[0][0], f"{invoice.invoice_number}.pdf")
            self.assertEqual(invoice.items.get().order_item.order, order)
        self.assertNotIn("Other Product", invoice_html(first.invoices.get()))
        self.assertNotIn("Product One", invoice_html(second.invoices.get()))

    def test_mixed_rates_discounts_shipping_exactly_reconcile(self):
        Coupon.objects.create(shop=self.shop, code="SAVE", discount_type="fixed", discount_value=Decimal("1.01"))
        order = self.order(
            coupon_code="SAVE",
            order_type="delivery",
            delivery_address="Buyer Street",
            items=[{"product_id": self.product.pk, "quantity": 1}, {"product_id": self.product_two.pk, "quantity": 1}],
        )
        invoice = order.invoices.get()
        lines = list(invoice.items.all())
        self.assertEqual(order.total, Decimal("23.59"))
        self.assertEqual(sum((line.line_total_inc_vat for line in lines), Decimal("0")), order.total)
        self.assertEqual(invoice.subtotal_ex_vat + invoice.vat_total, order.total)
        self.assertEqual(sum((line.discount_inc_vat for line in lines), Decimal("0")), Decimal("1.01"))
        self.assertEqual([row["rate"] for row in vat_summary(invoice)], [Decimal("9"), Decimal("21")])
        self.assertEqual(lines[-1].kind, "delivery")
        self.assertEqual(lines[-1].vat_rate, Decimal("9"))
        self.assertEqual(lines[-1].line_total_inc_vat, Decimal("2.50"))

    def test_full_discount_leaves_zero_merchandise_and_no_negative_vat(self):
        Coupon.objects.create(shop=self.shop, code="FREE", discount_type="fixed", discount_value=Decimal("999"))
        invoice = self.order(coupon_code="FREE").invoices.get()
        self.assertEqual(invoice.total_inc_vat, Decimal("0"))
        self.assertEqual(invoice.vat_total, Decimal("0"))

    def test_numbering_is_unique_even_with_matching_prefixes(self):
        first = self.order().invoices.get()
        second = self.order().invoices.get()
        settings = self.other_shop.settings
        settings.invoice_prefix = "RK"
        settings.save()
        third = self.order(shop=self.other_shop, product=self.other_product).invoices.get()
        self.assertEqual(len({first.invoice_number, second.invoice_number, third.invoice_number}), 3)
        self.assertTrue(first.invoice_number.endswith("-000001"))
        self.assertTrue(second.invoice_number.endswith("-000002"))
        self.assertTrue(third.invoice_number.endswith("-000001"))

    def test_generation_and_email_retry_are_idempotent(self):
        order = self.order()
        invoice = create_invoice(order)
        for _ in range(2):
            self.assertEqual(create_invoice(order).pk, invoice.pk)
            send_buyer_confirmation_email(order)
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(InvoiceSequence.objects.get(shop=self.shop).last_number, 1)
        self.assertEqual(InvoicePDF.objects.count(), 1)
        self.assertEqual(mail.outbox[0].attachments, mail.outbox[1].attachments)
        self.assertEqual(mail.outbox[0].attachments[0][2], "application/pdf")
        self.assertEqual(order.email_logs.filter(status="sent").count(), 2)

    def test_pdf_failure_is_logged_and_retry_reuses_invoice(self):
        order = self.order()
        invoice = order.invoices.get()
        with patch("apps.marketplace.billing.pdf_service.invoice_pdf", side_effect=RuntimeError("PDF unavailable")):
            with self.assertRaisesRegex(RuntimeError, "PDF unavailable"):
                send_buyer_confirmation_email(order)
        self.assertEqual(order.email_logs.get().status, "failed")
        send_buyer_confirmation_email(order)
        self.assertEqual(order.invoices.get().pk, invoice.pk)
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_snapshots_and_stored_pdf_do_not_change_with_catalogue_or_seller(self):
        order = self.order(user=self.buyer)
        invoice = order.invoices.get()
        original = invoice_pdf(invoice)
        self.product.price = Decimal("999")
        self.product.name = "Changed Product"
        self.product.save()
        settings = self.shop.settings
        settings.legal_business_name = "Changed Seller"
        settings.default_vat_rate = Decimal("21")
        settings.vat_number = "CHANGED"
        settings.save()
        self.buyer.email = "changed@example.com"
        self.buyer.save()
        invoice.refresh_from_db()
        self.assertEqual(invoice_pdf(invoice), original)
        html = invoice_html(invoice)
        self.assertIn("Product One", html)
        self.assertIn("Billing Shop", html)
        self.assertIn("buyer@example.com", html)
        self.assertNotIn("Changed", html)

    def test_snapshot_is_used_even_if_pdf_is_rendered_later(self):
        invoice = self.order().invoices.get()
        self.shop.settings.legal_business_name = "Later Seller"
        self.shop.settings.save()
        self.assertIn("Billing Shop", PdfReader(BytesIO(invoice_pdf(invoice))).pages[0].extract_text())

    def test_issued_documents_cannot_be_updated_deleted_or_cascaded(self):
        invoice = self.order().invoices.get()
        invoice.total_inc_vat = Decimal("1")
        with self.assertRaises(ValidationError):
            invoice.save()
        for queryset in (Invoice.objects.all(), InvoiceItem.objects.all()):
            with self.assertRaises(ValidationError):
                queryset.update()
            with self.assertRaises(ValidationError):
                queryset.delete()
        with self.assertRaises(ValidationError):
            invoice.items.get().delete()
        with self.assertRaises(ProtectedError):
            invoice.order.delete()

    def test_online_unpaid_has_no_invoice_and_paid_can_be_confirmed(self):
        order = self.order(payment_method="online")
        self.assertFalse(order.invoices.exists())
        with self.assertRaisesRegex(ValueError, "successful payment"):
            create_invoice(order)
        order.payment_status = "paid"
        order.save()
        send_buyer_confirmation_email(order)
        self.assertEqual(order.invoices.count(), 1)
        self.assertEqual(len(mail.outbox[-1].attachments), 1)

    def test_invalid_cart_rolls_back_without_invoice_or_number(self):
        with self.assertRaises(DRFValidationError):
            self.order(items=[{"product_id": self.other_product.pk, "quantity": 1}])
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Invoice.objects.exists())
        self.assertFalse(InvoiceSequence.objects.exists())

    def test_cancelled_and_inconsistent_orders_are_not_invoiced(self):
        order = self.order(payment_method="online")
        order.payment_status = "paid"
        order.status = "cancelled"
        order.save()
        with self.assertRaisesRegex(ValueError, "cancelled"):
            create_invoice(order)
        order.status = "pending"
        order.total = Decimal("99")
        order.save()
        with self.assertRaisesRegex(ValueError, "reconcile"):
            create_invoice(order)

    def test_owning_customer_seller_and_admin_can_download(self):
        order = self.order(user=self.buyer)
        invoice = order.invoices.get()
        for user in (self.buyer, self.seller, self.admin):
            self.client.force_authenticate(user)
            response = self.client.get(f"/api/marketplace/invoices/{invoice.pk}/pdf/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertEqual(response["Cache-Control"], "private, no-store")
            self.assertIn(invoice.invoice_number, response["Content-Disposition"])
            self.assertTrue(response.content.startswith(b"%PDF"))
            text = "".join(page.extract_text() for page in PdfReader(BytesIO(response.content)).pages)
            self.assertIn(invoice.invoice_number, text)
            self.assertIn(order.order_number, text)
            self.assertIn("1111111111", text)
            self.assertIn("ABNAXXXXXXXXX", text)
            self.assertNotIn("KVK:", text)
            listing = self.client.get(f"/api/marketplace/orders/{order.pk}/invoices/")
            self.assertEqual(listing.status_code, 200)
            self.assertEqual(listing.data[0]["invoice_number"], invoice.invoice_number)

    def test_other_customer_seller_and_guest_cannot_access_invoice(self):
        order = self.order(user=self.buyer)
        invoice = order.invoices.get()
        for user in (self.other_buyer, self.other_seller):
            self.client.force_authenticate(user)
            for path in (
                f"/api/marketplace/invoices/{invoice.pk}/",
                f"/api/marketplace/invoices/{invoice.pk}/pdf/",
                f"/api/marketplace/orders/{order.pk}/invoices/",
            ):
                self.assertEqual(self.client.get(path).status_code, 404)
            self.assertEqual(self.client.get("/api/marketplace/invoices/").data, [])
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(f"/api/marketplace/invoices/{invoice.pk}/pdf/").status_code, (401, 403))

    def test_inactive_seller_cannot_download(self):
        invoice = self.order().invoices.get()
        self.seller.seller_profile.is_active = False
        self.seller.seller_profile.save()
        self.client.force_authenticate(self.seller)
        self.assertEqual(self.client.get(f"/api/marketplace/invoices/{invoice.pk}/pdf/").status_code, 404)

    def test_seller_permissions_follow_invoice_shop_even_if_order_is_reassigned(self):
        order = self.order(user=self.buyer)
        invoice = order.invoices.get()
        order.shop = self.other_shop
        order.save()
        self.client.force_authenticate(self.other_seller)
        self.assertEqual(self.client.get(f"/api/marketplace/invoices/{invoice.pk}/pdf/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/marketplace/orders/{order.pk}/invoices/").data, [])
        self.client.force_authenticate(self.seller)
        self.assertEqual(self.client.get(f"/api/marketplace/invoices/{invoice.pk}/").status_code, 200)
        self.assertEqual(len(self.client.get(f"/api/marketplace/orders/{order.pk}/invoices/").data), 1)

    def test_guest_invoice_access_follows_existing_order_linking(self):
        order = self.order()
        invoice = order.invoices.get()
        self.assertIsNone(invoice.customer)
        link_guest_orders_to_user(self.buyer)
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.get(f"/api/marketplace/invoices/{invoice.pk}/").status_code, 200)

    def test_kvk_only_rendered_when_present(self):
        html = invoice_html(self.order().invoices.get())
        self.assertNotIn("KVK:", html)
        self.shop.settings.kvk_number = "12345678"
        self.shop.settings.save()
        self.assertIn("KVK: 12345678", invoice_html(self.order().invoices.get()))

    def test_seller_settings_are_scoped_and_validated(self):
        self.client.force_authenticate(self.seller)
        response = self.client.patch(
            "/api/seller/settings/",
            {
                "legal_business_name": "Legal Name",
                "default_vat_rate": "21.00",
                "invoice_prefix": "BILL",
                "kvk_number": "",
                "vat_number": "NL123",
                "invoice_iban": "abna xxxxxxxx",
                "billing_address_line1": "Street 7",
                "billing_city": "Town",
                "billing_country": "NL",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.shop.settings.refresh_from_db()
        self.other_shop.settings.refresh_from_db()
        self.assertEqual(self.shop.settings.legal_business_name, "Legal Name")
        self.assertEqual(self.other_shop.settings.legal_business_name, "Other Shop")
        for data in ({"default_vat_rate": "-1"}, {"default_vat_rate": "100.01"}, {"invoice_prefix": "../../bad"}):
            self.assertEqual(self.client.patch("/api/seller/settings/", data, format="json").status_code, 400)
        self.client.force_authenticate(self.buyer)
        self.assertEqual(
            self.client.patch("/api/seller/settings/", {"vat_number": "hijack"}, format="json").status_code, 403
        )

    def test_billing_settings_are_not_leaked_on_public_shop_api(self):
        response = self.client.get(f"/api/marketplace/shops/{self.shop.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("invoice_iban", response.data["settings"])
        self.assertNotIn("vat_number", response.data["settings"])

    def test_product_rate_is_editable_and_blank_uses_shop_default(self):
        self.client.force_authenticate(self.seller)
        path = f"/api/seller/products/{self.product.pk}/"
        response = self.client.patch(path, {"vat_rate": "5.50"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.order().invoices.get().items.get().vat_rate, Decimal("5.50"))
        response = self.client.patch(path, {"vat_rate": ""}, format="multipart")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.order().invoices.get().items.get().vat_rate, Decimal("9"))

    def test_arbitrary_logo_urls_are_not_fetched(self):
        self.shop.logo_url = "http://127.0.0.1/private"
        with patch("apps.marketplace.billing.pdf_service.requests.get") as get:
            self.assertEqual(snapshot_logo(self.shop), "")
            get.assert_not_called()

    def test_uploaded_logo_is_embedded_and_frozen(self):
        buffer = BytesIO()
        Image.new("RGB", (20, 20), "green").save(buffer, format="PNG")
        self.shop.logo_url = "https://res.cloudinary.com/example/image/upload/logo.png"
        self.shop.save()
        with patch("apps.marketplace.billing.pdf_service.requests.get") as get:
            response = get.return_value.__enter__.return_value
            response.status_code = 200
            response.iter_content.return_value = [buffer.getvalue()]
            invoice = self.order().invoices.get()
            self.assertTrue(invoice.seller_snapshot["logo"].startswith("data:image/png;base64,"))
            get.assert_called_once_with(self.shop.logo_url, timeout=(3, 5), allow_redirects=False, stream=True)
        self.shop.logo_url = ""
        self.shop.save()
        self.assertIn('class="logo"', invoice_html(invoice))
        pdf = PdfReader(BytesIO(invoice_pdf(invoice)))
        self.assertEqual(len(pdf.pages[0].images), 1)

    def test_billing_seed_preserves_real_settings(self):
        self.shop.name = "Rishi Kitchen"
        self.shop.save()
        settings = self.shop.settings
        settings.vat_number = "REALVAT"
        settings.invoice_iban = "REALIBAN"
        settings.kvk_number = "12345678"
        settings.save()
        migration = import_module("apps.marketplace.migrations.0015_seed_seller_billing_details")
        migration.seed_billing(apps, SimpleNamespace(connection=connection))
        settings.refresh_from_db()
        self.assertEqual(settings.vat_number, "REALVAT")
        self.assertEqual(settings.invoice_iban, "REALIBAN")
        self.assertEqual(settings.kvk_number, "12345678")

    def test_sequence_rolls_back_with_order(self):
        with self.assertRaisesRegex(RuntimeError, "rollback"):
            with transaction.atomic():
                self.order()
                raise RuntimeError("rollback")
        self.assertFalse(Invoice.objects.exists())
        self.assertTrue(self.order().invoices.get().invoice_number.endswith("-000001"))


class ConcurrentNumberingTests(TransactionTestCase):
    def test_numbering_on_database_with_row_locking(self):
        if not connection.features.has_select_for_update:
            self.skipTest(
                "Real row-lock concurrency requires PostgreSQL; SQLite is covered by uniqueness and checkout retry."
            )
        _, _, shop = create_seller_with_shop(
            email="concurrent@example.com",
            password="test",
            first_name="Seller",
            last_name="One",
            business_name="Concurrent Shop",
        )
        orders = []
        for index in range(4):
            order = Order.objects.create(
                shop=shop,
                order_number=f"CONCURRENT-{index}",
                customer_name="Buyer",
                customer_phone="123",
                subtotal=Decimal("10"),
                total=Decimal("10"),
            )
            OrderItem.objects.create(
                order=order, product_name="Snapshot", unit_price=Decimal("10"), quantity=1, line_total=Decimal("10")
            )
            orders.append(order.pk)

        def issue(pk):
            close_old_connections()
            try:
                return create_invoice(Order.objects.get(pk=pk)).invoice_number
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=4) as pool:
            numbers = list(pool.map(issue, orders))
        self.assertEqual(len(set(numbers)), 4)
        self.assertEqual(InvoiceSequence.objects.get(shop=shop).last_number, 4)
        with ThreadPoolExecutor(max_workers=4) as pool:
            repeated = list(pool.map(issue, [orders[0]] * 4))
        self.assertEqual(len(set(repeated)), 1)
        self.assertEqual(Invoice.objects.count(), 4)
