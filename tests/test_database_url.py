"""Database URL sources: a full URL (Vercel, Supabase) or the RDS secret JSON (AWS)."""

import json
import secrets

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.database_url import DatabaseSecretError, database_url_from_env, url_from_rds_secret

RDS_SECRET = {
    "engine": "postgres",
    "username": "neurophobia",
    "password": "p@ss/word:with#reserved",
    "host": "db.example.internal",
    "port": 5432,
    "dbname": "neurophobia",
}


def test_rds_secret_becomes_a_tls_url_with_an_encoded_password():
    url = url_from_rds_secret(json.dumps(RDS_SECRET))
    assert url == (
        "postgresql+psycopg://neurophobia:p%40ss%2Fword%3Awith%23reserved"
        "@db.example.internal:5432/neurophobia?sslmode=require"
    )


def test_rds_secret_defaults_port_and_database():
    minimal = {key: RDS_SECRET[key] for key in ("username", "password", "host")}
    assert url_from_rds_secret(json.dumps(minimal)).endswith("@db.example.internal:5432/postgres?sslmode=require")


@pytest.mark.parametrize("bad", ["not json", "[]", json.dumps({"username": "u", "host": "h"})])
def test_malformed_rds_secret_is_rejected(bad):
    with pytest.raises(DatabaseSecretError):
        url_from_rds_secret(bad)


def test_full_url_wins_over_the_secret():
    environ = {"NP_DATABASE_URL": "postgresql+psycopg://a:b@c/d", "NP_DATABASE_SECRET": json.dumps(RDS_SECRET)}
    assert database_url_from_env(environ) == "postgresql+psycopg://a:b@c/d"
    assert database_url_from_env({"NP_DATABASE_SECRET": json.dumps(RDS_SECRET)}).startswith("postgresql+psycopg://")
    assert database_url_from_env({}) is None


def test_settings_accept_the_rds_secret(monkeypatch):
    monkeypatch.delenv("NP_DATABASE_URL", raising=False)
    monkeypatch.setenv("NP_DATABASE_SECRET", json.dumps(RDS_SECRET))
    monkeypatch.setenv("NP_SECRET_KEY", secrets.token_urlsafe(40))
    settings = Settings()  # type: ignore[call-arg]
    assert settings.database_url.get_secret_value() == url_from_rds_secret(json.dumps(RDS_SECRET))


def test_settings_still_require_a_database(monkeypatch):
    monkeypatch.delenv("NP_DATABASE_URL", raising=False)
    monkeypatch.delenv("NP_DATABASE_SECRET", raising=False)
    monkeypatch.setenv("NP_SECRET_KEY", secrets.token_urlsafe(40))
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]
