# PCARS2-AI: Referencia de Datos UDP — Project CARS 2

Puerto: `5606` | Protocolo: `SMS_UDP_Definitions.hpp`

---

## Tipos de Paquetes (EUDPStreamerPacketHandlerType)

| ID  | Nombre                              | Frecuencia                   | Enviado cuando                 |
| --- | ----------------------------------- | ---------------------------- | ------------------------------ |
| 0   | `eCarPhysics` (sTelemetryData)      | Cada tick UDP (configurable) | En carrera                     |
| 1   | `eRaceDefinition` (sRaceData)       | Decremento logarítmico       | Al entrar en carrera / cambios |
| 2   | `eParticipants` (sParticipantsData) | Decremento logarítmico       | Al entrar en carrera / cambios |
| 3   | `eTimings` (sTimingsData)           | Cada tick UDP                | En carrera                     |
| 4   | `eGameState` (sGameStateData)       | Cada 5s menú / 10s carrera   | Siempre                        |
| 5   | `eWeatherState`                     | —                            | **NO se envía actualmente**    |
| 6   | `eVehicleNames`                     | —                            | **NO se envía actualmente**    |
| 7   | `eTimeStats` (sTimeStatsData)       | Al cruzar sectores           | En carrera                     |
| 8   | `eParticipantVehicleNames`          | Decremento logarítmico       | Al entrar en carrera           |

---

## Paquete 0 — `sTelemetryData` (CarPhysics) — 556 bytes

El más importante. Contiene toda la física del coche del participante observado.

### Posición y Movimiento

| Campo                   | Tipo     | Descripción                                                    |
| ----------------------- | -------- | -------------------------------------------------------------- |
| `sFullPosition[3]`      | float[3] | **Posición XYZ de alta precisión** (clave para grabar trazado) |
| `sOrientation[3]`       | float[3] | Rotación del coche (roll, pitch, yaw)                          |
| `sLocalVelocity[3]`     | float[3] | Velocidad en ejes locales del coche                            |
| `sWorldVelocity[3]`     | float[3] | Velocidad en ejes del mundo                                    |
| `sAngularVelocity[3]`   | float[3] | Velocidad angular (detectar sobreviraje)                       |
| `sLocalAcceleration[3]` | float[3] | Aceleración en ejes locales                                    |
| `sWorldAcceleration[3]` | float[3] | Aceleración en ejes del mundo                                  |
| `sSpeed`                | float    | **Velocidad escalar del coche (m/s)**                          |
| `sOdometerKM`           | float    | Odómetro total en kilómetros                                   |

### Inputs del Piloto

| Campo                 | Tipo  | Descripción                               |
| --------------------- | ----- | ----------------------------------------- |
| `sUnfilteredThrottle` | uchar | Acelerador sin filtrar (0-255)            |
| `sUnfilteredBrake`    | uchar | Freno sin filtrar (0-255)                 |
| `sUnfilteredSteering` | schar | Volante sin filtrar (-128..127)           |
| `sUnfilteredClutch`   | uchar | Embrague sin filtrar (0-255)              |
| `sThrottle`           | uchar | Acelerador filtrado (señal real al coche) |
| `sBrake`              | uchar | Freno filtrado                            |
| `sSteering`           | schar | Volante filtrado                          |
| `sClutch`             | uchar | Embrague filtrado                         |
| `sGearNumGears`       | uchar | Marcha actual + número total de marchas   |
| `sHandBrake`          | uchar | Freno de mano                             |
| `sBrakeBias`          | uchar | Bias de frenada (cuantizado)              |

### Motor y Combustible

