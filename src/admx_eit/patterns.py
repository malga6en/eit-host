from __future__ import annotations

from typing import Iterator, Tuple


ElectrodeTuple = Tuple[int, int, int, int]


def _next_electrode(e: int, n: int) -> int:
    return (e % n) + 1


def _wrap_electrode(e: int, n: int) -> int:
    while e > n:
        e -= n
    while e < 1:
        e += n
    return e


def adjacent_pattern(n: int = 16) -> Iterator[ElectrodeTuple]:
    """Adjacent current pairs with adjacent voltage pairs further around the ring."""
    if n < 4:
        raise ValueError("n must be at least 4")

    for cur_hi in range(1, n + 1):
        cur_lo = _next_electrode(cur_hi, n)

        for offset in range(2, n - 1):
            pot_hi = _wrap_electrode(cur_hi + offset, n)
            pot_lo = _next_electrode(pot_hi, n)

            if len({cur_hi, cur_lo, pot_hi, pot_lo}) < 4:
                continue

            yield cur_hi, cur_lo, pot_hi, pot_lo


def opposite_pattern(n: int = 16) -> Iterator[ElectrodeTuple]:
    """Opposite current pairs and voltage pairs on the two arcs."""
    if n % 2 != 0:
        raise ValueError("n must be even for opposite pattern")

    half = n // 2

    for cur_hi in range(1, half + 1):
        cur_lo = cur_hi + half

        for offset in range(1, half - 1):
            pot_hi_1 = _wrap_electrode(cur_hi + offset, n)
            pot_lo_1 = _next_electrode(pot_hi_1, n)
            if len({cur_hi, cur_lo, pot_hi_1, pot_lo_1}) == 4:
                yield cur_hi, cur_lo, pot_hi_1, pot_lo_1

            pot_hi_2 = _wrap_electrode(cur_lo + offset, n)
            pot_lo_2 = _next_electrode(pot_hi_2, n)
            if len({cur_hi, cur_lo, pot_hi_2, pot_lo_2}) == 4:
                yield cur_hi, cur_lo, pot_hi_2, pot_lo_2
