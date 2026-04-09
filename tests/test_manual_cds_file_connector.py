from __future__ import annotations

from sqlalchemy import func, select

from jera_fx_api.db.models import Observation, SourceFile
from jera_fx_connectors.manual_cds_file import (
    ingest_manual_cds_file,
    normalize_manual_cds_payload,
    read_manual_cds_csv,
)
from tests.conftest import write_sample_cds_csv


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