| Campo                 | Tipo   | Descripción                      |
| --------------------- | ------ | -------------------------------- |
| `sRpm`                | ushort | RPM actuales                     |
| `sMaxRpm`             | ushort | RPM máximas                      |
| `sEngineSpeed`        | float  | Velocidad del motor              |
| `sEngineTorque`       | float  | Torque del motor                 |
| `sFuelLevel`          | float  | Nivel de combustible (0.0 - 1.0) |
| `sFuelCapacity`       | uchar  | Capacidad total del depósito     |
| `sFuelPressureKpa`    | ushort | Presión del combustible          |
| `sBoostAmount`        | uchar  | Cantidad de boost                |
| `sTurboBoostPressure` | float  | Presión del turbo                |
| `sOilTempCelsius`     | sshort | Temperatura del aceite           |
| `sOilPressureKPa`     | ushort | Presión del aceite               |
| `sWaterTempCelsius`   | sshort | Temperatura del agua             |
| `sWaterPressureKpa`   | ushort | Presión del agua                 |

### Neumáticos (arrays de 4: FL, FR, RL, RR)

| Campo                       | Tipo      | Descripción                               |
| --------------------------- | --------- | ----------------------------------------- |
| `sTyreTemp[4]`              | uchar[4]  | Temperatura general del neumático         |
| `sTyreTreadTemp[4]`         | ushort[4] | Temperatura de la banda de rodadura       |
| `sTyreLayerTemp[4]`         | ushort[4] | Temperatura de la capa interior           |
| `sTyreCarcassTemp[4]`       | ushort[4] | Temperatura de la carcasa                 |
| `sTyreRimTemp[4]`           | ushort[4] | Temperatura de la llanta                  |
| `sTyreInternalAirTemp[4]`   | ushort[4] | Temperatura del aire interior             |
| `sTyreTempLeft[4]`          | ushort[4] | Temperatura zona izquierda del neumático  |
| `sTyreTempCenter[4]`        | ushort[4] | Temperatura zona central                  |
| `sTyreTempRight[4]`         | ushort[4] | Temperatura zona derecha                  |
| `sTyreWear[4]`              | uchar[4]  | Desgaste del neumático (0-255)            |
| `sTyreRPS[4]`               | float[4]  | Rotaciones por segundo de cada rueda      |
| `sTyreHeightAboveGround[4]` | float[4]  | Altura sobre el suelo (detectar vuelos)   |
| `sTyreFlags[4]`             | uchar[4]  | Flags de estado del neumático             |
| `sTerrain[4]`               | uchar[4]  | Tipo de terreno bajo cada rueda           |
| `sTyreCompound[4][40]`      | char      | Nombre del compuesto (ej: "Soft", "Rain") |
| `sAirPressure[4]`           | ushort[4] | Presión del aire en cada neumático        |

### Suspensión (arrays de 4: FL, FR, RL, RR)

| Campo                      | Tipo      | Descripción                             |
| -------------------------- | --------- | --------------------------------------- |
| `sRideHeight[4]`           | float[4]  | Altura de la carrocería en cada esquina |
| `sSuspensionTravel[4]`     | float[4]  | Recorrido de suspensión actual          |
| `sSuspensionVelocity[4]`   | float[4]  | Velocidad de la suspensión              |
| `sSuspensionRideHeight[4]` | ushort[4] | Ride height cuantizado                  |
| `sWheelLocalPositionY[4]`  | float[4]  | Posición local de cada rueda            |
| `sTyreY[4]`                | float[4]  | Posición Y del neumático                |

### Daños

| Campo                  | Tipo      | Descripción                      |
| ---------------------- | --------- | -------------------------------- |
| `sAeroDamage`          | uchar     | Daño aerodinámico (0-255)        |
| `sEngineDamage`        | uchar     | Daño del motor                   |
| `sBrakeDamage[4]`      | uchar[4]  | Daño de frenos por rueda         |
| `sSuspensionDamage[4]` | uchar[4]  | Daño de suspensión por rueda     |
| `sBrakeTempCelsius[4]` | sshort[4] | Temperatura de frenos en Celsius |

### Estado del Coche

