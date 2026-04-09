"""Initial meta, raw, and curated foundation schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_meta_raw_curated"
down_revision = None
branch_labels = None
depends_on = None


def _create_schema(schema_name: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))


def upgrade() -> None:
    for schema_name in ("meta", "raw", "curated"):
        _create_schema(schema_name)

    op.create_table(
        "sources",
        sa.Column("source_key", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=255), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("official", sa.Boolean(), nullable=False),
        sa.Column("release_metadata_behavior", sa.String(length=255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("connection", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source_key", name="pk_sources"),
        schema="meta",
    )

    op.create_table(
        "series_definitions",
        sa.Column("series_key", sa.String(length=120), nullable=False),
        sa.Column("source_key", sa.String(length=100), nullable=False),
        sa.Column("source_code", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=255), nullable=False),
        sa.Column("frequency", sa.String(length=32), nullable=False),
        sa.Column("units", sa.String(length=64), nullable=False),
        sa.Column("release_metadata_behavior", sa.String(length=255), nullable=False),
        sa.Column("transformation_rules", sa.JSON(), nullable=False),
        sa.Column("display_metadata", sa.JSON(), nullable=False),
        sa.Column("canonical_scale_policy", sa.JSON(), nullable=False),
        sa.Column("is_placeholder", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("series_key", name="pk_series_definitions"),
        sa.UniqueConstraint("source_key", "source_code", name="uq_series_definitions_source_code"),
        schema="meta",
    )
    op.create_index(
        "ix_series_definitions_source_key",
        "series_definitions",
        ["source_key"],
        unique=False,
        schema="meta",
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("ingestion_run_key", sa.String(length=160), nullable=False),
        sa.Column("source_key", sa.String(length=100), nullable=False),
        sa.Column("job_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("parameters_json", sa.JSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("ingestion_run_key", name="pk_ingestion_runs"),
        sa.UniqueConstraint("idempotency_key", name="uq_ingestion_runs_idempotency_key"),
        schema="meta",
    )
    op.create_index(
        "ix_ingestion_runs_source_key",
        "ingestion_runs",
        ["source_key"],
        unique=False,
        schema="meta",
    )

    op.create_table(
        "source_files",
        sa.Column("source_file_key", sa.String(length=160), nullable=False),
        sa.Column("source_key", sa.String(length=100), nullable=False),
        sa.Column("ingestion_run_key", sa.String(length=160), nullable=False),
        sa.Column("logical_name", sa.String(length=255), nullable=False),
        sa.Column("original_path", sa.Text(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("update_header", sa.String(length=255), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("source_file_key", name="pk_source_files"),
        sa.UniqueConstraint("source_key", "checksum_sha256", name="uq_source_files_source_checksum"),
        schema="raw",
    )
    op.create_index("ix_source_files_source_key", "source_files", ["source_key"], unique=False, schema="raw")
    op.create_index(
        "ix_source_files_ingestion_run_key",
        "source_files",
        ["ingestion_run_key"],
        unique=False,
        schema="raw",
    )

    op.create_table(
        "observations",
        sa.Column("observation_key", sa.String(length=200), nullable=False),
        sa.Column("source_key", sa.String(length=100), nullable=False),
        sa.Column("series_key", sa.String(length=120), nullable=False),
        sa.Column("ingestion_run_key", sa.String(length=160), nullable=False),
        sa.Column("source_file_key", sa.String(length=160), nullable=True),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("reference_month_end", sa.Date(), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vintage_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value_numeric", sa.Float(), nullable=False),
        sa.Column("units", sa.String(length=64), nullable=False),
        sa.Column("scale_policy", sa.String(length=64), nullable=False),
        sa.Column("attributes_json", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("observation_key", name="pk_observations"),
        sa.UniqueConstraint(
            "series_key",
            "observation_date",
            "scale_policy",
            name="uq_observations_series_date_scale",
        ),
        schema="raw",
    )
    op.create_index("ix_observations_source_key", "observations", ["source_key"], unique=False, schema="raw")
    op.create_index("ix_observations_series_key", "observations", ["series_key"], unique=False, schema="raw")
    op.create_index(
        "ix_observations_ingestion_run_key",
        "observations",
        ["ingestion_run_key"],
        unique=False,
        schema="raw",
    )
    op.create_index(
        "ix_observations_source_file_key",
        "observations",
        ["source_file_key"],
        unique=False,
        schema="raw",
    )
    op.create_index(
        "ix_observations_reference_month_end",
        "observations",
        ["reference_month_end"],
        unique=False,
        schema="raw",
    )

    op.create_table(
        "feature_sets",
        sa.Column("feature_set_key", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("definition_hash", sa.String(length=64), nullable=False),
        sa.Column("scale_policy", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("feature_set_key", name="pk_feature_sets"),
        schema="curated",
    )

    op.create_table(
        "feature_values",
        sa.Column("feature_value_key", sa.String(length=220), nullable=False),
        sa.Column("feature_set_key", sa.String(length=160), nullable=False),
        sa.Column("series_key", sa.String(length=120), nullable=False),
        sa.Column("feature_name", sa.String(length=120), nullable=False),
        sa.Column("reference_month_end", sa.Date(), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=True),
        sa.Column("value_numeric", sa.Float(), nullable=False),
        sa.Column("units", sa.String(length=64), nullable=False),
        sa.Column("scale_policy", sa.String(length=64), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("feature_value_key", name="pk_feature_values"),
        sa.UniqueConstraint(
            "feature_set_key",
            "feature_name",
            "series_key",
            "reference_month_end",
            name="uq_feature_values_set_feature_series_month",
        ),
        schema="curated",
    )
    op.create_index(
        "ix_feature_values_feature_set_key",
        "feature_values",
        ["feature_set_key"],
        unique=False,
        schema="curated",
    )
    op.create_index(
        "ix_feature_values_series_key",
        "feature_values",
        ["series_key"],
        unique=False,
        schema="curated",
    )
    op.create_index(
        "ix_feature_values_reference_month_end",
        "feature_values",
        ["reference_month_end"],
        unique=False,
        schema="curated",
    )

    op.create_table(
        "client_snapshots",
        sa.Column("snapshot_key", sa.String(length=180), nullable=False),
        sa.Column("snapshot_type", sa.String(length=64), nullable=False),
        sa.Column("reference_month_end", sa.Date(), nullable=False),
        sa.Column("feature_set_key", sa.String(length=160), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("snapshot_key", name="pk_client_snapshots"),
        sa.UniqueConstraint("snapshot_type", "reference_month_end", name="uq_client_snapshots_type_month"),
        schema="curated",
    )
    op.create_index(
        "ix_client_snapshots_snapshot_type",
        "client_snapshots",
        ["snapshot_type"],
        unique=False,
        schema="curated",
    )
    op.create_index(
        "ix_client_snapshots_reference_month_end",
        "client_snapshots",
        ["reference_month_end"],
        unique=False,
        schema="curated",
    )


def downgrade() -> None:
    op.drop_index("ix_client_snapshots_reference_month_end", table_name="client_snapshots", schema="curated")
    op.drop_index("ix_client_snapshots_snapshot_type", table_name="client_snapshots", schema="curated")
    op.drop_table("client_snapshots", schema="curated")

    op.drop_index("ix_feature_values_reference_month_end", table_name="feature_values", schema="curated")
    op.drop_index("ix_feature_values_series_key", table_name="feature_values", schema="curated")
    op.drop_index("ix_feature_values_feature_set_key", table_name="feature_values", schema="curated")
    op.drop_table("feature_values", schema="curated")
    op.drop_table("feature_sets", schema="curated")

    op.drop_index("ix_observations_reference_month_end", table_name="observations", schema="raw")
    op.drop_index("ix_observations_source_file_key", table_name="observations", schema="raw")
    op.drop_index("ix_observations_ingestion_run_key", table_name="observations", schema="raw")
    op.drop_index("ix_observations_series_key", table_name="observations", schema="raw")
    op.drop_index("ix_observations_source_key", table_name="observations", schema="raw")
    op.drop_table("observations", schema="raw")

    op.drop_index("ix_source_files_ingestion_run_key", table_name="source_files", schema="raw")
    op.drop_index("ix_source_files_source_key", table_name="source_files", schema="raw")
    op.drop_table("source_files", schema="raw")

    op.drop_index("ix_ingestion_runs_source_key", table_name="ingestion_runs", schema="meta")
    op.drop_table("ingestion_runs", schema="meta")

    op.drop_index("ix_series_definitions_source_key", table_name="series_definitions", schema="meta")
    op.drop_table("series_definitions", schema="meta")
    op.drop_table("sources", schema="meta")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("DROP SCHEMA IF EXISTS curated CASCADE"))
        op.execute(sa.text("DROP SCHEMA IF EXISTS raw CASCADE"))
        op.execute(sa.text("DROP SCHEMA IF EXISTS meta CASCADE"))
