import pytest

from src.routing.template_selector import select, whatsapp_enabled, TemplateNotConfigured
from src.config_loader import get_categories


def test_every_category_has_email_and_whatsapp_template():
    for category in get_categories():
        email_sel = select(category, "email")
        assert email_sel["subject"]
        assert email_sel["body_template_path"]

        whatsapp_sel = select(category, "whatsapp")
        assert whatsapp_sel["template_name"]


def test_unknown_category_raises():
    with pytest.raises(TemplateNotConfigured):
        select("not_a_real_category", "email")


def test_whatsapp_disabled_by_default_until_meta_approves():
    for category in get_categories():
        assert whatsapp_enabled(category) is False
