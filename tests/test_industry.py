from app import industry


def test_verified_only(monkeypatch, tmp_path):
    path = tmp_path / "mappings.csv"
    path.write_text(
        "db25,db07,verified\n621000,620100,true\n642120,642020,false\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(industry, "MAPPING_FILE", path)
    assert industry.to_db07("621000") == "620100"
    assert industry.to_db07("642120") is None
    assert industry.to_db07("000000") is None


def test_duplicate_mapping_is_rejected(monkeypatch, tmp_path):
    path = tmp_path / "mappings.csv"
    path.write_text("db25,db07,verified\n212000,212000,true\n212000,212001,true\n", encoding="utf-8")
    monkeypatch.setattr(industry, "MAPPING_FILE", path)
    assert industry.to_db07("212000") is None
