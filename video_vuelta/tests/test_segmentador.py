"""Tests de `segmentador.py`: formas, IoU y que una red aprenda una máscara trivial."""

import numpy as np
import torch

from video_vuelta.src import segmentador as sg


def test_la_red_conserva_la_resolucion_y_da_dos_clases():
    y = sg.UNetPequena()(torch.zeros(2, 3, 144, 256))
    assert y.shape == (2, 2, 144, 256)


def test_iou_ignora_los_pixeles_255():
    verdad = np.array([[1, 1, 0, 255]], np.uint8)
    pred = np.array([[1, 0, 0, 1]], np.uint8)
    assert abs(sg.iou_pasillo(pred, verdad) - 0.5) < 1e-9  # intersección 1, unión 2; el 255 no cuenta


def test_aprende_una_mascara_sencilla():
    rng = np.random.default_rng(0)
    n = 48
    img = np.zeros((n, 144, 256, 3), np.uint8)
    mask = np.zeros((n, 144, 256), np.uint8)
    for k in range(n):
        x0 = rng.integers(40, 120)
        img[k, 72:, x0:x0 + 100] = 200  # «calzada» clara en la mitad inferior
        mask[k, 72:, x0:x0 + 100] = 1
    datos = {"imagenes": img, "mascaras": mask, "s": np.r_[np.zeros(36), np.full(12, 5000)].astype(np.float32), "vuelta": np.ones(n, np.int16)}
    torch.set_num_threads(2)
    _, hist = sg.entrenar(datos, s_val=1000.0, epocas=6, lote=12, log=lambda m: None)
    assert hist["iou_val"][-1] > 0.85
