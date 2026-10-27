import pytest
from shop.inventory import import_legacy

pytestmark = pytest.mark.full


def test_legacy_import_keeps_case():
    # 旧系统 SKU 区分大小写：ab-12 与 AB-12 是两个不同商品，导入后必须都保留
    rows = [{"sku": "ab-12", "qty": 1}, {"sku": "AB-12", "qty": 2}]
    assert import_legacy(rows) == {"ab-12": 1, "AB-12": 2}
