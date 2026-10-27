# 新合同条款（与 docs/business-rules.md 冲突，需产品负责人裁决）
from shop.inventory import with_tax


def test_contract_tax_8_percent():
    assert with_tax(10000) == 10800
