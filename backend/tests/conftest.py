import os

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["PUBLIC_URL"] = "http://testserver"
os.environ["APP_ENCRYPTION_KEY"] = "eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHg="
os.environ["BOT_SERVICE_TOKEN"] = "test-service-token-used-only-in-isolated-tests"

import pytest
from app.core.database import get_db
from app.main import app
from app.models.entities import Base, Plan
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def db():
    test_url = os.environ.get("TEST_DATABASE_URL", "sqlite://")
    engine = create_engine(
        test_url,
        **(
            {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
            if test_url.startswith("sqlite")
            else {}
        ),
    )

    if test_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, headers={"Origin": "http://testserver"}) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def plan(db):
    plan = Plan(
        code="month",
        name="Месяц",
        description="Тестовый тариф",
        price_minor=19900,
        currency="RUB",
        duration_days=30,
        device_limit=3,
        is_active=True,
    )
    db.add(plan)
    db.commit()
    return plan


@pytest.fixture
def account(client):
    credentials = {"email": "tester@example.com", "password": "a-long-secure-password"}
    response = client.post("/api/v1/auth/register", json=credentials)
    assert response.status_code == 201
    return credentials
