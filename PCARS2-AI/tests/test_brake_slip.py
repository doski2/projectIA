"""Tests del limitador de frenada por deslizamiento (V43): fórmula, apagado, recuperación y un lazo cerrado con una rueda delantera simulada."""

import math

import pytest

from brake_slip import MIN_REAR_RPS, BrakeSlipConfig, BrakeSlipLimiter

R = 0.274  # radio efectivo (m) medido en rodadura libre


def _limiter(limit=0.2, **kw):
    return BrakeSlipLimiter(BrakeSlipConfig(limit=limit, **kw))


def test_deslizamiento_relativo_de_las_delanteras_frente_a_las_traseras():
    s = BrakeSlipLimiter.relative_slip
    assert s((100.0, 100.0, 100.0, 100.0)) == 0.0
    assert s((80.0, 80.0, 100.0, 100.0)) == pytest.approx(0.2)
    assert s((0.0, 0.0, 100.0, 100.0)) == 1.0
    assert s((-80.0, -80.0, -100.0, -100.0)) == pytest.approx(0.2)  # el signo del giro no importa
    assert s((110.0, 110.0, 100.0, 100.0)) == 0.0  # delanteras más rápidas: no es bloqueo
    assert s((60.0, 100.0, 100.0, 100.0)) == pytest.approx(0.2)  # media de las dos delanteras
    assert s((50.0, 50.0, MIN_REAR_RPS - 1, MIN_REAR_RPS - 1)) is None  # sin referencia fiable


def test_apagado_no_toca_el_pedal():
    lim = BrakeSlipLimiter()  # limit = 0
    assert not lim.active
    assert lim.apply(1.0, (0.0, 0.0, 100.0, 100.0)) == 1.0
    assert lim.scale == 1.0


def test_por_debajo_del_objetivo_el_pedal_pasa_entero():
    lim = _limiter(0.2)
    for _ in range(50):
        assert lim.apply(0.8, (90.0, 90.0, 100.0, 100.0)) == pytest.approx(0.8)  # deslizamiento 0,10


def test_un_bloqueo_baja_la_escala_hasta_el_minimo_y_nunca_a_cero():
    lim = _limiter(0.2, min_scale=0.15)
    out = [lim.apply(1.0, (0.0, 0.0, 100.0, 100.0)) for _ in range(30)]
    assert out[0] < 1.0 and out == sorted(out, reverse=True)
    assert out[-1] == pytest.approx(0.15)


def test_la_escala_se_recupera_al_recuperar_agarre_y_se_restablece_sin_freno():
    lim = _limiter(0.2, up_rate=0.05)
    for _ in range(10):
        lim.apply(1.0, (0.0, 0.0, 100.0, 100.0))
    baja = lim.scale
    assert baja < 0.3
    for _ in range(5):
        lim.apply(1.0, (95.0, 95.0, 100.0, 100.0))
    assert lim.scale == pytest.approx(baja + 5 * 0.05)
    for _ in range(40):
        lim.apply(0.0, (95.0, 95.0, 100.0, 100.0))  # sin freno la escala vuelve a 1
    assert lim.scale == 1.0
    assert lim.apply(0.0, (0.0, 0.0, 100.0, 100.0)) == 0.0  # y sin pedal no se inventa freno


def test_sin_referencia_de_traseras_no_limita_y_el_diag_lo_dice():
    lim = _limiter(0.2)
    assert lim.apply(1.0, (0.0, 0.0, 1.0, 1.0)) == 1.0
    assert lim.diag() == {"brake_slip": -1.0, "brake_scale": 1.0}
    lim.apply(1.0, (50.0, 50.0, 100.0, 100.0))
    d = lim.diag()
    assert d["brake_slip"] == pytest.approx(0.5) and d["brake_scale"] < 1.0


