"""Tests del signo de signed_lateral_error."""

from obs_universal import signed_lateral_error
from reference_recorder import ReferenceLine, ReferencePoint


def _straight_ref() -> ReferenceLine:
    points = [
        ReferencePoint(
            lap_distance=float(d),
            position=(float(d), 0.0, 0.0),
            speed=10.0,
            throttle=100,
            brake=0,
            steering=0,
            gear=2,
            orientation=(0.0, 0.0, 0.0),
            local_velocity=(10.0, 0.0, 0.0),
        )
        for d in range(30)
    ]
    return ReferenceLine(points=points, track_length=30.0, track_name="straight", lap_time=3.0)


def test_signed_lateral_error_left_and_right():
    ref = _straight_ref()
    d = 10.0
    pt = ref.lookup(d)
    hv = ref.heading_vector(d)
    assert pt is not None
    assert hv is not None
    rx, rz = hv[1], -hv[0]
    left = (pt.position[0] + rx * (-2.0), pt.position[1], pt.position[2] + rz * (-2.0))
    right = (pt.position[0] + rx * 2.0, pt.position[1], pt.position[2] + rz * 2.0)
    assert signed_lateral_error(ref, left, d) < 0.0
    assert signed_lateral_error(ref, right, d) > 0.0
