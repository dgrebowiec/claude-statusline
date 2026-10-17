"""Relative token prices and the "weighted tokens" measure.

One weighted token is one uncached input token of Opus 5. Anthropic does not publish the
formula behind subscription limits, so these ratios are a proxy, not an exact count.
The table and weights match claude-token-report.
"""
from typing import List, Mapping, Tuple

W_WRITE_5M = 1.25
W_WRITE_1H = 2.0

REF_PRICE = 5.0  # input price of Opus 5; a model's weight is its input price / REF_PRICE
FALLBACK_PRICE = (5.0, 25.0, 0.50)  # unknown models are counted like Opus 5

# (substring of the model id, input, output, cache read) per 1M tokens; first match wins.
PRICES: List[Tuple[str, float, float, float]] = [
    ("fable-5-1", 10.0, 50.0, 0.25),
    ("mythos-5-1", 10.0, 50.0, 0.25),
    ("fable-5", 10.0, 50.0, 1.00),
    ("mythos-5", 10.0, 50.0, 1.00),
    ("opus-5-5", 4.0, 20.0, 0.20),
    ("opus-5", 5.0, 25.0, 0.50),
    ("opus-4-8", 5.0, 25.0, 0.50),
    ("opus-4-7", 5.0, 25.0, 0.50),
    ("opus-4-6", 5.0, 25.0, 0.50),
    ("opus-4-5", 5.0, 25.0, 0.50),
    ("opus-4", 15.0, 75.0, 1.50),
    ("3-opus", 15.0, 75.0, 1.50),
    ("sonnet-5-5", 2.0, 10.0, 0.20),
    ("sonnet-5", 2.0, 10.0, 0.20),
    ("sonnet", 3.0, 15.0, 0.30),
    ("haiku-4-5", 1.0, 5.0, 0.10),
    ("3-5-haiku", 0.8, 4.0, 0.08),
    ("3-haiku", 0.25, 1.25, 0.025),
    ("haiku", 1.0, 5.0, 0.10),
]


def price_for(model: str) -> Tuple[float, float, float]:
    name = (model or "").lower()
    for pattern, price_in, price_out, price_cache_read in PRICES:
        if pattern in name:
            return price_in, price_out, price_cache_read
    return FALLBACK_PRICE


def weighted(usage: Mapping, model: str) -> float:
    """Weighted tokens of one API usage record, model weight included."""
    cache_creation = usage.get("cache_creation") or {}
    write_5m = cache_creation.get("ephemeral_5m_input_tokens", 0) or 0
    write_1h = cache_creation.get("ephemeral_1h_input_tokens", 0) or 0
    if not write_5m and not write_1h:
        write_5m = usage.get("cache_creation_input_tokens", 0) or 0  # older records: no split
    price_in, price_out, price_cache_read = price_for(model)
    return (
        (usage.get("input_tokens", 0) or 0) * price_in
        + (usage.get("cache_read_input_tokens", 0) or 0) * price_cache_read
        + write_5m * price_in * W_WRITE_5M
        + write_1h * price_in * W_WRITE_1H
        + (usage.get("output_tokens", 0) or 0) * price_out
    ) / REF_PRICE
