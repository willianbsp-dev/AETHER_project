from machine_feira.filter import OneEuroFilter, PointFilter
from machine_feira.types import Point


def test_one_euro_filter_smoothing() -> None:
    f = OneEuroFilter(min_cutoff=1.0, beta=0.01)

    # Primeiro valor passa sem alteração
    v0 = f.filter(10.0, 0.0)
    assert v0 == 10.0

    # Jitter em repouso deve ser atenuado
    v1 = f.filter(10.5, 0.033)
    assert 10.0 < v1 < 10.5

    v2 = f.filter(10.0, 0.066)
    assert abs(v2 - 10.0) < 0.3


def test_point_filter_2d() -> None:
    pf = PointFilter(min_cutoff=1.0, beta=0.01)
    p0 = pf.filter(Point(0.5, 0.5), 0.0)
    assert p0.x == 0.5 and p0.y == 0.5

    p1 = pf.filter(Point(0.52, 0.48), 0.033)
    assert 0.5 < p1.x < 0.52
    assert 0.48 < p1.y < 0.5

