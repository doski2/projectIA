"""Segmentador pequeño del pasillo (D7 de docs/DECISIONES.md): U-Net de PyTorch puro (sin torchvision ni ultralytics), pensado para CPU.

Uso:
    python video_vuelta/src/segmentador.py entrenar --datos data/x.npz --salida data/modelo.pt [--epocas 20] [--s-val 2400]

Entrena con los fotogramas de distancia de vuelta < `--s-val` y valida con el resto (un tramo de pista que la red no ha visto, en las dos vueltas),
porque validar con la otra vuelta del mismo tramo sería hacer trampa. Métrica: IoU de la clase «pasillo» sin contar la carrocería (255).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

IGNORAR = 255
MEDIA = np.array([0.45, 0.45, 0.45], np.float32)
STD = np.array([0.25, 0.25, 0.25], np.float32)


def _bloque(c_in: int, c_out: int) -> nn.Sequential:
    return nn.Sequential(nn.Conv2d(c_in, c_out, 3, padding=1, bias=False), nn.BatchNorm2d(c_out), nn.ReLU(inplace=True),
                         nn.Conv2d(c_out, c_out, 3, padding=1, bias=False), nn.BatchNorm2d(c_out), nn.ReLU(inplace=True))


class UNetPequena(nn.Module):
    """Cuatro niveles (÷2 cada uno); la entrada debe tener alto y ancho múltiplos de 8."""

    def __init__(self, canales=(16, 32, 64, 96), clases: int = 2):
        super().__init__()
        c1, c2, c3, c4 = canales
        self.e1, self.e2, self.e3, self.e4 = _bloque(3, c1), _bloque(c1, c2), _bloque(c2, c3), _bloque(c3, c4)
        self.d3, self.d2, self.d1 = _bloque(c4 + c3, c3), _bloque(c3 + c2, c2), _bloque(c2 + c1, c1)
        self.salida = nn.Conv2d(c1, clases, 1)

    def forward(self, x):
        e1 = self.e1(x)
        e2 = self.e2(F.max_pool2d(e1, 2))
        e3 = self.e3(F.max_pool2d(e2, 2))
        e4 = self.e4(F.max_pool2d(e3, 2))
        up = lambda a, b: torch.cat([F.interpolate(a, size=b.shape[-2:], mode="bilinear", align_corners=False), b], 1)  # noqa: E731
        d3 = self.d3(up(e4, e3))
        d2 = self.d2(up(d3, e2))
        d1 = self.d1(up(d2, e1))
        return self.salida(d1)


def a_tensor(imagenes: np.ndarray) -> torch.Tensor:
    """(N, H, W, 3) uint8 RGB -> (N, 3, H, W) float normalizado."""
    x = (imagenes.astype(np.float32) / 255.0 - MEDIA) / STD
    return torch.from_numpy(np.ascontiguousarray(x.transpose(0, 3, 1, 2)))


def iou_pasillo(pred: np.ndarray, verdad: np.ndarray) -> float:
    """IoU de la clase 1 sin contar los píxeles ignorados (255)."""
    valido = verdad != IGNORAR
    p, v = (pred == 1) & valido, (verdad == 1) & valido
    union = (p | v).sum()
    return float((p & v).sum() / union) if union else float("nan")


def predecir(modelo: nn.Module, imagenes: np.ndarray, lote: int = 32) -> np.ndarray:
    modelo.eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(imagenes), lote):
            out.append(modelo(a_tensor(imagenes[i:i + lote])).argmax(1).numpy().astype(np.uint8))
    return np.concatenate(out)


def entrenar(datos: dict, s_val: float, epocas: int, lote: int = 16, lr: float = 3e-3, semilla: int = 0, log=print) -> tuple[nn.Module, dict]:
    torch.manual_seed(semilla)
    rng = np.random.default_rng(semilla)
    tr, va = datos["s"] < s_val, datos["s"] >= s_val
    xi, yi = datos["imagenes"][tr], datos["mascaras"][tr]
    xv, yv = datos["imagenes"][va], datos["mascaras"][va]
    log(f"entrenamiento {len(xi)} fotogramas (s < {s_val:g}), validación {len(xv)} (s ≥ {s_val:g})")
    modelo = UNetPequena()
    opt = torch.optim.AdamW(modelo.parameters(), lr=lr, weight_decay=1e-4)
    pasos = epocas * ((len(xi) + lote - 1) // lote)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=pasos)
    hist = {"iou_val": [], "perdida": []}
    for ep in range(epocas):
        t0 = time.time()
        modelo.train()
        orden = rng.permutation(len(xi))
        perdida = 0.0
        for i in range(0, len(orden), lote):
            idx = orden[i:i + lote]
            x, y = xi[idx].copy(), yi[idx].copy()
            volteo = rng.random(len(idx)) < 0.5  # el pasillo es simétrico: voltear imagen y máscara es una etiqueta válida
            x[volteo], y[volteo] = x[volteo][:, :, ::-1], y[volteo][:, :, ::-1]
            x = x.astype(np.float32) * rng.uniform(0.7, 1.3, (len(idx), 1, 1, 1)) + rng.uniform(-20, 20, (len(idx), 1, 1, 1))  # brillo y contraste
            xt = a_tensor(np.clip(x, 0, 255).astype(np.uint8))
            loss = F.cross_entropy(modelo(xt), torch.from_numpy(y.astype(np.int64)), ignore_index=IGNORAR)
            opt.zero_grad(); loss.backward(); opt.step(); sched.step()
            perdida += float(loss.detach()) * len(idx)
        iou = iou_pasillo(predecir(modelo, xv), yv) if len(xv) else float("nan")
        hist["iou_val"].append(iou); hist["perdida"].append(perdida / len(xi))
        log(f"época {ep + 1:2d}/{epocas}  pérdida {perdida / len(xi):.4f}  IoU validación {iou:.4f}  ({time.time() - t0:.0f} s)")
    return modelo, hist


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("entrenar")
    e.add_argument("--datos", type=Path, required=True)
    e.add_argument("--salida", type=Path, required=True)
    e.add_argument("--epocas", type=int, default=20)
    e.add_argument("--s-val", type=float, default=2400.0)
    e.add_argument("--hilos", type=int, default=8)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    torch.set_num_threads(a.hilos)
    d = dict(np.load(a.datos))
    modelo, hist = entrenar(d, a.s_val, a.epocas, log=lambda m: print(m, flush=True))
    torch.save({"estado": modelo.state_dict(), "hist": hist, "s_val": a.s_val}, a.salida)
    print("guardado:", a.salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
