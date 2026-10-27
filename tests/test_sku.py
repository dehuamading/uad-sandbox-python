from shop.inventory import normalize_sku


def test_normalize_sku_strips_and_uppercases():
    assert normalize_sku("  ab-12 ") == "AB-12"
