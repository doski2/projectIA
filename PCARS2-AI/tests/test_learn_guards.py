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