| Campo               | Tipo     | Descripción                                |
| ------------------- | -------- | ------------------------------------------ |
| `sCarFlags`         | uchar    | Flags de estado (en pista, en boxes, etc.) |
| `sCrashState`       | uchar    | Estado de colisión                         |
| `sExtentsCentre[3]` | float[3] | Centro de la caja de colisión              |
| `sWings[2]`         | uchar[2] | Estado de alas (delantero/trasero)         |

---

## Paquete 1 — `sRaceData` (RaceDefinition) — 308 bytes

| Campo                           | Tipo   | Descripción                                   |
| ------------------------------- | ------ | --------------------------------------------- |
| `sTrackLength`                  | float  | **Longitud total del circuito en metros**     |
| `sTrackLocation[64]`            | char   | Nombre del circuito (ej: "Spa-Francorchamps") |
| `sTrackVariation[64]`           | char   | Variante del circuito (ej: "Full Circuit")    |
| `sTranslatedTrackLocation[64]`  | char   | Nombre traducido del circuito                 |
| `sTranslatedTrackVariation[64]` | char   | Variante traducida                            |
| `sWorldFastestLapTime`          | float  | Vuelta rápida mundial                         |
| `sPersonalFastestLapTime`       | float  | Vuelta rápida personal                        |
| `sPersonalFastestSector1Time`   | float  | Sector 1 más rápido personal                  |
| `sPersonalFastestSector2Time`   | float  | Sector 2 más rápido personal                  |
| `sPersonalFastestSector3Time`   | float  | Sector 3 más rápido personal                  |
| `sWorldFastestSector1Time`      | float  | Sector 1 más rápido mundial                   |
| `sWorldFastestSector2Time`      | float  | Sector 2 más rápido mundial                   |
| `sWorldFastestSector3Time`      | float  | Sector 3 más rápido mundial                   |
| `sLapsTimeInEvent`              | ushort | Nº de vueltas (o duración en timed sessions)  |
| `sEnforcedPitStopLap`           | schar  | Vuelta de pit obligatorio (-1 si no aplica)   |

---

## Paquete 2 — `sParticipantsData` — 1136 bytes

| Campo              | Tipo   | Descripción                       |
| ------------------ | ------ | --------------------------------- |
| `sName[16][64]`    | char   | Nombres de hasta 16 participantes |
| `sNationality[16]` | uint   | Nacionalidad de cada participante |
| `sIndex[16]`       | ushort | Índice único de sesión MP         |

---

## Paquete 3 — `sTimingsData` — 1059 bytes

### Por participante (`sParticipantInfo`, hasta 32 participantes)

| Campo                 | Tipo      | Descripción                                       |
| --------------------- | --------- | ------------------------------------------------- |
| `sWorldPosition[3]`   | sshort[3] | Posición cuantizada XYZ en el mundo               |
| `sOrientation[3]`     | sshort[3] | Orientación cuantizada                            |
| `sCurrentLapDistance` | ushort    | **Distancia recorrida en vuelta actual (metros)** |
| `sCurrentLap`         | uchar     | Número de vuelta actual                           |
| `sSector`             | uchar     | Sector actual (1, 2 o 3)                          |
| `sRacePosition`       | uchar     | Posición en carrera                               |
| `sHighestFlag`        | uchar     | Color y motivo de la bandera más alta             |
| `sPitModeSchedule`    | uchar     | Modo pit actual y programado                      |
| `sRaceState`          | uchar     | Flags de estado + indicador de vuelta invalidada  |
| `sCurrentTime`        | float     | Tiempo de vuelta actual                           |
| `sCurrentSectorTime`  | float     | Tiempo del sector actual                          |

### Generales

| Campo                    | Tipo   | Descripción                                 |
| ------------------------ | ------ | ------------------------------------------- |
| `sNumParticipants`       | schar  | Número de participantes activos             |
| `sEventTimeRemaining`    | float  | Tiempo restante (-1 en carrera por vueltas) |
| `sSplitTimeAhead`        | float  | Tiempo al coche de delante                  |
| `sSplitTimeBehind`       | float  | Tiempo al coche de detrás                   |
| `sLocalParticipantIndex` | ushort | Índice del jugador local en MP              |

