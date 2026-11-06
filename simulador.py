"""
SIMULADOR DE OPERACIONES
Recorre vela por vela cada señal y calcula su resultado en "R"
(R = múltiplos del riesgo: +2R significa ganar el doble de lo arriesgado).

Medir en R tiene una ventaja enorme: el resultado no depende del tamaño de la
posición, así que la misma simulación sirve para entrenar el modelo y para el
backtest de cartera con cualquier gestión de riesgo.

Supuestos conservadores (para no engañarnos):
  - Entrada en la apertura de la vela siguiente a la señal, con deslizamiento.
  - Si en una misma vela se tocan el stop y el objetivo, se asume que tocó primero el STOP.
  - Los ajustes del stop (break-even, trailing) rigen desde la vela siguiente.
  - Se descuentan comisiones, deslizamiento y funding.
"""
import numpy as np
import pandas as pd
import config as C


def simular_operacion(arr, t, lado, stop, objetivo, p):
    """arr: diccionario de arrays numpy. t: índice de la vela de la señal.
    p: parámetros de salida de la estrategia (config.ESTRATEGIAS[...])."""
    largo = len(arr["apertura"])
    e = t + 1
    if e >= largo:
        return None

    entrada = arr["apertura"][e] * (1 + lado * C.DESLIZAMIENTO)
    riesgo = lado * (entrada - stop)
    if riesgo <= 0 or lado * (objetivo - entrada) <= 0:     # hueco de precio: la señal ya no vale
        return None

    costo_unitario = entrada / riesgo                        # convierte % de precio a R
    costos_R = C.COMISION_TAKER * costo_unitario             # comisión de entrada
    usa_parcial = p["parcial"] is not None and p["cierre_parcial"] > 0
    precio_parcial = entrada + (p["parcial"] or 1.0) * (objetivo - entrada)

    restante, resultado_R = 1.0, 0.0
    parcial_hecho = False
    break_even_hecho = False
    stop_actual = stop
    extremo = entrada                                        # máximo (long) o mínimo (short) alcanzado
    mae, mfe = 0.0, 0.0
    motivo, salida = "datos_insuficientes", largo - 1

    for j in range(e, min(e + p["max_velas"], largo)):
        h, l, cierre = arr["maximo"][j], arr["minimo"][j], arr["cierre"][j]
        favorable = h if lado == 1 else l
        adverso = l if lado == 1 else h
        mae = min(mae, lado * (adverso - entrada) / riesgo)
        mfe = max(mfe, lado * (favorable - entrada) / riesgo)

        # funding (cada vela de 4h es media ventana de 8h)
        costos_R += lado * arr["funding"][j] * 0.5 * costo_unitario * restante

        # 1) ¿tocó el stop? (se revisa primero: supuesto conservador)
        if lado * (adverso - stop_actual) <= 0:
            # si la vela abrió ya más allá del stop (hueco), se sale a la apertura: peor precio
            base = arr["apertura"][j] if lado * (arr["apertura"][j] - stop_actual) < 0 else stop_actual
            precio = base * (1 - lado * C.DESLIZAMIENTO)
            resultado_R += restante * lado * (precio - entrada) / riesgo
            costos_R += restante * C.COMISION_TAKER * costo_unitario
            if stop_actual == entrada:
                motivo = "break_even"
            else:
                motivo = "trailing" if (parcial_hecho or break_even_hecho) else "stop"
            restante, salida = 0.0, j
            break

        # 2) ¿llegó a la toma parcial?
        nuevo_stop = stop_actual
        if usa_parcial and not parcial_hecho and lado * (favorable - precio_parcial) >= 0:
            fraccion = p["cierre_parcial"]
            resultado_R += fraccion * lado * (precio_parcial - entrada) / riesgo
            costos_R += fraccion * C.COMISION_MAKER * costo_unitario
            restante -= fraccion
            parcial_hecho = True
            if restante <= 1e-9:
                motivo, salida = "objetivo", j
                break
            if C.MOVER_STOP_A_ENTRADA:
                nuevo_stop = entrada

        # 2b) break-even: al alcanzar +X R a favor, el stop pasa a la entrada (desde la vela siguiente)
        if p["break_even_R"] and not break_even_hecho and mfe >= p["break_even_R"]:
            nuevo_stop = max(nuevo_stop, entrada) if lado == 1 else min(nuevo_stop, entrada)
            break_even_hecho = True

        # 3) trailing para lo que queda, desde la vela siguiente
        extremo = max(extremo, h) if lado == 1 else min(extremo, l)
        # (con toma parcial, el trailing arranca después de la parcial; sin parcial, después del break-even)
        if parcial_hecho or (not usa_parcial and break_even_hecho):
            trailing = extremo - lado * p["trailing_atr"] * arr["atr"][j]
            nuevo_stop = max(nuevo_stop, trailing) if lado == 1 else min(nuevo_stop, trailing)
        stop_actual = nuevo_stop
        salida = j
    else:
        # 4) cierre por tiempo (o fin de datos)
        if restante > 0:
            precio = arr["cierre"][salida] * (1 - lado * C.DESLIZAMIENTO)
            resultado_R += restante * lado * (precio - entrada) / riesgo
            costos_R += restante * C.COMISION_TAKER * costo_unitario
            motivo = "tiempo" if salida - e + 1 >= p["max_velas"] else "datos_insuficientes"

    return {
        "idx_senal": t, "idx_salida": salida,
        "fecha_entrada": arr["fecha"][e], "fecha_salida": arr["fecha"][salida],
        "precio_entrada": entrada, "stop_inicial": stop, "objetivo": objetivo,
        "dist_stop_pct": riesgo / entrada,
        "R_bruto": resultado_R, "costos_R": costos_R, "R": resultado_R - costos_R,
        "mae_R": mae, "mfe_R": mfe, "velas": salida - e + 1,
        "motivo_salida": motivo, "completa": motivo != "datos_insuficientes",
    }


def simular_senales(df, senales, moneda):
    """Simula todas las señales de una moneda (de cualquier estrategia).
    Devuelve una tabla de operaciones candidatas."""
    columnas = ["apertura", "maximo", "minimo", "cierre", "atr", "funding"]
    arr = {k: df[k].to_numpy(dtype=float) for k in columnas}
    arr["fecha"] = df["fecha"].to_numpy()
    filas = []
    for s in senales.itertuples(index=False):
        p = C.ESTRATEGIAS[s.estrategia]
        res = simular_operacion(arr, int(s.idx_senal), int(s.lado), s.stop_plan, s.objetivo_plan, p)
        if res:
            res.update({"moneda": moneda, "lado": int(s.lado), "estrategia": s.estrategia,
                        "setup": s.setup, "rr_plan": s.rr_plan})
            filas.append(res)
    return pd.DataFrame(filas)
