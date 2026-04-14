from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from jera_fx_api.db.models import Observation, SourceFile
from jera_fx_connectors.manual_cds_file import (
    ingest_manual_cds_file,
    normalize_manual_cds_payload,
    read_manual_cds_csv,
    validate_manual_cds_file,
)
from tests.conftest import write_sample_cds_csv


REAL_CDS_FILE_PATH = Path("data/raw/cds/BRGV5YUSAC=R_2026-04-07.csv")


def test_manual_cds_csv_reader_and_normalizer(tmp_path) -> None:
    file_path = write_sample_cds_csv(tmp_path / "BRGV5YUSAC=R_manual_batch.csv")
    records, field_names = read_manual_cds_csv(file_path)
    normalized = normalize_manual_cds_payload(records, canonical_value_field="Price")

    assert field_names == ["Date", "Price", "Open", "High", "Low", "Change %"]
    assert len(normalized) == 3
    assert normalized[0]["observation_date"].isoformat() == "2026-04-01"
    assert normalized[0]["reference_month_end"].isoformat() == "2026-04-30"
    assert normalized[0]["value_numeric"] == 101.25
    assert normalized[0]["change_percent"] == 0.45


def test_manual_cds_ingest_stores_source_file_metadata_and_raw_observations(session, catalog, tmp_path) -> None:
    file_path = write_sample_cds_csv(tmp_path / "BRGV5YUSAC=R_manual_batch.csv")

    payload = ingest_manual_cds_file(session, catalog, file_path=file_path)

    source_file = session.execute(select(SourceFile)).scalars().one()
    observations = session.execute(
        select(Observation).where(Observation.series_key == "cds_brazil_5y").order_by(Observation.observation_date.asc())
    ).scalars().all()

    assert payload["row_count"] == 3
    assert payload["file_path"].endswith("BRGV5YUSAC=R_manual_batch.csv")
    assert len(payload["checksum_sha256"]) == 64
    assert source_file.source_key == "approved_internal_cds_file_drop"
    assert source_file.metadata_json["source_mode"] == "approved_internal_file_drop"
    assert source_file.metadata_json["automation_mode"] == "manual_batch"
    assert source_file.metadata_json["source_symbol"] == "BRGV5YUSAC=R"
    assert source_file.metadata_json["canonical_value_field"] == "Price"
    assert observations[-1].observation_date.isoformat() == "2026-04-03"
    assert observations[-1].reference_month_end.isoformat() == "2026-04-30"
    assert observations[-1].value_numeric == 100.95
    assert observations[-1].released_at is None
    assert observations[-1].attributes_json["raw_row"]["Price"] == "100.95"
    assert observations[-1].attributes_json["source_mode"] == "approved_internal_file_drop"
    assert observations[-1].attributes_json["automation_mode"] == "manual_batch"


def test_manual_cds_ingest_is_idempotent(session, catalog, tmp_path) -> None:
    file_path = write_sample_cds_csv(tmp_path / "BRGV5YUSAC=R_manual_batch.csv")

    ingest_manual_cds_file(session, catalog, file_path=file_path)
    ingest_manual_cds_file(session, catalog, file_path=file_path)

    source_file_count = session.execute(select(func.count()).select_from(SourceFile)).scalar_one()
    observation_count = session.execute(
        select(func.count()).select_from(Observation).where(Observation.series_key == "cds_brazil_5y")
    ).scalar_one()

    assert source_file_count == 1
    assert observation_count == 3


def test_validate_manual_cds_file_reports_ok_for_valid_fixture(catalog, tmp_path) -> None:
    file_path = write_sample_cds_csv(tmp_path / "BRGV5YUSAC=R_2026-04-03.csv")

    report = validate_manual_cds_file(catalog, file_path=file_path)

    assert report["file_exists"] is True
    assert report["columns_ok"] is True
    assert report["missing_columns"] == []
    assert report["naming_convention_ok"] is True
    assert report["row_count"] == 3
    assert report["observation_date_range"] == {
        "min": "2026-04-01",
        "max": "2026-04-03",
    }
    assert report["errors"] == []
    assert len(report["checksum_sha256"]) == 64


def test_validate_manual_cds_file_flags_missing_columns(catalog, tmp_path) -> None:
    bad_path = tmp_path / "BRGV5YUSAC=R_bad.csv"
    bad_path.write_text("Date,Price\n2026-04-01,101.25\n", encoding="utf-8")

    report = validate_manual_cds_file(catalog, file_path=bad_path)

    assert report["columns_ok"] is False
    assert set(report["missing_columns"]) == {"Open", "High", "Low", "Change %"}
    assert report["errors"], "expected blocking error for missing columns"


def test_validate_manual_cds_file_warns_on_bad_filename(catalog, tmp_path) -> None:
    file_path = write_sample_cds_csv(tmp_path / "not_conventional.csv")

    report = validate_manual_cds_file(catalog, file_path=file_path)

    assert report["naming_convention_ok"] is False
    assert report["naming_convention_warnings"], "expected a warning for non-conforming filename"
    # Naming issues are warnings, not errors
    assert report["errors"] == []


def test_validate_manual_cds_file_detects_already_ingested(session, catalog, tmp_path) -> None:
    file_path = write_sample_cds_csv(tmp_path / "BRGV5YUSAC=R_2026-04-03.csv")
    ingest_manual_cds_file(session, catalog, file_path=file_path)

    report = validate_manual_cds_file(catalog, file_path=file_path, session=session)

    assert report["already_ingested"] is True
    assert "existing_source_file_key" in report


def test_manual_cds_ingest_persists_operator_and_source_note(session, catalog, tmp_path) -> None:
    file_path = write_sample_cds_csv(tmp_path / "BRGV5YUSAC=R_2026-04-03.csv")

    ingest_manual_cds_file(
        session,
        catalog,
        file_path=file_path,
        operator="fnobre@jera.capital",
        source_note="Test export 2026-04-03",
    )

    source_file = session.execute(select(SourceFile)).scalars().one()
    assert source_file.metadata_json["operator"] == "fnobre@jera.capital"
    assert source_file.metadata_json["source_note"] == "Test export 2026-04-03"
    assert source_file.metadata_json["filename_convention_ok"] is True
    assert source_file.metadata_json["filename_file_date"] == "2026-04-03"


@pytest.mark.skipif(
    not REAL_CDS_FILE_PATH.exists(),
    reason="Real CDS fixture file not present in checkout",
)
def test_validate_real_cds_fixture_file(catalog) -> None:
    """Regression test: the committed real fixture must always validate clean.

    If this test fails, someone changed the real file on disk without
    updating expectations. Review `docs/runbooks/manual-cds-ingestion.md`
    before modifying the fixture.
    """
    report = validate_manual_cds_file(catalog, file_path=REAL_CDS_FILE_PATH)

    assert report["file_exists"] is True
    assert report["columns_ok"] is True
    assert report["missing_columns"] == []
    assert report["naming_convention_ok"] is True
    assert report["filename_symbol"] == "BRGV5YUSAC=R"
    assert report["filename_file_date"] == "2026-04-07"
    assert report["row_count"] > 1000  # sanity: multi-year history
    assert report["observation_date_range"] is not None
    assert report["errors"] == []