---

## Paquete 4 — `sGameStateData` — 24 bytes

| Campo                 | Tipo   | Descripción                                    |
| --------------------- | ------ | ---------------------------------------------- |
| `mGameState`          | char   | Estado del juego + estado de sesión (3+3 bits) |
| `mBuildVersionNumber` | ushort | Versión del juego                              |
| `sAmbientTemperature` | schar  | Temperatura ambiente (°C)                      |
| `sTrackTemperature`   | schar  | **Temperatura del asfalto (°C)**               |
| `sRainDensity`        | uchar  | Densidad de lluvia                             |
| `sSnowDensity`        | uchar  | Densidad de nieve                              |
| `sWindSpeed`          | schar  | Velocidad del viento                           |
| `sWindDirectionX`     | schar  | Dirección del viento (eje X)                   |
| `sWindDirectionY`     | schar  | Dirección del viento (eje Y)                   |

---

## Paquete 7 — `sTimeStatsData` — 1040 bytes

Se envía cada vez que un participante cruza un límite de sector.

| Campo                   | Tipo  | Descripción                         |
| ----------------------- | ----- | ----------------------------------- |
| `sFastestLapTime`       | float | Vuelta más rápida del participante  |
| `sLastLapTime`          | float | Última vuelta completada            |
| `sLastSectorTime`       | float | Último sector completado            |
| `sFastestSector1Time`   | float | Sector 1 más rápido                 |
| `sFastestSector2Time`   | float | Sector 2 más rápido                 |
| `sFastestSector3Time`   | float | Sector 3 más rápido                 |
| `sParticipantOnlineRep` | uint  | Reputación online (rank + strength) |

---

## Enums de superficie y flags (shared memory = UDP)

Implementación en código: `PCARS2-AI/src/pcars2_surface.py`.
Origen: shared memory Type#9–11 (véase también
[MacManley/project-cars-2-udp](https://github.com/MacManley/project-cars-2-udp) tabla
TerrainMaterial IDs).

### `sCarFlags` (offset **17**, 1 byte, bitmask)

| Bit | Nombre               | Significado      |
| --- | -------------------- | ---------------- |
| 0   | `CAR_HEADLIGHT`      | Faros            |
| 1   | `CAR_ENGINE_ACTIVE`  | Motor en marcha  |
| 2   | `CAR_ENGINE_WARNING` | Aviso motor      |
| 3   | `CAR_SPEED_LIMITER`  | Limitador activo |
| 4   | `CAR_ABS`            | ABS activo       |
| 5   | `CAR_HANDBRAKE`      | Freno de mano    |

**Nota:** boxes / pit no vienen aquí; usar `sPitModeSchedule` del paquete Timings (futuro).

### `sTyreFlags[4]` (offset **136**)

| Bit | Nombre           |
| --- | ---------------- |
| 0   | `TYRE_ATTACHED`  |
| 1   | `TYRE_INFLATED`  |
| 2   | `TYRE_ON_GROUND` |

Aún **no parseado** en `telemetry_udp.py` (reservado).

### `sTerrain[4]` (offset **140**, enum por rueda FL/FR/RL/RR)

