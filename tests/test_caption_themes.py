from creatoriq_dashboard.caption_themes import classify_caption


def test_fall_refresh():
    f = classify_caption("My fall refresh with @wayfair #wayfaircreator #wayfairelevate")
    assert f.fall_or_fall_refresh
    assert not f.halloween


def test_halloween():
    f = classify_caption("Spooky season decor for Halloween 🎃")
    assert f.halloween


def test_pre_holiday():
    f = classify_caption("Getting holiday ready for Thanksgiving hosting")
    assert f.pre_holiday


def test_category_sideboard_and_verified():
    f = classify_caption("New sideboard from Wayfair Verified program")
    assert f.category_sideboard
    assert f.category_wayfair_verified
    assert f.category_specific


def test_single_product_not_haul():
    f = classify_caption("I love this arched cabinet from Wayfair — one piece that changed the room.")
    assert f.single_product_highlight


def test_multi_product_not_single():
    f = classify_caption("Shop my room — these finds are all linked in bio")
    assert not f.single_product_highlight
