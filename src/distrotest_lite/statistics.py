from __future__ import annotations

import math


def wilson(k: int, n: int, z: float = 1.959963984540054) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return [center - half, center + half]


def percentile(values: list[float], p: float) -> float | None:
    finite = sorted(value for value in values if value is not None and math.isfinite(value))
    if not finite:
        return None
    position = (len(finite) - 1) * p
    low = int(math.floor(position))
    high = int(math.ceil(position))
    return finite[low] if low == high else finite[low] * (high - position) + finite[high] * (position - low)


def ci95(values: list[float]) -> list[float] | None:
    low, high = percentile(values, 0.025), percentile(values, 0.975)
    return None if low is None or high is None else [low, high]


def exact_mcnemar_p(b: int, c: int) -> float | None:
    n = b + c
    if n == 0:
        return None
    tail = sum(math.comb(n, index) for index in range(min(b, c) + 1)) / (2**n)
    return min(1.0, 2 * tail)
