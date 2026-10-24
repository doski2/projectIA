from learn_guards import SustainedCteGuard, is_poor_demo


def test_guard_needs_sustained_cte():
    g = SustainedCteGuard(enter_m=2.0, release_m=1.0, hold_s=0.1)
    n = g.hold_steps
    assert not any(g.update(2.5) for _ in range(n - 1))
    assert g.update(2.5)


def test_guard_resets_on_dip_before_activation():
    g = SustainedCteGuard(enter_m=2.0, release_m=1.0, hold_s=0.1)
    for _ in range(g.hold_steps - 1):
        g.update(2.5)
    g.update(0.5)
    assert not g.update(2.5)


def test_guard_hysteresis_release():
    g = SustainedCteGuard(enter_m=2.0, release_m=1.0, hold_s=0.1)
    for _ in range(g.hold_steps):
        g.update(-2.5)
    assert g.active
    assert g.update(1.5)
    assert not g.update(0.9)


def test_poor_demo_reasons():
    assert is_poor_demo("safety_off_surface")
    assert is_poor_demo("safety_no_progress")
    assert not is_poor_demo("maintain_speed")
    assert not is_poor_demo("safety_off_track")


def test_vehicle_diag_fields():
    from types import SimpleNamespace

    from session_log import vehicle_diag

    t = SimpleNamespace(
        steering=-64, raw_steering=127, angular_velocity=(0.0, 0.2, 0.0),
        local_acceleration=(0.0, 0.0, 3.0), terrain=(0, 0, 7, 7),
        tyre_rps=(10.123, 10.0, 9.0, 9.0), throttle=255, brake=0,
    )
    d = vehicle_diag(t)
    assert d["game_steer"] == -0.504 and d["raw_steer"] == 1.0
    assert d["yaw_rate"] == 0.2 and d["lat_accel"] == 3.0
    assert d["game_throttle"] == 1.0 and d["game_brake"] == 0.0
    assert d["terrain"] == [0, 0, 7, 7] and d["tyre_rps"][0] == 10.1


def test_guard_spin_trigger_fires_without_waiting_hold():
    g = SustainedCteGuard(enter_m=3.5, release_m=2.5, hold_s=2.0)
    assert g.update(2.6, speed_ms=16.0, heading_err=-0.7)
    assert g.active


def test_guard_spin_trigger_ignores_slow_or_small_deviation():
    g = SustainedCteGuard()
    assert not g.update(2.6, speed_ms=5.0, heading_err=-0.8)  # lento
    assert not g.update(1.5, speed_ms=16.0, heading_err=-0.8)  # cerca de la línea
    assert not g.update(2.6, speed_ms=16.0, heading_err=0.3)  # rumbo normal


def test_stuck_abort_after_hold():
    from learn_guards import StuckOffTrackAbort

    a = StuckOffTrackAbort(hold_s=10.0)
    assert not a.update(19.0, 0.0, now=100.0)
    assert not a.update(19.0, 0.0, now=109.9)
    assert a.update(19.0, 0.0, now=110.0)


def test_stuck_abort_resets_when_moving_or_near_line():
    from learn_guards import StuckOffTrackAbort

    a = StuckOffTrackAbort(hold_s=10.0)
    a.update(19.0, 0.0, now=100.0)
    assert not a.update(19.0, 3.0, now=108.0)  # se movió
    assert not a.update(19.0, 0.0, now=112.0)  # reinicia la cuenta
    a.update(19.0, 0.0, now=113.0)
    assert not a.update(2.0, 0.0, now=125.0)  # volvió a la línea


def test_guard_spin_release_needs_heading_recovered():
    g = SustainedCteGuard(enter_m=3.5, release_m=2.5, hold_s=2.0)
    assert g.update(2.6, speed_ms=16.0, heading_err=-0.7)
    assert g.update(2.4, speed_ms=16.0, heading_err=-0.7)  # sin rebote
    assert not g.update(2.0, speed_ms=16.0, heading_err=-0.1)