Valores 0–50 (lista completa en repos CREST2 `SharedMemory.h` Type#11). Los más usados en teaching:

| ID  | Material                |
| --- | ----------------------- |
| 0   | `TERRAIN_ROAD`          |
| 1   | `TERRAIN_LOW_GRIP_ROAD` |
| 7   | `TERRAIN_GRASS`         |
| 8   | `TERRAIN_GRAVEL`        |
| 10  | `TERRAIN_RUMBLE_STRIPS` |
| 15  | `TERRAIN_SAND`          |
| 17  | `TERRAIN_DIRT`          |
| 30  | `TERRAIN_SAND_ROAD`     |
| 46  | `TERRAIN_RUNOFF_ROAD`   |
| 47  | `TERRAIN_ILLEGAL_STRIP` |

**Uso en ProjectIA:** `SafetyMonitor` marca `off_surface` si alguna rueda está en terreno fuera de
pista (césped, gravel, etc.) o las cuatro ruedas salen de la lista «racing surface» (estilo
CrewChief), **sin depender solo del CTE** a la referencia.

### Campos útiles aún no parseados (candidatos)

| Campo                          | Offset (paquete 0) | Notas                       |
| ------------------------------ | ------------------ | --------------------------- |
| `sTyreFlags[4]`                | 136                | Contacto rueda/suelo        |
| `sTyreHeightAboveGround[4]`    | 180                | Vuelo / despegue            |
| `sCrashState`                  | 47                 | Colisión                    |
| Paquete **4** `sGameStateData` | —                  | Temp. pista, lluvia, viento |

`sTyreGrip` / `sTyreSlipSpeed`: marcados **OBSOLETE** en headers recientes de SMS; preferir
`sTyreRPS` + aceleraciones.

---

## Lo que NO está disponible por UDP

| Dato                                        | Razón                          | Alternativa                            |
| ------------------------------------------- | ------------------------------ | -------------------------------------- |
| **Línea de trazado (verde/rojo/ámbar)**     | Efecto visual solo en pantalla | Captura OpenCV o grabar trazado propio |
| **Posición exacta de los límites de pista** | No exportado                   | Derivar de posiciones históricas       |
| **Mapa del circuito**                       | No exportado                   | Reconstruir desde `sFullPosition`      |

---

## Datos Derivados Útiles (calculados, no directos)

| Dato derivado                            | Cómo calcularlo                                            | Datos necesarios                        |
| ---------------------------------------- | ---------------------------------------------------------- | --------------------------------------- |
| **Ángulo de deslizamiento (slip angle)** | `atan2(localVel.z, localVel.x)`                            | `sLocalVelocity[3]`                     |
| **Sobreviraje / Subviraje**              | Diferencia entre heading y dirección de velocidad          | `sOrientation` + `sWorldVelocity`       |
| **Cross-Track Error**                    | Distancia del coche a la línea de referencia grabada       | `sFullPosition` + referencia            |
| **Velocidad ideal en punto X**           | Extraer de vuelta de referencia grabada                    | `sSpeed` + `sCurrentLapDistance`        |
| **Grip disponible**                      | Correlacionar aceleración lateral vs temp. neumático       | `sLocalAcceleration` + `sTyreTreadTemp` |
| **Mapa del circuito**                    | Acumular `sFullPosition` a lo largo de una vuelta completa | `sFullPosition` + `sCurrentLapDistance` |

---

## Estrategia: Grabar Línea de Referencia

```python
```

Esto permite:

- Calcular **Cross-Track Error** comparando posición del agente vs referencia
- Saber la **velocidad mínima aceptable** en cada punto (si va más lento → penalizar)
- Detectar **puntos de frenada** (`brake > 0` en referencia)
- Generar **reward shaping** basado en similitud con el piloto de referencia

---

## Notas de Implementación

- El byte de marcha `sGearNumGears`: bits 0-3 = marcha actual, bits 4-7 = número total de marchas
- `sRacePosition`: bit 7 indica si el participante está activo
- `sSector`: bits 0-1 = sector (1/2/3), bits 2-7 = bits extra de precisión para posición XZ
- `sHighestFlag`: bits 0-2 = color de bandera, bits 3-4 = motivo
- `sCarFlags`: contiene flags como si está en boxes, si el motor está encendido, etc.
- Coordenadas `sFullPosition` están en el sistema de coordenadas del mundo del juego (metros)
