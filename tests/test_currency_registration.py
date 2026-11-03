import json
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.platform_admin.views import CURRENCY_MASTER_URL, _register_tenant_currency


class FakeResponse:
    def __init__(self, body, status=200):
        self._body = body
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_opener(existing_rows=b"[]"):
    """Stub urlopen: GET returns the registered rows, POST is recorded."""
    captured = []

    def opener(req, timeout=None):
        captured.append(req)
        if req.get_method() == "POST":
            return FakeResponse(b'{"id": 9}')
        return FakeResponse(existing_rows)

    return opener, captured


class CurrencyRegistrationTests(SimpleTestCase):
    """The central currency-master POST must match the documented payload."""

    def test_posts_documented_payload(self):
        opener, captured = fake_opener()
        with patch("apps.platform_admin.views.urlopen", opener):
            result = _register_tenant_currency("gW9q6nqq5onru", "inr")

        self.assertEqual(result["status"], "registered")
        posts = [req for req in captured if req.get_method() == "POST"]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].get_full_url(), CURRENCY_MASTER_URL)
        self.assertEqual(
            json.loads(posts[0].data),
            {
                "client_id": "GW9Q6NQQ5ONRU",
                "code": "INR",
                "name": "Indian Rupee",
                "status": "ACTIVE",
            },
        )

    def test_unknown_currency_uses_code_as_name(self):
        opener, captured = fake_opener()
        with patch("apps.platform_admin.views.urlopen", opener):
            result = _register_tenant_currency("GW9Q6NQQ5ONRU", "USD")

        self.assertEqual(result["status"], "registered")
        posts = [req for req in captured if req.get_method() == "POST"]
        self.assertEqual(json.loads(posts[0].data)["name"], "USD")

    def test_skips_when_already_registered(self):
        rows = (
            b'[{"id":1,"client_id":"GW9Q6NQQ5ONRU","code":"INR",'
            b'"name":"Indian Rupee","status":"ACTIVE"}]'
        )
        opener, captured = fake_opener(existing_rows=rows)
        with patch("apps.platform_admin.views.urlopen", opener):
            result = _register_tenant_currency("GW9Q6NQQ5ONRU", "INR")

        self.assertEqual(result["status"], "skipped")
        self.assertEqual([req for req in captured if req.get_method() == "POST"], [])

    def test_reports_failure_when_master_is_unreachable(self):
        def opener(req, timeout=None):
            raise OSError("network down")

        with patch("apps.platform_admin.views.urlopen", opener):
            result = _register_tenant_currency("GW9Q6NQQ5ONRU", "INR")

        self.assertEqual(result["status"], "failed")

    def test_skips_without_tenant_code(self):
        result = _register_tenant_currency("", "INR")
        self.assertEqual(result["status"], "skipped")
