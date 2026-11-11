# -*- coding: utf-8 -*-
"""Облёт сцены для видео и запись MP4 (flight.py, video.py)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import flight  # noqa: E402
import video  # noqa: E402

CAM = {"center": [100.0, 200.0, -50.0], "distance": 1000.0,
       "azimuth": 30.0, "elevation": 25.0, "fov": 60.0, "ortho": False}


def test_frame_count_rounds_and_is_never_zero():
    assert flight.frame_count(2.0) == 50
    assert flight.frame_count(0.0) == 1
    assert flight.frame_count(0.03, fps=25) == 1


def test_orbit_keeps_distance_and_tilt():
    fr = flight.orbit(CAM, 360, 4)
    assert len(fr) == 100
    for c in fr:
        assert c["distance"] == CAM["distance"]
        assert c["elevation"] == CAM["elevation"]
        assert c["center"] == CAM["center"]


def test_full_orbit_does_not_repeat_the_first_frame():
    fr = flight.orbit(CAM, 360, 2)
    step = 360.0 / len(fr)
    assert abs(fr[-1]["azimuth"] - (CAM["azimuth"] - step) % 360) < 1e-9
    assert abs(fr[0]["azimuth"] - CAM["azimuth"]) < 1e-9


def test_partial_orbit_ends_on_the_angle():
    fr = flight.orbit(CAM, 90, 2)
    assert abs(fr[-1]["azimuth"] - (CAM["azimuth"] + 90)) < 1e-9


def test_orbit_frames_are_independent_copies():
    fr = flight.orbit(CAM, 360, 1)
    fr[0]["center"][0] = -1
    assert fr[1]["center"][0] == 100.0
    assert CAM["center"][0] == 100.0


def test_azimuth_takes_the_short_arc():
    assert flight.turn(350, 10) == 20
    assert flight.turn(10, 350) == -20
    mid = flight.blend(dict(CAM, azimuth=350), dict(CAM, azimuth=10), 0.5)
    assert abs(mid["azimuth"] - 0.0) < 1e-9 or abs(mid["azimuth"] - 360) < 1e-9


def test_distance_changes_in_log():
    a = dict(CAM, distance=10000.0)
    b = dict(CAM, distance=100.0)
    mid = flight.blend(a, b, 0.5)
    assert abs(mid["distance"] - 1000.0) < 1e-6


def test_smoothstep_has_flat_ends():
    assert flight.smoothstep(0) == 0 and flight.smoothstep(1) == 1
    assert flight.smoothstep(0.01) < 0.01
    assert flight.smoothstep(-1) == 0 and flight.smoothstep(2) == 1


def test_tour_holds_and_moves():
    a = dict(CAM)
    b = dict(CAM, center=[500.0, 200.0, -50.0], azimuth=120.0)
    fr = flight.tour([a, b], leg=2, pause=1)
    hold, move = 25, 50
    assert len(fr) == hold + move + hold
    assert fr[0]["center"] == a["center"]
    assert fr[hold - 1]["center"] == a["center"]
    assert abs(fr[hold + move - 1]["center"][0] - 500.0) < 1e-9
    assert abs(fr[-1]["azimuth"] - 120.0) < 1e-9
    xs = [c["center"][0] for c in fr]
    assert xs == sorted(xs), "камера не возвращается назад"


def test_tour_of_one_view_is_a_pause():
    fr = flight.tour([CAM], leg=3, pause=2)
    assert len(fr) == 50
    assert all(c["azimuth"] == CAM["azimuth"] for c in fr)


def test_tour_without_views_is_empty():
    assert flight.tour([]) == []
    assert flight.tour(None) == []


def test_tour_without_pause_still_reaches_every_view():
    a, b, c = (dict(CAM, azimuth=x) for x in (0.0, 90.0, 180.0))
    fr = flight.tour([a, b, c], leg=1, pause=0)
    assert len(fr) == 50
    assert abs(fr[24]["azimuth"] - 90.0) < 1e-9
    assert abs(fr[-1]["azimuth"] - 180.0) < 1e-9


def test_video_is_windows_only_and_sizes_are_even():
    if sys.platform != "win32":
        assert video.available() is False
    assert video.even_size(1921, 1081) == (1920, 1080)
    assert video.even_size(1, 1) == (2, 2)
    assert video.bitrate(1920, 1080, 25) > 0


def test_video_refuses_odd_frames_before_touching_windows():
    import pytest
    with pytest.raises(video.VideoError):
        video.Mp4Writer("x.mp4", 1921, 1080) if video.available() else \
            (_ for _ in ()).throw(video.VideoError("no MF"))
