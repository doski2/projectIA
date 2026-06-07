"""
controller.py
Traduce las decisiones del agente de RL en señales de mando virtual
que Project CARS 2 reconoce como mando Xbox 360 o DualShock 4 (PS4).

Modos disponibles:
  'xbox'  → VX360Gamepad  (por defecto, funciona con Steam Input desactivado)
  'ds4'   → VDS4Gamepad   (útil si Steam Input traduce DS4 → Xbox para PCARS2)

IMPORTANTE — Steam Input:
  Si el juego no recibe inputs, desactiva Steam Input para PCARS2:
  Steam → clic derecho PCARS2 → Propiedades → Controlador → Desactivar Steam Input

Instalación:
    pip install vgamepad

Requisito adicional (Windows):
    ViGEmBus driver — https://github.com/nefarius/ViGEmBus/releases
    Instalar antes de ejecutar cualquier script que use vgamepad.
"""

import vgamepad as vg

# ---------------------------------------------------------------------------
# Rangos de la acción del agente (normalizados)
# ---------------------------------------------------------------------------
# El agente RL trabaja con valores continuos en [-1.0, 1.0]:
#   throttle : 0.0 (sin gas)   → 1.0 (gas fondo)
#   brake    : 0.0 (sin freno) → 1.0 (freno fondo)
#   steering : -1.0 (izq.)    → 1.0 (der.)

# El agente no puede acelerar y frenar a la vez: si throttle > 0, brake = 0
# y viceversa. Esto se aplica en apply_action() antes de enviar al mando.

# ---------------------------------------------------------------------------
# Clase principal
# ---------------------------------------------------------------------------

