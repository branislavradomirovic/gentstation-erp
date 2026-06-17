from __future__ import annotations

import os
import uuid
from typing import Tuple

import psycopg2
from sqlalchemy.engine import make_url


def resolve_test_database_url() -> str:
    database_url = (
        os.getenv("TEST_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("SQLALCHEMY_DATABASE_URL")
    )
    if database_url:
        if database_url.startswith("postgres://"):
            return database_url.replace("postgres://", "postgresql://", 1)
        if database_url.startswith("postgresql+psycopg2://"):
            return database_url.replace("postgresql+psycopg2://", "postgresql://", 1)
        return database_url

    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "gentstation")
    user = os.getenv("DB_USER", "gentstation_user")
    password = os.getenv("DB_PASSWORD", "change_me_for_local_dev")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def build_schema_scoped_url(base_url: str, schema_name: str) -> str:
    url = make_url(base_url)
    query = dict(url.query)
    search_path_option = f"-csearch_path={schema_name},public"
    existing_options = str(query.get("options", "")).strip()
    query["options"] = (
        f"{existing_options} {search_path_option}".strip()
        if existing_options
        else search_path_option
    )
    return url.set(query=query).render_as_string(hide_password=False)


def create_isolated_schema(base_url: str, prefix: str = "pytest") -> Tuple[str, str]:
    schema_name = f"{prefix}_{uuid.uuid4().hex[:12]}"
    with psycopg2.connect(base_url) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{schema_name}"')
    return schema_name, build_schema_scoped_url(base_url, schema_name)


def drop_isolated_schema(base_url: str, schema_name: str) -> None:
    with psycopg2.connect(base_url) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
