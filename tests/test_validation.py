from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_products_require_authentication():
    response = client.get('/api/products')
    assert response.status_code == 401

def test_customers_require_authentication():
    response = client.get('/api/customers')
    assert response.status_code == 401

def test_product_rejects_invalid_token():
    response = client.post('/api/products', headers={'Authorization': 'Bearer invalid'}, json={'sku':'x','name':'x','price':1,'stock':0})
    assert response.status_code == 401

def test_registration_requires_long_password():
    response = client.post('/api/register', json={'company_name':'Test Co','industry':'retail','email':'short-password@example.com','password':'short'})
    assert response.status_code == 422


def test_security_headers_are_set():
    response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"

def test_registration_rejects_invalid_email():
    response = client.post("/api/register", json={
        "company_name": "Invalid Email Test",
        "industry": "retail",
        "email": "not-an-email",
        "password": "secure-test-password",
    })
    assert response.status_code == 422

def test_login_handles_duplicate_company_and_email_across_tenants():
    import os
    suffix = str(os.getpid())
    common_email = "duplicate-" + suffix + "@example.com"
    for password in ("password-for-first-account", "password-for-second-account"):
        response = client.post("/api/register", json={
            "company_name": "Duplicate Company " + suffix,
            "industry": "retail",
            "email": common_email,
            "password": password,
        })
        assert response.status_code == 200, response.text
    response = client.post("/api/login", json={
        "company_name": "Duplicate Company " + suffix,
        "email": common_email,
        "password": "password-for-second-account",
    })
    assert response.status_code == 200, response.text
    assert response.json().get("token")



def test_login_throttles_repeated_failures():
    import os
    suffix = str(os.getpid())
    company = "Throttle Test " + suffix
    email = "throttle-" + suffix + "@example.com"
    registration = client.post("/api/register", json={
        "company_name": company,
        "industry": "retail",
        "email": email,
        "password": "correct-secure-password",
    })
    assert registration.status_code == 200, registration.text
    payload = {"company_name": company, "email": email, "password": "wrong-password"}
    for _ in range(5):
        response = client.post("/api/login", json=payload)
        assert response.status_code == 401, response.text
    blocked = client.post("/api/login", json=payload)
    assert blocked.status_code == 429
    assert "۱۵ دقیقه" in blocked.text


def test_blank_trimmed_product_and_customer_names_are_rejected():
    import os
    suffix = str(os.getpid())
    registration = client.post("/api/register", json={
        "company_name": "Blank Field Test " + suffix,
        "industry": "retail",
        "email": "blank-fields-" + suffix + "@example.com",
        "password": "correct-secure-password",
    })
    assert registration.status_code == 200, registration.text
    headers = {"Authorization": "Bearer " + registration.json()["token"]}
    product = client.post("/api/products", headers=headers, json={
        "sku": "   ", "name": "Valid name", "price": 0, "stock": 0,
    })
    customer = client.post("/api/customers", headers=headers, json={"name": "   ", "phone": ""})
    assert product.status_code == 422
    assert customer.status_code == 422
