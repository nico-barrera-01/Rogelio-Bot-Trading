"""
GRÁFICOS
  python graficos.py BTC 60     -> velas japonesas de BTC, últimos 60 días, con estructura y señales
  (la curva de capital la genera rogelio.py en la carpeta reportes)
"""
import os
import sys
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf
import config as C
from indicadores import cargar
from estructura import agregar_estructura
from senales import agregar_contexto, generar_senales


def preparar(moneda):
    ref = cargar(C.MONEDA_REFERENCIA)
    df = agregar_estructura(cargar(moneda))
    df = agregar_contexto(df, ref)
    df, _ = generar_senales(df)
    return df


def grafico_velas(df, moneda, dias=60, guardar=None):
    graf = df.tail(dias * C.VELAS_POR_DIA).set_index("fecha").rename(columns={
        "apertura": "Open", "maximo": "High", "minimo": "Low", "cierre": "Close", "volumen": "Volume"})
    m = graf["atr"] * 0.6
    extras = [mpf.make_addplot(graf["ema50"], color="orange", width=1),
              mpf.make_addplot(graf["ema200"], color="blue", width=1)]
    capas = {
        "swing high": (graf["High"].where(graf["swing_high"]) + m, "v", "red", 25),
        "swing low": (graf["Low"].where(graf["swing_low"]) - m, "^", "green", 25),
        "compra": (graf["Low"].where(graf["senal"] == 1) - 2 * m, "^", "lime", 120),
        "venta": (graf["High"].where(graf["senal"] == -1) + 2 * m, "v", "magenta", 120),
    }
    for serie, marca, color, tam in capas.values():
        if serie.notna().any():
            extras.append(mpf.make_addplot(serie, type="scatter", marker=marca, color=color, markersize=tam))

    niveles = df.attrs.get("niveles_actuales", [])
    precio = graf["Close"].iloc[-1]
    visibles = [n for n in sorted(niveles, key=lambda x: -x[2])[:8]
                if graf["Low"].min() <= n[0] <= graf["High"].max()]
    args = dict(type="candle", style="charles", volume=True, addplot=extras, figsize=(15, 8),
                title=f"{moneda}/USDT {C.TEMPORALIDAD} - estructura y señales (últimos {dias} días)")
    if visibles:
        args["hlines"] = dict(hlines=[n[0] for n in visibles],
                              colors=["green" if n[0] < precio else "red" for n in visibles],
                              linewidths=[min(0.6 + n[2] / 3, 3) for n in visibles],
                              linestyle="--", alpha=0.6)
    if guardar:
        args["savefig"] = guardar
    mpf.plot(graf, **args)


def grafico_capital(curva_con, curva_sin, diaria_dd, guardar, tabla=None):
    fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(13, 10), sharex=True,
                                     gridspec_kw={"height_ratios": [3, 2, 1]})
    a1.plot(curva_con["fecha"], curva_con["capital"], label="Con modelos predictivos", color="navy")
    if curva_sin is not None:
        a1.plot(curva_sin["fecha"], curva_sin["capital"], label="Solo reglas", color="gray", alpha=0.7)
    a1.axhline(C.CAPITAL_INICIAL, color="black", linewidth=0.6, linestyle=":")
    a1.set_ylabel("Capital (USDT)")
    a1.set_title("Rogelio v2.6 (40 monedas) - curva de capital del backtest")
    a1.legend()
    a1.grid(alpha=0.3)
    if tabla is not None and len(tabla):
        colores = {"vendedor": "crimson", "comprador": "seagreen", "batacazo": "darkorange"}
        for nombre, g in tabla.sort_values("fecha_salida").groupby("estrategia"):
            a2.plot(g["fecha_salida"], g["pnl"].cumsum(), label=nombre, color=colores.get(nombre))
        a2.axhline(0, color="black", linewidth=0.6)
        a2.set_ylabel("Ganancia acumulada\npor estrategia (USDT)")
        a2.legend()
        a2.grid(alpha=0.3)
    a3.fill_between(diaria_dd.index, diaria_dd.values * 100, 0, color="crimson", alpha=0.5)
    a3.axhline(-C.DRAWDOWN_CORTE * 100, color="black", linestyle="--", linewidth=0.8)
    a3.set_ylabel("Drawdown %")
    a3.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(guardar, dpi=110)
    plt.close()


def grafico_distribucion(tabla, guardar):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5))
    a1.hist(tabla["R"], bins=40, color="steelblue", edgecolor="white")
    a1.axvline(0, color="black")
    a1.axvline(tabla["R"].mean(), color="red", linestyle="--", label=f"expectativa {tabla['R'].mean():+.2f}R")
    a1.set_title("Distribución de resultados (R)")
    a1.legend()
    colores = ["green" if r > 0 else "red" for r in tabla["R"]]
    a2.scatter(tabla["mae_R"], tabla["mfe_R"], c=colores, s=8, alpha=0.5)
    a2.set_xlabel("MAE: máximo en contra (R)")
    a2.set_ylabel("MFE: máximo a favor (R)")
    a2.set_title("Recorrido de cada operación (verde gana, rojo pierde)")
    for a in (a1, a2):
        a.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(guardar, dpi=110)
    plt.close()


if __name__ == "__main__":
    moneda = sys.argv[1].upper() if len(sys.argv) > 1 else "BTC"
    dias = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    grafico_velas(preparar(moneda), moneda, dias)
