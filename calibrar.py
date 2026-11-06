"""
CALIBRAR EL RIESGO PARA EL OBJETIVO DE RENDIMIENTO (v2.3)

La ventaja de Rogelio (ganancia por operación en R) no cambia con el riesgo:
lo que cambia es cuánto se gana Y cuánto se cae la cuenta. Este programa prueba
varias escalas de riesgo sobre las MISMAS operaciones del último backtest y busca
la menor escala que alcanza el objetivo anual sin pasar la caída máxima tolerada.

Uso (después de correr rogelio.py, que deja reportes/candidatas.csv):
    python calibrar.py
"""
import os
import warnings
import numpy as np
import pandas as pd
import config as C
from cartera import backtest_cartera
from metricas import metricas_cartera, montecarlo

warnings.filterwarnings("ignore")
pd.set_option("display.width", 220)
ESCALAS = [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5]


def cagr_periodo(curva, desde=None, hasta=None):
    diaria = curva.set_index("fecha")["capital"].resample("1D").last().ffill()
    if desde is not None:
        diaria = diaria[diaria.index >= desde]
    if hasta is not None:
        diaria = diaria[diaria.index < hasta]
    if len(diaria) < 30:
        return np.nan
    anios = (diaria.index[-1] - diaria.index[0]).days / 365.25
    return (diaria.iloc[-1] / diaria.iloc[0]) ** (1 / anios) - 1


if __name__ == "__main__":
    ruta = os.path.join(C.CARPETA_REPORTES, "candidatas.csv")
    if not os.path.exists(ruta):
        raise SystemExit("Primero corré: python rogelio.py")
    cand = pd.read_csv(ruta)
    for col in ("fecha_entrada", "fecha_salida"):
        cand[col] = pd.to_datetime(cand[col], utc=True, format="mixed")
    activas = [n for n, cfg in C.ESTRATEGIAS.items() if cfg["activa"]]
    cand = cand[cand["estrategia"].isin(activas)]
    inicio = cand["fecha_entrada"].min() + pd.DateOffset(months=C.MESES_ENTRENAMIENTO_MIN)
    periodo = cand[cand["fecha_entrada"] >= inicio]
    corte = pd.Timestamp(C.FECHA_CORTE_VALIDACION, tz="UTC")

    print(f"Estrategias activas: {activas}")
    print(f"Objetivo: {C.OBJETIVO_ANUAL:.0%} anual con caída máxima de hasta {C.CAIDA_MAXIMA_TOLERADA:.0%}\n")
    filas = []
    for e in ESCALAS:
        tabla, curva, _, _, _ = backtest_cartera(periodo, escala=e)
        m, _, _ = metricas_cartera(curva)
        mc = montecarlo(tabla["R"], tabla["riesgo_pct"])
        filas.append({
            "escala": e,
            "riesgo_medio": tabla["riesgo_pct"].mean(),
            "CAGR": m["CAGR"],
            "CAGR_antes_2024": cagr_periodo(curva, hasta=corte),
            "CAGR_desde_2024": cagr_periodo(curva, desde=corte),
            "caida_maxima": m["drawdown_maximo"],
            "sharpe": m["sharpe_anual"],
            "MC_caida_p95": mc.get("drawdown_percentil_95", np.nan),
            "MC_P(corte)": [v for k, v in mc.items() if k.startswith("P(drawdown")][0] if mc else np.nan,
        })
        print(f"  escala {e:.2f}: CAGR {m['CAGR']:.1%}, caída máxima {m['drawdown_maximo']:.1%}")

    t = pd.DataFrame(filas)
    fmt = {c: "{:.1%}".format for c in t.columns if c not in ("escala", "sharpe")}
    fmt.update({"escala": "{:.2f}".format, "sharpe": "{:.2f}".format, "riesgo_medio": "{:.2%}".format})
    print("\n================ CALIBRACIÓN ================")
    print(t.to_string(index=False, formatters=fmt))

    ok = t[(t["CAGR"] >= C.OBJETIVO_ANUAL) & (t["caida_maxima"] >= -C.CAIDA_MAXIMA_TOLERADA)]
    seguras = t[t["caida_maxima"] >= -C.CAIDA_MAXIMA_TOLERADA]
    print()
    if len(ok):
        elegida = ok.iloc[0]
        print(f"RECOMENDACIÓN: ESCALA_RIESGO = {elegida['escala']:.2f} en config.py")
        print(f"  -> {elegida['CAGR']:.1%} anual con caída máxima de {elegida['caida_maxima']:.1%} "
              f"(riesgo medio por operación {elegida['riesgo_medio']:.2%})")
    elif len(seguras):
        elegida = seguras.iloc[-1]
        print(f"El objetivo de {C.OBJETIVO_ANUAL:.0%} NO se alcanza sin pasar la caída de "
              f"{C.CAIDA_MAXIMA_TOLERADA:.0%}.")
        print(f"La mejor opción segura es ESCALA_RIESGO = {elegida['escala']:.2f}: "
              f"{elegida['CAGR']:.1%} anual, caída {elegida['caida_maxima']:.1%}.")
        print("Para llegar al objetivo hacen falta más ventaja (nuevas estrategias) o aceptar más caída.")
    else:
        print("Ninguna escala respeta la caída máxima tolerada: revisá la estrategia antes de operar.")
    print("\nIMPORTANTE: elegir la escala mirando el backtest también es una forma de ajuste al pasado.")
    print("En vivo, el rendimiento suele ser menor. Por eso el testnet es el paso siguiente.")
