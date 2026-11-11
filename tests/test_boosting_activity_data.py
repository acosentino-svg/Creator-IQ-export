from creatoriq_dashboard.boosting_activity_data import prepare_demo_boosting_raw


def test_demo_boosting_raw_has_creators_and_posts():
    raw = prepare_demo_boosting_raw()
    assert len(raw.creators) > 0
    assert "WBP" in raw.creators["tags"].astype(str).str.cat()
    assert len(raw.posts) > 0
    assert (raw.posts["campaign_id"].astype(str) == "2206666").any()
