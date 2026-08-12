"""Tests for geography CSV export (Looker Studio pipeline)."""
from pathlib import Path

import sys


def test_export_geography_table_from_demo_warehouse(tmp_path: Path):
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo / "src"))
    sys.path.insert(0, str(repo / "scripts"))

    from creatoriq_dashboard.demo_data import generate_demo_data
    from creatoriq_dashboard.storage import get_engine, write_table
    from export_geography_table import build_geography_table  # noqa: WPS433

    db_path = tmp_path / "warehouse.db"
    demo = generate_demo_data(n_creators=50)
    engine = get_engine(db_path)
    write_table(engine, "creators", demo.creators)

    table = build_geography_table(db_path, us_only_program=True)
    assert len(table) == 50
    assert "state_code" in table.columns
    assert "creator_id" in table.columns
