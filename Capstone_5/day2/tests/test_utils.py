from utils import clamp, is_even, square


def test_clamp_inside_range():
    assert clamp(5, 0, 10) == 5


def test_clamp_above_range():
    assert clamp(15, 0, 10) == 10


def test_square_positive():
    assert square(5) == 25


def test_square_zero():
    assert square(0) == 0


def test_is_even_positive():
    assert is_even(4) is True


def test_is_even_negative():
    assert is_even(-3) is False
