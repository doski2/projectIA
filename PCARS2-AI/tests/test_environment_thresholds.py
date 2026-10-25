"""Umbrales de terminación del entorno (sin hardware)."""

from environment import (
    GRACE_STEPS,
    NO_PROGRESS_CURRICULUM_TIME_S,
    NO_PROGRESS_TIME_S,
    STUCK_SPEED_BASICS_MS,
    STUCK_SPEED_MS,
    STUCK_TIME_BASICS_S,
    STUCK_TIME_S,
    termination_frame_count,
)


def test_no_progress_stricter_without_curriculum():
    assert termination_frame_count(NO_PROGRESS_TIME_S) == 720  # 12s × 60 fps


def test_no_progress_relaxed_with_curriculum_or_basics():
    assert termination_frame_count(NO_PROGRESS_CURRICULUM_TIME_S) == 1800  # 30s × 60 fps


def test_expected_episode_cap_frames_with_curriculum():
    cap = GRACE_STEPS + termination_frame_count(NO_PROGRESS_CURRICULUM_TIME_S)
    assert cap == 2050  # 250 grace + 1800 no_progress


def test_stuck_relaxed_in_basics():
    assert STUCK_SPEED_BASICS_MS < STUCK_SPEED_MS
    assert STUCK_TIME_BASICS_S > STUCK_TIME_S
    assert termination_frame_count(STUCK_TIME_S) == 480  # 8s × 60 fps
    assert termination_frame_count(STUCK_TIME_BASICS_S) == 900  # 15s × 60 fps


def test_termination_independent_of_frame_skip():
    """Los contadores avanzan por frame de juego; frame_skip no acorta el tiempo real."""
    assert termination_frame_count(8.0) == 480
    assert termination_frame_count(15.0) == 900
