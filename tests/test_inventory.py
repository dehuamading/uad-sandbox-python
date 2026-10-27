from shop.inventory import total_value, is_low_stock, with_tax, apply_coupon


def test_total_value_multiplies_qty():
    assert total_value([{"price": 100, "qty": 3}, {"price": 50, "qty": 2}]) == 400


def test_total_value_empty():
    assert total_value([]) == 0


def test_low_stock_boundary():
    assert is_low_stock(5) is True
    assert is_low_stock(6) is False


def test_with_tax_6_percent():
    assert with_tax(10000) == 10600


def test_coupon():
    assert apply_coupon(2000) == 1500
    assert apply_coupon(300) == 0
