# Dependencias — PCARS2-AI

Documentación de paquetes, compatibilidad y verificación del entorno.

**Última revisión:** 2026-06-14
**Entorno probado:** Windows 10/11, Python 3.13.5, venv en `C:\Users\doski\projectIA\.venv`

---

## Instalación

```bat
```

Verificar que no hay conflictos:

```bat
```

**No uses `pytest` a secas** si el intérprete activo es el Python del sistema
(`AppData\Local\Programs\Python\...`). Las dependencias están solo en `..\.venv`. Usa `tests.bat` o
el Python del venv.

Documentación de entrenamiento y logs: [ENTRENAMIENTO.md](ENTRENAMIENTO.md)

---

## Stack verificado (2026-06-14)

| Paquete           | Versión instalada | Estado |
| ----------------- | ----------------- | ------ |
| Python            | 3.13.5            | OK     |
| numpy             | 2.4.4             | OK     |
| gymnasium         | 1.2.3             | OK     |
| stable-baselines3 | 2.8.0             | OK     |
| torch             | 2.11.0+cpu        | OK     |
| vgamepad          | 0.1.0             | OK     |
| rich              | 15.0.0            | OK     |
| tensorboard       | 2.20.0            | OK     |
| pytest            | 9.0.3             | OK     |

- `pip check`: sin conflictos
- `pytest tests`: **41 passed**

---

## Paquetes y uso en el proyecto

| Paquete               | Módulo Python       | Archivos que lo usan            | Función                                      |
| --------------------- | ------------------- | ------------------------------- | -------------------------------------------- |
| **numpy**             | `numpy`             | `environment.py`, `pretrain.py` | Observaciones, rewards, tensores de pretrain |
| **gymnasium**         | `gymnasium`         | `environment.py`                | API del entorno (`PCARS2Env`)                |
| **stable-baselines3** | `stable_baselines3` | `main.py`                       | PPO, `VecNormalize`, callbacks, checkpoints  |
| **torch**             | `torch`             | `main.py`, `pretrain.py`        | Backend de SB3; pretrain del actor           |
| **vgamepad**          | `vgamepad`          | `controller.py`                 | Mando virtual (Xbox/DS4) hacia el juego      |
| **rich**              | `rich`              | `monitor.py`                    | Dashboard en consola                         |
| **tensorboard**       | `tensorboard`       | `main.py`, `tensorboard.bat`    | Logs de entrenamiento (opcional)             |
| **pytest**            | `pytest`            | `tests/`                        | Suite de tests sin hardware                  |

### Dependencias transitivas relevantes (no listadas en `requirements.txt`)

Instaladas automáticamente por SB3/torch:

| Paquete                 | Origen      | Notas                       |
| ----------------------- | ----------- | --------------------------- |
| cloudpickle             | SB3         | Serialización de modelos    |
| protobuf, grpcio        | TensorBoard | Servidor de logs            |
| sympy, networkx, jinja2 | PyTorch     | Solo build/runtime de torch |
| colorama                | pytest/rich | Colores en terminal Windows |

**No usadas por el código:** `pandas`, `matplotlib`, `shimmy`. SB3 2.8+ ya no exige
pandas/matplotlib como dependencias core.

---

## Matriz de compatibilidad

### Python

| Versión         | Soporte                                                                    |
| --------------- | -------------------------------------------------------------------------- |
| **3.10 – 3.13** | Recomendado. Probado en **3.13.5**.                                        |
| 3.9             | SB3 ≥2.7.1 fue el último con soporte 3.9; no usar en instalaciones nuevas. |
| &lt;3.10        | No compatible con SB3 2.8+.                                                |

### stable-baselines3 2.8.x

Requisitos oficiales (aprox.):

