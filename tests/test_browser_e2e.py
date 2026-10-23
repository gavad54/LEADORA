"""Real-browser smoke tests for the primary company login and reload flow."""
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture(scope="module")
def live_app(tmp_path_factory):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    db_path = tmp_path_factory.mktemp("leadora-browser") / "browser-test.db"
    env = os.environ.copy()
    env["LEADORA_DB"] = str(db_path)
    env["LEADORA_SECRET"] = "browser-test-secret-that-is-long-enough-123456789"
    env["LEADORA_ENV"] = "test"
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 20
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError("LEADORA test server exited before becoming ready")
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=1) as response:
                if response.status == 200:
                    break
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)
    else:
        process.terminate()
        raise RuntimeError("LEADORA test server did not become ready")
    yield url
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def test_company_register_login_reload_and_logout_do_not_blank(live_app):
    browser_errors = []
    suffix = str(time.time_ns())
    company = "Browser Test " + suffix[-8:]
    email = "browser-" + suffix + "@example.com"
    password = "browser-test-password-2026"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda error: browser_errors.append(str(error)))
        page.goto(live_app, wait_until="networkidle")
        assert page.locator("#publicHome").is_visible()
        assert page.locator("#workspaceShell").is_hidden()
        assert page.locator("#authOverlay").is_hidden()
        assert page.get_by_text("کسب‌وکار خود را", exact=False).is_visible()

        # Refreshing as a visitor keeps the public landing visible without forcing authentication.
        page.reload(wait_until="networkidle")
        assert page.locator("#publicHome").is_visible()
        assert page.locator("#authOverlay").is_hidden()

        page.locator("#publicStartBtn").click()
        assert page.locator("#authOverlay").is_visible()
        page.locator('[data-auth-mode="register"]').click()
        page.locator("#company").fill(company)
        page.locator("#industry").fill("retail")
        page.locator("#email").fill(email)
        page.locator("#password").fill(password)
        page.locator("#authSubmit").click()

        page.wait_for_function("document.getElementById('authOverlay').hidden === true")
        assert page.locator("#workspaceShell").is_visible()
        assert page.locator("#publicHome").is_hidden()
        page.wait_for_function("document.getElementById('connectionState').textContent.includes('اطلاعات دریافت شد')")
        assert page.locator("#runtimeError").is_hidden()

        page.reload(wait_until="networkidle")
        page.wait_for_function("document.getElementById('authOverlay').hidden === true")
        page.wait_for_function("document.getElementById('connectionState').textContent.includes('اطلاعات دریافت شد')")
        assert page.locator("#runtimeError").is_hidden()

        page.locator('[data-view="settings"]:visible').click()
        page.locator("#densitySetting").select_option("compact")
        page.locator("#motionSetting").select_option("reduced")
        page.locator("#saveSettingsBtn").click()
        assert "compact" in page.locator("body").get_attribute("class")
        assert "reduce-motion" in page.locator("body").get_attribute("class")
        assert "leadora_preferences" in page.evaluate("Object.keys(localStorage).join(',')")
        page.reload(wait_until="networkidle")
        page.locator('[data-view="settings"]:visible').click()
        assert page.locator("#densitySetting").input_value() == "compact"
        assert page.locator("#motionSetting").input_value() == "reduced"
        page.locator("#logoutBtn").click()
        assert page.locator("#publicHome").is_visible()
        assert page.locator("#authOverlay").is_hidden()
        page.locator("#publicLoginBtn").click()
        assert page.locator("#authOverlay").is_visible()
        page.locator("#company").fill(company)
        page.locator("#email").fill(email)
        page.locator("#password").fill(password)
        page.locator("#authSubmit").click()
        page.wait_for_function("document.getElementById('authOverlay').hidden === true")
        page.wait_for_function("document.getElementById('connectionState').textContent.includes('اطلاعات دریافت شد')")

        # Mobile viewport smoke test: public landing stays visible and the auth dialog is opt-in.
        mobile = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        mobile_errors = []
        mobile.on("pageerror", lambda error: mobile_errors.append(str(error)))
        mobile.goto(live_app, wait_until="networkidle")
        assert mobile.locator("#publicHome").is_visible()
        assert mobile.locator("#authOverlay").is_hidden()
        assert mobile.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
        mobile.locator("#publicLoginBtn").click()
        assert mobile.locator("#authOverlay").is_visible()
        assert mobile_errors == [], "Mobile browser JavaScript errors: " + "; ".join(mobile_errors)

        assert browser_errors == [], "Browser JavaScript errors: " + "; ".join(browser_errors)
        browser.close()