# ---- lazo cerrado con una rueda delantera simulada ------------------------------------------------------------------------------------------------
def _fx(slip):
    """Fuerza longitudinal normalizada: pico hacia el 13 % de deslizamiento y ≈ 30 % menos con la rueda bloqueada."""
    return math.sin(1.6 * math.atan(10.0 * max(0.0, min(1.0, slip))))


def _frenada(limiter, v0=40.0, pedal=1.0, t_max=3.0, mu=1.6):
    """Frenada a fondo de un coche de 700 kg desde v0 m/s. Devuelve (deslizamiento relativo máx. tras 0,5 s, % de ticks bloqueados, deceleración media, distancia)."""
    dt = 1.0 / 60.0
    m, g = 700.0, 9.81
    n_f = n_r = 0.5 * m * g
    inercia, tb_max = 1.5, 2500.0
    v, w_f, x, t = v0, v0 / R, 0.0, 0.0
    maximos, bloqueados, ticks = 0.0, 0, 0
    while t < t_max and v > 8.0:
        w_r = 0.95 * v / R  # las traseras no se acercan al límite
        slip_f = 1.0 - w_f * R / v
        fx_f = mu * n_f * _fx(slip_f)
        fx_r = mu * n_r * _fx(0.05)
        rel = max(0.0, 1.0 - w_f / w_r)
        pedal_aplicado = limiter.apply(pedal, (w_f, w_f, w_r, w_r)) if limiter else pedal
        w_f = max(0.0, w_f + dt * (-pedal_aplicado * tb_max + fx_f * R) / inercia)
        v -= dt * (fx_f + fx_r) / m
        x += v * dt
        t += dt
        if t > 0.5:
            maximos = max(maximos, rel)
        ticks += 1
        bloqueados += rel > 0.9
    return maximos, bloqueados / ticks, (v0 - v) / t, x


def test_sin_limitador_la_rueda_delantera_se_bloquea_a_pedal_1():
    maximo, bloqueado, _, _ = _frenada(None)
    assert maximo > 0.95 and bloqueado > 0.6


def test_con_limitador_no_se_bloquea_y_frena_mas_que_bloqueado():
    maximo0, bloqueado0, dec0, x0 = _frenada(None)
    lim = _limiter(0.2)
    maximo1, bloqueado1, dec1, x1 = _frenada(lim)
    assert bloqueado1 == 0.0
    assert maximo1 < 0.5  # tras el transitorio inicial no se acerca al bloqueo
    assert dec1 > dec0 * 1.03  # el bloqueo pierde fuerza: sin él frena más y recorre menos distancia
    assert x1 < x0


def test_el_limitador_se_adapta_a_un_agarre_distinto():
    """Con el mismo ajuste, un agarre menor (mu 1,0) y mayor (mu 2,2) tampoco bloquean: el límite no depende de un pedal fijo."""
    for mu in (1.0, 2.2):
        assert _frenada(None, mu=mu)[1] > 0.5  # sin limitador, a pedal 1,0, bloquea en los dos casos
        maximo, bloqueado, _, _ = _frenada(_limiter(0.2), mu=mu)
        assert bloqueado == 0.0 and maximo < 0.7


def test_los_valores_por_defecto_recuperan_el_pedal_en_unos_0_3_s():
    """V45: con 0,02 por tick el pedal tardaba ≈ 0,6 s en volver y la frenada perdía ≈ 17 %; con 0,05 vuelve a 1,0 en ≈ 17 ticks."""
    cfg = BrakeSlipConfig(limit=0.2)
    assert cfg.down_gain == 1.0 and cfg.up_rate == 0.05
    lim = BrakeSlipLimiter(cfg)
    for _ in range(20):
        lim.apply(1.0, (0.0, 0.0, 100.0, 100.0))  # bloqueo: la escala baja al mínimo
    assert lim.scale == pytest.approx(cfg.min_scale)
    ticks = 0
    while lim.scale < 1.0 and ticks < 100:
        lim.apply(1.0, (95.0, 95.0, 100.0, 100.0))  # agarre recuperado
        ticks += 1
    assert ticks <= 18
