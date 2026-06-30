from pathlib import Path

from django.conf import settings
from django.contrib import admin
from django.core.management import get_commands
from django.test import SimpleTestCase

from apps.marketplace.admin import ProductAdmin
from apps.marketplace.models import Product


class MarketplaceDeploymentConfigTests(SimpleTestCase):
    def test_rishi_seed_is_manual_only(self):
        project_root = Path(settings.BASE_DIR)
        entrypoint = (project_root / "entrypoint.sh").read_text()
        render_config = (project_root / "render.yaml").read_text()

        self.assertNotIn("seed_rishi_kitchen", entrypoint)
        self.assertNotIn("seed_rishi_kitchen", render_config)
        self.assertIn("seed_rishi_kitchen", get_commands())

    def test_product_admin_is_shop_first(self):
        product_admin = ProductAdmin(Product, admin.site)

        self.assertEqual(product_admin.list_display[:2], ["shop", "name"])
        self.assertEqual(product_admin.ordering, ["shop__name", "name"])
        self.assertIn("shop__name", product_admin.search_fields)
