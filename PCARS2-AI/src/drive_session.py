"""
drive_session.py
Sesión UDP compartida para teaching_driver e imitation_driver.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Tuple

from telemetry_udp import (
    UDPListener,
    TelemetryFrame,
    TimingsFrame,
    RaceData,
    VehicleInfo,
    PACKET_CAR_PHYSICS,
    PACKET_TIMINGS,
    PACKET_RACE_DEF,
    PACKET_VEHICLE_NAMES,
)


@dataclass
class DriveSession:
    """Mantiene telemetría sincronizada y drena backlog UDP."""

    listener: UDPListener = field(default_factory=UDPListener)
    udp_timeout: float = 2.0

    last_telem: Optional[TelemetryFrame] = None
    last_timings: Optional[TimingsFrame] = None
    race_data: Optional[RaceData] = None
    vehicle_info: Optional[VehicleInfo] = None
    physics_anchor: Optional[Tuple[float, float, float, float, float, float]] = None

    stats: dict = field(default_factory=lambda: {
        "physics_frames": 0,
        "timeouts": 0,
        "backlog_dropped": 0,
        "other_packets": 0,
    })

    @staticmethod
    def physics_key(telem: TelemetryFrame) -> Tuple[float, float, float, float, float, float]:
        return (
            telem.position[0], telem.position[1], telem.position[2],
            telem.local_velocity[0], telem.local_velocity[1], telem.local_velocity[2],
        )

    def viewed_index(self) -> Optional[int]:
        if self.last_telem is not None:
            return self.last_telem.viewed_participant_index
        return None

    def _apply_packet(self, ptype: int, packet) -> str:
        if ptype == PACKET_CAR_PHYSICS and packet is not None:
            self.last_telem = packet
            return "physics"
        if ptype == PACKET_TIMINGS and packet is not None:
            self.last_timings = packet
            return "timings"
        if ptype == PACKET_RACE_DEF and packet is not None:
            self.race_data = packet
        elif ptype == PACKET_VEHICLE_NAMES and packet is not None:
            self.vehicle_info = packet
        return "other"

    def ingest_pending(self) -> None:
        viewed_idx = self.viewed_index()
        pending = self.listener.drain(viewed_index=viewed_idx)
        physics_seen = 0
        for ptype, packet in pending:
            kind = self._apply_packet(ptype, packet)
            if kind == "physics":
                physics_seen += 1
            elif kind == "other":
                self.stats["other_packets"] += 1
        if physics_seen > 1:
            self.stats["backlog_dropped"] += physics_seen - 1
        if self.last_telem is not None:
            self.physics_anchor = self.physics_key(self.last_telem)

    def recv_blocking(self) -> None:
        ptype, packet = self.listener.recv(
            timeout=self.udp_timeout,
            viewed_index=self.viewed_index(),
        )
        if ptype is None:
            return
        kind = self._apply_packet(ptype, packet)
        if kind == "other":
            self.stats["other_packets"] += 1

    def sync_physics_frame(self) -> bool:
        """Espera un CAR_PHYSICS nuevo. Devuelve False si expira el timeout."""
        self.ingest_pending()
        anchor = self.physics_anchor
        viewed_idx = self.viewed_index()
        deadline = time.monotonic() + self.udp_timeout

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            ptype, packet = self.listener.recv(
                timeout=max(remaining, 0.001),
                viewed_index=viewed_idx,
            )
            if ptype is None:
                break

            kind = self._apply_packet(ptype, packet)
            if kind == "timings":
                continue
            if kind == "other":
                self.stats["other_packets"] += 1
                continue

            key = self.physics_key(packet)
            if anchor is not None and key == anchor:
                self.stats["backlog_dropped"] += 1
                continue

            self.physics_anchor = key
            self.stats["physics_frames"] += 1
            return True

        self.stats["timeouts"] += 1
        return False

    def wait_for_telemetry(self, max_wait_s: float = 30.0) -> bool:
        deadline = time.monotonic() + max_wait_s
        while time.monotonic() < deadline:
            self.recv_blocking()
            if self.last_telem is not None and self.last_timings is not None:
                return True
        return False
