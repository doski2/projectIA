import json
from types import SimpleNamespace
from typing import cast

from experimental.common import registro_pasivo as rp
from experimental.common.informe_c0 import damage_events, load_log


def _telem(i, ref, engine_damage=0):
    pt = ref.lookup(float(10 + i))
    return SimpleNamespace(
        speed=11.0, throttle=40, brake=0, steering=3, raw_steering=3, gear=1, num_gears=4, rpm=3800,
        position=pt.position, world_velocity=(11.0, 0.0, 0.0), angular_velocity=(0.0, 0.01, 0.0),
        local_acceleration=(0.0, 0.0, 0.1), terrain=(0, 0, 0, 0), tyre_rps=(40.0,) * 4,
        aero_damage=0, engine_damage=engine_damage, brake_damage=(0, 0, 0, 0), suspension_damage=(0, 0, 0, 0),
        tyre_flags=(7, 7, 7, 7), brake_temp=(100, 100, 100, 100), tyre_temp=(60, 60, 60, 60),
        crash_state=0, car_flags=2,
    )


class FakeSession:
    def __init__(self, ref, ticks=40, hit_at=20):
        self.frames = [(_telem(i, ref, 30 if i >= hit_at else 0), i) for i in range(ticks)]
        self.last_telem = self.last_timings = self.game_state = None

    def wait_for_telemetry(self):
        return True

    def sync_physics_frame(self):
        if not self.frames:
            return False
        telem, i = self.frames.pop(0)
        self.last_telem = telem
        self.last_timings = SimpleNamespace(
            sector=1, current_sector_time=1.0 + i / 60, current_time=1.0 + i / 60, lap_distance=10.0 + i, current_lap=1,
        )
        return True


def test_pasivo_records_ticks_and_damage_event(tmp_path):
    ref = rp.ReferenceLine.load(str(rp.APP / "src" / "refs" / "sugo_ai.json"))
    path = rp.run("t", minutes=1, after_damage_s=0, session=cast(rp.DriveSession, FakeSession(ref)), out_dir=tmp_path)
    assert path is not None and path.is_file()
    header, ticks, events = load_log(path)
    assert header["experiment"] == "pasivo_t" and header["origin"] == "experimental" and header["log_schema"] == 2
    assert len(ticks) == 40 and {t["drive_source"] for t in ticks} == {"manual"}
    assert ticks[0]["throttle"] > 0 and "tyre_flags" in ticks[0]["vehicle"]
    dmg = damage_events(events)
    assert len(dmg) == 1 and dmg[0]["canales"] == ["engine"] and dmg[0]["niveles"]["engine"] == 30
    # el modo pasivo no corta por daño: el log sigue hasta quedarse sin telemetría
    assert json.loads(path.read_text(encoding="utf-8").splitlines()[0])["mode"] == "passive"