class DS4Controller:
    """
    Controlador virtual para Project CARS 2. Soporta Xbox 360 y DualShock 4.

    Parámetros:
      mode : 'xbox' (por defecto) o 'ds4'

    Mapeo de ejes:
      Acelerador = RT/R2  |  Freno = LT/L2  |  Volante = joystick izquierdo X

    Uso:
        ctrl = DS4Controller()           # Xbox 360 (por defecto)
        ctrl = DS4Controller(mode='ds4') # DualShock 4
        ctrl.apply_action(throttle=0.8, brake=0.0, steering=0.15)
        ctrl.release()
    """

    def __init__(self, mode: str = 'xbox'):
        self._mode = mode.lower()
        if self._mode == 'ds4':
            self._gamepad = vg.VDS4Gamepad()
            print('[Controller] Modo: DualShock 4 (VDS4Gamepad)')
        else:
            self._gamepad = vg.VX360Gamepad()
            print('[Controller] Modo: Xbox 360 (VX360Gamepad)')
        # Asegurarnos de que el mando empieza en estado neutro
        self.neutral()

    # ------------------------------------------------------------------
    # API principal
    # ------------------------------------------------------------------

    def apply_action(
        self,
        throttle: float,
        brake:    float,
        steering: float,
    ):
        """
        Aplica una acción del agente al mando virtual.

        Parámetros (todos normalizados):
          throttle : [0.0, 1.0]   — acelerador
          brake    : [0.0, 1.0]   — freno
          steering : [-1.0, 1.0]  — volante (negativo = izquierda)

        Lógica de seguridad:
          - Clampea todos los valores a su rango válido.
          - Si throttle > 0 y brake > 0 simultáneamente (situación inusual
            pero posible al inicio del entrenamiento), da prioridad al freno.
            Esto replica el comportamiento real de overlapping de pedales.
        """
        # Clamp
        throttle = max(0.0, min(1.0, float(throttle)))
        brake    = max(0.0, min(1.0, float(brake)))
        steering = max(-1.0, min(1.0, float(steering)))

        # Prioridad al freno cuando ambos activos (arranque errático del agente)
        if brake > 0.05 and throttle > 0.05:
            throttle = 0.0

        # Convertir a rangos del hardware virtual
        # R2 (gas) y L2 (freno): 0–255 en DS4
        r2_val = int(throttle * 255)
        l2_val = int(brake    * 255)

        # Joystick izquierdo horizontal (volante): -32768 a 32767
        steer_val = int(steering * 32767)
        steer_val = max(-32768, min(32767, steer_val))

        if self._mode == 'ds4':
            self._gamepad.right_trigger_float(value_float=throttle)   # R2
            self._gamepad.left_trigger_float(value_float=brake)        # L2
            self._gamepad.left_joystick_float(
                x_value_float=steering,
                y_value_float=0.0,
            )
        else:
            self._gamepad.right_trigger(value=r2_val)   # RT = acelerador
            self._gamepad.left_trigger(value=l2_val)    # LT = freno
            self._gamepad.left_joystick(
                x_value=steer_val,
                y_value=0,
            )
        self._gamepad.update()

    def neutral(self):
        """Devuelve el mando a estado completamente neutro (sin inputs)."""
        if self._mode == 'ds4':
            self._gamepad.right_trigger_float(value_float=0.0)
            self._gamepad.left_trigger_float(value_float=0.0)
            self._gamepad.left_joystick_float(x_value_float=0.0, y_value_float=0.0)
        else:
            self._gamepad.right_trigger(value=0)
            self._gamepad.left_trigger(value=0)
            self._gamepad.left_joystick(x_value=0, y_value=0)
        self._gamepad.update()

    def press_button(self, button: str):
        """
        Pulsa un botón del mando brevemente (útil para menús o reinicio).

        Botones soportados:
          'a', 'b', 'x', 'y', 'lb', 'rb', 'ls', 'rs',
          'start', 'back', 'guide',
          'dpad_up', 'dpad_down', 'dpad_left', 'dpad_right'
        """
        import time

        btn_map = {
            "a":          vg.XUSB_BUTTON.XUSB_GAMEPAD_A,
            "b":          vg.XUSB_BUTTON.XUSB_GAMEPAD_B,
            "x":          vg.XUSB_BUTTON.XUSB_GAMEPAD_X,
            "y":          vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
            "lb":         vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
            "rb":         vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
            "ls":         vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB,
            "rs":         vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB,
            "start":      vg.XUSB_BUTTON.XUSB_GAMEPAD_START,
            "back":       vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK,
            "guide":      vg.XUSB_BUTTON.XUSB_GAMEPAD_GUIDE,
            "dpad_up":    vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
            "dpad_down":  vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
            "dpad_left":  vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
            "dpad_right": vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
        }
        if button not in btn_map:
            raise ValueError(
                f"Botón '{button}' no reconocido. "
                f"Opciones: {list(btn_map.keys())}"
            )
        self._gamepad.press_button(button=btn_map[button])
        self._gamepad.update()
        time.sleep(0.08)
        self._gamepad.release_button(button=btn_map[button])
        self._gamepad.update()

    def release(self):
        """Libera el mando virtual. Llamar al cerrar el entorno."""
        self.neutral()
        # vgamepad libera automáticamente el dispositivo al destruir el objeto
        del self._gamepad

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.release()


# ---------------------------------------------------------------------------
# Mapeo de la acción del agente
# ---------------------------------------------------------------------------

def decode_action(action) -> tuple:
    """
    Convierte el array de acción continua del agente PPO en
    (throttle, brake, steering) normalizados.

    El Action Space de Gymnasium será:
        Box(low=[-1, -1, -1], high=[1, 1, 1], shape=(3,))

    Convención del agente:
        action[0] : acelerador  (tanh → [-1,1], mapeamos [0,1])
        action[1] : freno       (tanh → [-1,1], mapeamos [0,1])
        action[2] : volante     (tanh → [-1,1], directo)
    """
    import numpy as np
    action = np.clip(action, -1.0, 1.0)

    # Convertir de [-1,1] a [0,1] para acelerador y freno
    throttle = (float(action[0]) + 1.0) / 2.0
    brake    = (float(action[1]) + 1.0) / 2.0
    steering =  float(action[2])

    return throttle, brake, steering
