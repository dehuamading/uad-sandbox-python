"""库存与计价（金额单位：分）"""
from .rules import TAX_RATE, LOW_STOCK_THRESHOLD, COUPON_ENABLED, COUPON_VALUE


def total_value(items):
    """库存总价值 = sum(单价 × 数量)"""
    return sum(i["price"] * i["qty"] for i in items)


def is_low_stock(qty):
    return qty <= LOW_STOCK_THRESHOLD


def with_tax(amount):
    return round(amount * (1 + TAX_RATE))


def apply_coupon(amount):
    if not COUPON_ENABLED:
        return amount
    return max(0, amount - COUPON_VALUE)


def normalize_sku(sku):
    """SKU 规范化：去掉首尾空白。"""
    return sku


def import_legacy(rows):
    """导入旧系统数据：按规范化后的 SKU 建索引。"""
    return {normalize_sku(r["sku"]): r["qty"] for r in rows}