| Dependencia | Rango SB3 2.8    | Rango en `requirements.txt` |
| ----------- | ---------------- | --------------------------- |
| gymnasium   | ≥0.29.1, &lt;2.0 | `>=0.29.1,<2.0`             |
| numpy       | ≥1.20, &lt;3.0   | `>=1.24.0,<3.0`             |
| torch       | ≥2.8, &lt;3.0    | `>=2.8.0,<3.0`              |

### Cambios respecto al `requirements.txt` anterior

| Antes                      | Ahora                 | Motivo                                                         |
| -------------------------- | --------------------- | -------------------------------------------------------------- |
| `stable-baselines3>=2.0.0` | `>=2.8.0,<3.0`        | SB3 2.8 exige torch≥2.8 y gymnasium 1.x                        |
| `torch>=2.0.0`             | `>=2.8.0,<3.0`        | Mínimo real impuesto por SB3 2.8 (seguridad + API)             |
| `gymnasium>=0.29.0`        | `>=0.29.1,<2.0`       | Alineado con SB3; evita gymnasium 2.x hasta que SB3 lo soporte |
| `numpy>=1.24.0`            | `>=1.24.0,<3.0`       | Tope &lt;3.0 exigido por SB3                                   |
| *(ausente)*                | `tensorboard>=2.14.0` | Usado en `main.py` y `tensorboard.bat`                         |
| Sin documentación          | Este archivo          | Trazabilidad de versiones                                      |

### SB3 2.9.0 (PyPI, abril 2026)

Disponible pero **no probado** en este proyecto. El stack actual con **2.8.0** funciona. Si se
actualiza a 2.9:

1. `pip install "stable-baselines3>=2.9.0,<3.0"`
2. `pip check`
3. `pytest tests -q`
4. Probar carga de un checkpoint existente (`--model`)

---

## PyTorch: CPU vs CUDA

El venv actual tiene **torch 2.11.0+cpu**. Para GPU NVIDIA:

```bat
```

SB3 funciona igual; el entrenamiento PPO se beneficia de CUDA si hay GPU disponible. El cuello de
botella habitual en PCARS2-AI sigue siendo **esperar al juego** (UDP + frame_skip), no solo la red.

---

## Requisitos de sistema (Windows)

| Componente                       | Necesario para                            |
| -------------------------------- | ----------------------------------------- |
| **ViGEmBus**                     | `vgamepad` — driver del mando virtual     |
| **Project CARS 2**               | Telemetría UDP + control                  |
| **Puerto UDP 5606** (telemetría) | `telemetry_udp.py`                        |
| Permisos de administrador        | A veces necesarios para instalar ViGEmBus |

Sin ViGEmBus, `controller.py` fallará al crear el gamepad virtual.

---

## Comandos de verificación rápida

```bat
```

---

## Resolución de problemas

| Síntoma                                   | Causa probable                      | Acción                                                          |
| ----------------------------------------- | ----------------------------------- | --------------------------------------------------------------- |
| `pip` instala torch antiguo con SB3 nuevo | Orden de instalación                | `pip install -r requirements.txt` de nuevo; torch debe ser ≥2.8 |
| Error al importar `vgamepad`              | ViGEmBus no instalado               | Instalar driver ViGEmBus y reiniciar                            |
| TensorBoard no arranca                    | Paquete no instalado                | `pip install tensorboard` o reinstalar requirements             |
| Tests fallan en imports                   | `src/` no en PYTHONPATH             | Ejecutar desde `PCARS2-AI/` con `pytest.ini` (ya configurado)   |
| Checkpoint no carga tras upgrade SB3      | Cambio de formato raro entre majors | Mantener SB3 2.8.x; probar carga antes de entrenar largo        |

---

## Mantenimiento

Revisar dependencias cuando:

- Se actualice Python del venv
- Falle `pip check` tras un `pip install -U`
- SB3 publique una release mayor (2.x → 3.x)
- Se añadan nuevos imports en `src/`

Tras cualquier cambio en `requirements.txt`, ejecutar siempre `pip check` y `pytest tests -q`, y
actualizar la tabla **Stack verificado** de este documento.
