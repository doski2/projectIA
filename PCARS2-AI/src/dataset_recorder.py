"""
dataset_recorder.py
Graba demostraciones etiquetadas (DEMO / TEACHER / MIXED) en JSONL.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import numpy as np

from obs_builder import OBS_DIM
from obs_universal import OBS_SCHEMA, OBS_UNIVERSAL_DIM
from teacher_intents import encode_reason_id, normalize_reason, rule_for_reason

ORIGIN_DEMO = "DEMO"
ORIGIN_TEACHER = "TEACHER"
ORIGIN_MIXED = "MIXED"

MAX_CTE_RECORD = 8.0
MIN_QUALITY = 0.3


@dataclass
class DatasetSample:
    origin: str
    timestamp: float
    lap_distance: float
    obs: List[float]
    action: List[float]
    quality: float
    confidence: float
    teacher_reason: str = ""
    cte: float = 0.0
    heading_err: float = 0.0
    mix_alpha: Optional[float] = None
    obs_schema: str = "legacy_19"
    reason_id: int = 0
    rule: Optional[dict] = None
    track_name: str = ""
    learn_stage: str = ""
    speed_band_kmh: float = 0.0

    def to_dict(self) -> dict:
        d = {
            "origin": self.origin,
            "timestamp": self.timestamp,
            "lap_distance": self.lap_distance,
            "obs": self.obs,
            "action": self.action,
            "quality": self.quality,
            "confidence": self.confidence,
            "teacher_reason": self.teacher_reason,
            "reason_id": self.reason_id,
            "cte": self.cte,
            "heading_err": self.heading_err,
            "obs_schema": self.obs_schema,
        }
        if self.rule is not None:
            d["rule"] = self.rule
        if self.track_name:
            d["track_name"] = self.track_name
        if self.learn_stage:
            d["learn_stage"] = self.learn_stage
        if self.speed_band_kmh > 0:
            d["speed_band_kmh"] = self.speed_band_kmh
        if self.mix_alpha is not None:
            d["mix_alpha"] = self.mix_alpha
        return d


@dataclass
class DatasetRecorder:
    output_path: str
    origin: str = ORIGIN_TEACHER
    max_cte: float = MAX_CTE_RECORD
    min_quality: float = MIN_QUALITY

    samples_written: int = 0
    samples_skipped: int = 0
    _file = None

    def open(self) -> None:
        path = Path(self.output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(path, "a", encoding="utf-8")

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def _quality_score(self, cte: float, safety: bool) -> float:
        if safety:
            return 0.0
        cte_score = max(0.0, 1.0 - cte / self.max_cte)
        return round(cte_score, 3)

    def maybe_record(
        self,
        obs: np.ndarray,
        action: tuple,
        lap_distance: float,
        cte: float,
        heading_err: float,
        teacher_reason: str = "",
        safety: bool = False,
        confidence: float = 1.0,
        mix_alpha: Optional[float] = None,
        obs_schema: str = "legacy_19",
        track_name: str = "",
        learn_stage: str = "",
        speed_band_kmh: float = 0.0,
    ) -> bool:
        if self._file is None:
            return False

        quality = self._quality_score(cte, safety)
        if quality < self.min_quality:
            self.samples_skipped += 1
            return False

        expected_dim = OBS_UNIVERSAL_DIM if obs_schema == OBS_SCHEMA else OBS_DIM
        if obs.shape[0] != expected_dim:
            self.samples_skipped += 1
            return False

        norm_reason = normalize_reason(teacher_reason)
        sample = DatasetSample(
            origin=self.origin,
            timestamp=time.time(),
            lap_distance=lap_distance,
            obs=[float(x) for x in obs],
            action=[float(action[0]), float(action[1]), float(action[2])],
            quality=quality,
            confidence=confidence,
            teacher_reason=norm_reason,
            reason_id=encode_reason_id(norm_reason),
            rule=rule_for_reason(norm_reason),
            cte=cte,
            heading_err=heading_err,
            mix_alpha=mix_alpha,
            obs_schema=obs_schema,
            track_name=track_name,
            learn_stage=learn_stage,
            speed_band_kmh=speed_band_kmh,
        )
        self._file.write(json.dumps(sample.to_dict()) + "\n")
        self._file.flush()
        self.samples_written += 1
        return True

    @staticmethod
    def default_output_path(track: str, combo: str, origin: str) -> str:
        date = datetime.now().strftime("%Y%m%d")
        return f"data/{track}_{combo}_{origin.lower()}_{date}.jsonl"


def _normalize_action(action) -> np.ndarray:
    """Convierte acción física [0,1] a espacio codificado [-1,1] si aplica."""
    from obs_builder import encode_action

    a = np.array(action, dtype=np.float32)
    if a[0] >= 0.0 and a[1] >= 0.0 and a[0] <= 1.0 and a[1] <= 1.0:
        return encode_action(float(a[0]), float(a[1]), float(a[2]))
    return a


def load_dataset(
    path: str,
    origin: Optional[str] = None,
    min_quality: float = 0.0,
    min_confidence: float = 0.0,
) -> tuple:
    """Carga JSONL y devuelve (obs_array, act_array, meta_list)."""
    obs_list: List[np.ndarray] = []
    act_list: List[np.ndarray] = []
    meta: List[dict] = []

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if origin and row.get("origin") != origin:
                continue
            if row.get("quality", 0.0) < min_quality:
                continue
            if row.get("confidence", 0.0) < min_confidence:
                continue
            obs_list.append(np.array(row["obs"], dtype=np.float32))
            act_list.append(np.array(row["action"], dtype=np.float32))
            meta.append(row)

    if not obs_list:
        return np.zeros((0, OBS_DIM), dtype=np.float32), np.zeros((0, 3), dtype=np.float32), []

    return np.stack(obs_list), np.stack(act_list), meta


def load_universal_dataset(
    path: str,
    origin: Optional[str] = None,
    min_quality: float = 0.0,
    min_confidence: float = 0.0,
    learn_stage: Optional[str] = None,
    speed_band_kmh: Optional[float] = None,
) -> tuple:
    """Carga JSONL universal_v1 → (obs, act, reason_ids, meta)."""
    obs_list: List[np.ndarray] = []
    act_list: List[np.ndarray] = []
    reason_ids: List[int] = []
    meta: List[dict] = []

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("obs_schema") != OBS_SCHEMA:
                continue
            if origin and row.get("origin") != origin:
                continue
            if row.get("quality", 0.0) < min_quality:
                continue
            if row.get("confidence", 0.0) < min_confidence:
                continue
            if learn_stage is not None and row.get("learn_stage") != learn_stage:
                continue
            if speed_band_kmh is not None:
                row_band = row.get("speed_band_kmh")
                if row_band is None or float(row_band) != float(speed_band_kmh):
                    continue
            obs_list.append(np.array(row["obs"], dtype=np.float32))
            act_list.append(_normalize_action(row["action"]))
            rid = row.get("reason_id")
            if rid is None:
                rid = encode_reason_id(row.get("teacher_reason", ""))
            reason_ids.append(int(rid))
            meta.append(row)

    if not obs_list:
        return (
            np.zeros((0, OBS_UNIVERSAL_DIM), dtype=np.float32),
            np.zeros((0, 3), dtype=np.float32),
            np.zeros(0, dtype=np.int64),
            [],
        )

    return (
        np.stack(obs_list),
        np.stack(act_list),
        np.array(reason_ids, dtype=np.int64),
        meta,
    )


def merge_datasets(
    paths: List[str],
    origin: Optional[str] = None,
    min_quality: float = 0.0,
    min_confidence: float = 0.0,
) -> tuple:
    """Combina varios JSONL universales (multi-pista)."""
    all_obs, all_act, all_rid, all_meta = [], [], [], []
    for path in paths:
        obs, act, rid, meta = load_universal_dataset(
            path, origin=origin, min_quality=min_quality, min_confidence=min_confidence,
        )
        if len(obs) == 0:
            continue
        all_obs.append(obs)
        all_act.append(act)
        all_rid.append(rid)
        all_meta.extend(meta)

    if not all_obs:
        return (
            np.zeros((0, OBS_UNIVERSAL_DIM), dtype=np.float32),
            np.zeros((0, 3), dtype=np.float32),
            np.zeros(0, dtype=np.int64),
            [],
        )

    return np.concatenate(all_obs), np.concatenate(all_act), np.concatenate(all_rid), all_meta
