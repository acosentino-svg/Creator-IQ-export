from creatoriq_dashboard.tiers import extract_tier_from_tags, PROGRAM_TIERS


def test_program_tiers():
    assert PROGRAM_TIERS == ("Curator", "Designer", "Trendsetter")


def test_extract_tier_from_tags():
    assert extract_tier_from_tags('"Curator","Favorite Brands|AllModern') == "Curator"
    assert extract_tier_from_tags("Designer, Home & Garden") == "Designer"
    assert extract_tier_from_tags("Trendsetter") == "Trendsetter"
    assert extract_tier_from_tags("Home & Garden") is None
