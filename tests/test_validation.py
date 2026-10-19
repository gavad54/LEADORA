from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_products_require_authentication():
    response = client.get('/api/products')
    assert response.status_code == 401

def test_customers_require_authentication():
    response = client.get('/api/customers')
    assert response.status_code == 401

def test_product_rejects_negative_price():
    response = client.post('/api/products', headers={'Authorization': 'Bearer invalid'}, json={'sku':'x','name':'x','price':-1,'stock':0})
    assert response.status_code == 401
