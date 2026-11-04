"""Regression contract for the unauthenticated LEADORA landing page."""
from html.parser import HTMLParser
from pathlib import Path


INDEX = Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"


class _PageElements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        element_id = attrs.get("id")
        if element_id:
            self.elements[element_id] = {"tag": tag, "attrs": attrs, "hidden": "hidden" in attrs}


def test_public_home_is_the_initial_unauthenticated_document():
    html = INDEX.read_text(encoding="utf-8")
    page = _PageElements()
    page.feed(html)

    assert 'dir="rtl"' in html
    assert "publicHome" in page.elements
    assert not page.elements["publicHome"]["hidden"]
    assert "workspaceShell" in page.elements
    assert page.elements["workspaceShell"]["hidden"]
    assert "authOverlay" in page.elements
    assert page.elements["authOverlay"]["hidden"]
    assert "publicLoginBtn" in page.elements
    assert "publicStartBtn" in page.elements
    assert "ورود / ساخت حساب" in html


def test_startup_always_shows_public_home_before_restoring_saved_session():
    html = INDEX.read_text(encoding="utf-8")
    startup = html.rfind("/* Always render the public landing first.")
    assert startup >= 0
    startup_code = html[startup:]
    assert "showPublicHome();" in startup_code
    assert "refresh().then(restored=>" in startup_code
    assert startup_code.index("showPublicHome();") < startup_code.index("refresh().then(restored=>")
