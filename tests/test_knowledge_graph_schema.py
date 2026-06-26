from __future__ import annotations

from pathlib import Path


MIGRATION = Path("db/migrations/008_knowledge_graph.sql")


def test_kg_migration_creates_schema_and_main_tables() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE SCHEMA IF NOT EXISTS kg" in sql
    for table in ("entity_types", "relation_types", "entities", "relations", "evidence"):
        assert f"CREATE TABLE IF NOT EXISTS kg.{table}" in sql


def test_kg_migration_seeds_entity_and_relation_vocabularies() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    for entity_type in ("project", "contract", "document", "section", "payment_item"):
        assert f"('{entity_type}'" in sql
    for relation_type in ("HAS_CONTRACT", "HAS_DOCUMENT", "SUPPORTED_BY"):
        assert f"('{relation_type}'" in sql


def test_kg_migration_requires_evidence_target() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "CHECK (entity_id IS NOT NULL OR relation_id IS NOT NULL)" in sql
    assert "source_file_id uuid NULL" in sql
    assert "section_id uuid NULL" in sql
    assert "clause_id uuid NULL" in sql
