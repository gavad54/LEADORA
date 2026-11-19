"""Isolated test applications for legacy finance modules.

These routers are mounted only in tests to preserve regression coverage of
historical source and data contracts. They are not mounted by app.main.
"""
from fastapi import FastAPI

from app.main import app as main_app, db, user_from_header, ROOT
from app.participation import create_router as create_legacy_finance_router
from app.accounting import install_accounting


def create_legacy_finance_app():
    test_app = FastAPI()
    test_app.include_router(create_legacy_finance_router(db, user_from_header))
    return test_app


def create_legacy_accounting_app():
    test_app = FastAPI()
    install_accounting(test_app, db, user_from_header, ROOT)
    return test_app
