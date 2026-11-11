"""Small helper functions."""


def clamp(value: float, low: float, high: float) -> float:
    """Limit value to the range [low, high]."""
    return max(low, min(value, high))


def square(x: float) -> float:
    """Return x squared."""
    return x * x


def is_even(n: int) -> bool:
    """Return True when an integer is even."""
    return n % 2 == 0
