"""
BUCLE DE FEEDBACK
Analiza el registro de operaciones (del backtest o, más adelante, de las reales)
y responde: ¿qué funciona, qué no, y si la estrategia se está deteriorando?

Uso:  python feedback.py                          (usa reportes/operaciones.csv)
      python feedback.py otro_registro.csv
"""
import os
import sys
import numpy as np
import pandas as pd
from scipy import stats
import config as C
from metricas import desglose, metricas_operaciones, formatear

pd.set_option("display.width", 200)


def analizar_salidas(t):
    """MAE/MFE: cuánto fue en contra y a favor cada operación antes de cerrarse."""
    perdedoras, ganadoras = t[t["R"] <= 0], t[t["R"] > 0]
    obs = {
        "perdedoras que estuvieron +1R a favor": (perdedoras["mfe_R"] >= 1).mean(),
        "perdedoras que estuvieron +0.5R a favor": (perdedoras["mfe_R"] >= 0.5).mean(),
        "ganadoras que estuvieron -0.7R en contra": (ganadoras["mae_R"] <= -0.7).mean(),
        "MFE medio de las perdedoras (R)": perdedoras["mfe_R"].mean(),
        "MAE medio de las ganadoras (R)": ganadoras["mae_R"].mean(),
    }
    return obs


def calibracion(t):
    """¿Cuando el modelo dice 60%, se gana el 60% de las veces?"""
    if "p_modelo" not in t or t["p_modelo"].isna().all():
        return None
    d = t.dropna(subset=["p_modelo"]).copy()
    d["tramo"] = pd.cut(d["p_modelo"], [0, 0.35, 0.45, 0.55, 0.65, 1])
    return d.groupby("tramo", observed=True).agg(
        operaciones=("R", "size"), p_predicha=("p_modelo", "mean"),
        win_rate_real=("R", lambda x: (x > 0).mean()), expectativa_R=("R", "mean"))


def detectar_degradacion(t, ventana=C.VENTANA_DEGRADACION):
    """Compara las últimas operaciones con el historial. Incluye un CUSUM:
    una suma acumulada que se dispara cuando los resultados se desvían hacia abajo."""
    R = t.sort_values("fecha_entrada")["R"].to_numpy()
    if len(R) < ventana * 2:
        return {"aviso": "pocas operaciones para evaluar degradación"}
    historico, reciente = R[:-ventana], R[-ventana:]
    t_stat, p = stats.ttest_ind(reciente, historico, equal_var=False, alternative="less")
    mu, sd = historico.mean(), historico.std()
    cusum, alarma = 0.0, False
    for r in reciente:
        cusum = min(0.0, cusum + (r - mu) / sd + 0.5)    # 0,5 = tolerancia
        alarma |= cusum < -5
    return {
        "expectativa_historica_R": mu, "expectativa_reciente_R": reciente.mean(),
        "p_valor(reciente peor)": p, "alarma_CUSUM": alarma,
    }


def recomendaciones(t, salidas, degr):
    rec = []
    col = "estrategia" if "estrategia" in t else "setup"
    for nombre, fila in desglose(t, col).iterrows():
        if fila["operaciones"] >= 30 and fila["expectativa_R"] < 0:
            rec.append(f"La estrategia '{nombre}' pierde en promedio ({fila['expectativa_R']:+.2f}R en "
                       f"{fila['operaciones']:.0f} ops): considerar pausarla (\"activa\": False en config.ESTRATEGIAS).")
    for moneda, fila in desglose(t, "moneda").iterrows():
        if fila["operaciones"] >= 20 and fila["expectativa_R"] < -0.15:
            rec.append(f"{moneda} tiene expectativa negativa ({fila['expectativa_R']:+.2f}R): candidata a salir del universo operativo.")
    if salidas["perdedoras que estuvieron +1R a favor"] > 0.25:
        rec.append("Más del 25% de las perdedoras llegó a +1R antes de perder: probar una toma parcial más temprana "
                   "(bajar 'parcial' en config.ESTRATEGIAS) o mover a break-even antes ('break_even_R').")
    if salidas["ganadoras que estuvieron -0.7R en contra"] < 0.10:
        rec.append("Casi ninguna ganadora estuvo cerca del stop: el stop podría ajustarse un poco (config.STOP_MIN_ATR) "
                   "para mejorar la relación b.")
    for nombre, d in degr.items():
        if isinstance(d, dict) and (d.get("alarma_CUSUM") or d.get("p_valor(reciente peor)", 1) < 0.05):
            rec.append(f"ALERTA en '{nombre}': su rendimiento reciente es significativamente peor que su historial. "
                       "Reducir su riesgo o pausarla, y revisar si cambió el régimen de mercado.")
    return rec or ["Sin alertas: los resultados son consistentes con el historial."]


def informe(t):
    print("\n================ FEEDBACK DE ROGELIO ================\n")
    print("Estadística general:")
    print(formatear(metricas_operaciones(t["R"], t["fecha_entrada"])))
    for col in ("estrategia", "lado", "regimen", "motivo_salida", "moneda"):
        if col in t:
            print(f"\nPor {col}:")
            print(desglose(t, col).to_string(float_format=lambda x: f"{x:.3f}"))
    salidas = analizar_salidas(t)
    print("\nAnálisis de salidas (MAE / MFE):")
    print(formatear(salidas))
    cal = calibracion(t)
    if cal is not None:
        print("\nCalibración del modelo (¿las probabilidades se cumplen?):")
        print(cal.to_string(float_format=lambda x: f"{x:.3f}"))
    # Degradación POR ESTRATEGIA: cada una se compara con su propio historial
    grupos = t.groupby("estrategia") if "estrategia" in t else [("todas", t)]
    degr = {}
    print("\nDegradación (cada estrategia contra su propio historial):")
    for nombre, g in grupos:
        degr[nombre] = detectar_degradacion(g)
        print(f"  [{nombre}]")
        print(formatear(degr[nombre]) if "aviso" not in degr[nombre] else "    " + degr[nombre]["aviso"])
    print("\nRECOMENDACIONES:")
    for r in recomendaciones(t, salidas, degr):
        print("  - " + r)


if __name__ == "__main__":
    ruta = sys.argv[1] if len(sys.argv) > 1 else os.path.join(C.CARPETA_REPORTES, "operaciones.csv")
    tabla = pd.read_csv(ruta, parse_dates=["fecha_entrada", "fecha_salida"])
    informe(tabla)
