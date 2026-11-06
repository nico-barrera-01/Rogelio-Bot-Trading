"""
ROGELIO v2.5 - MOTOR DE FACTORES + CUENTA COMBINADA

Pasos:
  1. Arma el panel diario de las 20 monedas (precios y funding).
  2. Prueba cada factor (carry y momentum) en sus dos sesgos (bajista y neutral),
     antes y después de 2024, con exposición fija (sin apalancar): ¿hay ventaja?
  3. Arma el motor con la configuración elegida en config.py y le aplica el objetivo de volatilidad.
  4. Lo combina con el motor de rupturas (v2), si existe reportes/operaciones.csv
     (correr antes: python rogelio.py).
  5. Calibra la volatilidad objetivo: ¿qué nivel llega al 25% anual sin pasar la caída tolerada?

Uso:  python v25.py
"""
import os
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import config as C
from factores import panel_diario, carteras_objetivo
from motor_factores import simular_factor, objetivo_volatilidad

warnings.filterwarnings("ignore")
pd.set_option("display.width", 220)
CORTE = pd.Timestamp(C.FECHA_CORTE_VALIDACION, tz="UTC")
VOLS_A_PROBAR = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35]


# ---------------- estadística de series diarias ----------------
def estadisticas(rend):
    rend = rend.dropna()
    rend = rend[rend.ne(0).cumsum() > 0]            # desde el primer día con actividad
    if len(rend) < 60:
        return dict(CAGR=np.nan, vol=np.nan, sharpe=np.nan, caida_max=np.nan, t_mensual=np.nan)
    curva = (1 + rend).cumprod()
    anios = len(rend) / 365.25
    mensual = (1 + rend).resample("ME").prod() - 1
    return dict(
        CAGR=curva.iloc[-1] ** (1 / anios) - 1,
        vol=rend.std() * np.sqrt(365),
        sharpe=rend.mean() / rend.std() * np.sqrt(365) if rend.std() > 0 else np.nan,
        caida_max=(curva / curva.cummax() - 1).min(),
        t_mensual=mensual.mean() / mensual.std() * np.sqrt(len(mensual)) if mensual.std() > 0 else np.nan,
    )


def antes_despues(rend):
    a, d = estadisticas(rend[rend.index < CORTE]), estadisticas(rend[rend.index >= CORTE])
    fila = {f"{k}_antes": v for k, v in a.items()}
    fila.update({f"{k}_despues": v for k, v in d.items()})
    return fila


def prob_caida(rend, limite, sims=3000):
    """Monte Carlo por bloques de un mes: probabilidad de una caída mayor al límite en el período."""
    mensual = ((1 + rend.dropna()).resample("ME").prod() - 1).to_numpy()
    if len(mensual) < 12:
        return np.nan
    rng = np.random.default_rng(3)
    muestras = rng.choice(mensual, size=(sims, len(mensual)))
    curvas = np.cumprod(1 + muestras, axis=1)
    caidas = (curvas / np.maximum.accumulate(curvas, axis=1) - 1).min(axis=1)
    return (caidas <= -limite).mean()


def fmt_tabla(df):
    pct = [c for c in df.columns if c.split("_")[0] in ("CAGR", "vol", "caida")]
    f = {c: "{:+.1%}".format for c in pct}
    f.update({c: "{:.2f}".format for c in df.columns if c not in pct and df[c].dtype != object})
    return df.to_string(formatters=f)


# ---------------- motor de rupturas (v2) ----------------
def rendimiento_rupturas():
    ruta = os.path.join(C.CARPETA_REPORTES, "operaciones.csv")
    if not os.path.exists(ruta):
        return None
    ops = pd.read_csv(ruta)
    ops["fecha_salida"] = pd.to_datetime(ops["fecha_salida"], utc=True, format="mixed")
    ops["fecha_entrada"] = pd.to_datetime(ops["fecha_entrada"], utc=True, format="mixed")
    pnl = ops.groupby(ops["fecha_salida"].dt.floor("D"))["pnl"].sum()
    dias = pd.date_range(ops["fecha_entrada"].min().floor("D"), pnl.index.max(), freq="D", tz="UTC")
    capital = C.CAPITAL_INICIAL + pnl.reindex(dias, fill_value=0).cumsum()
    return capital.pct_change().fillna(0)


def main():
    os.makedirs(C.CARPETA_REPORTES, exist_ok=True)
    inf = ["=" * 78, "ROGELIO v2.5 - MOTOR DE FACTORES Y CUENTA COMBINADA", "=" * 78]

    print("[1/5] Armando el panel diario...")
    P = panel_diario()
    inf.append(f"Panel: {P['cierre'].shape[1]} monedas, del {P['cierre'].index[0].date()} "
               f"al {P['cierre'].index[-1].date()}")

    # ---------- 2. cada factor y cada sesgo, sin apalancar ----------
    print("[2/5] Probando cada factor en sus dos sesgos...")
    filas, sims = [], {}
    for nombre, cfg in C.FACTORES.items():
        for sesgo in ("bajista", "neutral"):
            c = {**cfg, "sesgo": sesgo}
            sim = simular_factor(P, carteras_objetivo(P, nombre, c), c["stop"])
            sims[(nombre, sesgo)] = sim
            fila = {"factor": f"{nombre} / {sesgo}", "funding_cobrado_anual": sim["funding"].mean() * 365,
                    "costos_anual": sim["costo"].mean() * 365, "exposicion_media": sim["bruta"].mean()}
            fila.update(antes_despues(sim["rend"]))
            filas.append(fila)
    t = pd.DataFrame(filas).set_index("factor")
    inf.append("\n######## 1. CADA FACTOR, SIN APALANCAR (exposición bruta 1x) ########")
    inf.append(f"   'antes' = hasta {CORTE.date()} (para decidir) | 'despues' = desde {CORTE.date()} (prueba honesta)\n")
    cols = ["CAGR_antes", "sharpe_antes", "t_mensual_antes", "CAGR_despues", "sharpe_despues",
            "t_mensual_despues", "caida_max_despues", "funding_cobrado_anual", "costos_anual", "exposicion_media"]
    inf.append(fmt_tabla(t[cols]))
    for nombre in C.FACTORES:
        sub = t.loc[[f"{nombre} / bajista", f"{nombre} / neutral"]]
        mejor = sub["sharpe_antes"].idxmax()
        inf.append(f"  {nombre}: con datos ANTERIORES a 2024 se elegiría '{mejor}' -> después de 2024: "
                   f"Sharpe {sub.loc[mejor, 'sharpe_despues']:.2f}, t mensual {sub.loc[mejor, 't_mensual_despues']:.2f}")

    # ---------- 3. el motor con la configuración elegida ----------
    print("[3/5] Armando el motor con la configuración de config.py...")
    crudo, bruta = 0.0, 0.0
    for nombre, cfg in C.FACTORES.items():
        if not cfg["activa"]:
            continue
        sim = sims[(nombre, cfg["sesgo"])]
        peso = C.ASIGNACION_FACTORES.get(nombre, 0)
        crudo = crudo + peso * sim["rend"]
        bruta = bruta + peso * sim["bruta"]
    if isinstance(crudo, float):
        raise SystemExit("No hay factores activos en config.FACTORES.")
    factores, escala = objetivo_volatilidad(crudo, bruta)
    inf.append(f"\n######## 2. MOTOR DE FACTORES (config: " +
               ", ".join(f"{n}={c['sesgo']}" for n, c in C.FACTORES.items() if c["activa"]) +
               f"; volatilidad objetivo {C.VOLATILIDAD_OBJETIVO:.0%}) ########")
    motor = pd.DataFrame([{"serie": "sin apalancar", **antes_despues(crudo)},
                          {"serie": "con objetivo de volatilidad", **antes_despues(factores)}]).set_index("serie")
    inf.append(fmt_tabla(motor[["CAGR_antes", "caida_max_antes", "sharpe_antes",
                                "CAGR_despues", "caida_max_despues", "sharpe_despues", "t_mensual_despues"]]))
    inf.append(f"  exposición media del motor: {(escala * bruta).mean():.2f}x  |  máxima: {(escala * bruta).max():.2f}x")

    # ---------- 4. cuenta combinada ----------
    print("[4/5] Combinando con el motor de rupturas (v2)...")
    rupt = rendimiento_rupturas()
    inf.append("\n######## 3. CUENTA COMBINADA ########")
    if rupt is None:
        inf.append("  No se encontró reportes/operaciones.csv: corré primero 'python rogelio.py'.")
        comb = factores
    else:
        dias = rupt.index.intersection(factores.index)
        r1, r2 = rupt.reindex(dias).fillna(0), factores.reindex(dias).fillna(0)
        corr = ((1 + r1).resample("ME").prod() - 1).corr((1 + r2).resample("ME").prod() - 1)
        inf.append(f"  Correlación mensual rupturas vs factores: {corr:+.2f}  (cerca de 0 o negativa = se complementan)")
        comb = C.PESO_MOTOR_RUPTURAS * r1 + C.PESO_MOTOR_FACTORES * r2
        tabla = pd.DataFrame([
            {"serie": "solo rupturas (v2)", **estadisticas(r1)},
            {"serie": "solo factores (v2.5)", **estadisticas(r2)},
            {"serie": f"combinada {C.PESO_MOTOR_RUPTURAS:.0%}/{C.PESO_MOTOR_FACTORES:.0%}", **estadisticas(comb)},
        ]).set_index("serie")
        inf.append(fmt_tabla(tabla))
        anual = ((1 + pd.DataFrame({"rupturas": r1, "factores": r2, "combinada": comb}))
                 .resample("YE").prod() - 1)
        anual.index = anual.index.year
        inf.append("\n  Resultado por año:")
        inf.append(anual.to_string(float_format=lambda x: f"{x:+.1%}"))

    # ---------- 5. calibración de la volatilidad objetivo ----------
    print("[5/5] Calibrando la volatilidad objetivo...")
    limite = C.DRAWDOWN_CORTE
    filas = []
    for v in VOLS_A_PROBAR:
        f_v, _ = objetivo_volatilidad(crudo, bruta, vol_obj=v)
        if rupt is not None:
            c_v = C.PESO_MOTOR_RUPTURAS * r1 + C.PESO_MOTOR_FACTORES * f_v.reindex(dias).fillna(0)
        else:
            c_v = f_v
        e = estadisticas(c_v)
        filas.append({"vol_objetivo": v, **e, "CAGR_desde_2024": estadisticas(c_v[c_v.index >= CORTE])["CAGR"],
                      f"P(caida>{limite:.0%})": prob_caida(c_v, limite)})
    cal = pd.DataFrame(filas).set_index("vol_objetivo")
    inf.append(f"\n######## 4. CALIBRACIÓN: cuenta combinada según la volatilidad objetivo del motor de factores ########")
    inf.append(fmt_tabla(cal))
    ok = cal[(cal["CAGR"] >= C.OBJETIVO_ANUAL) & (cal["caida_max"] >= -limite)]
    if len(ok):
        v = ok.index[0]
        inf.append(f"\n  RECOMENDACIÓN: VOLATILIDAD_OBJETIVO = {v:.2f} en config.py -> {ok.loc[v, 'CAGR']:.1%} anual, "
                   f"caída máxima {ok.loc[v, 'caida_max']:.1%}")
    else:
        mejor = cal[cal["caida_max"] >= -limite]
        if len(mejor):
            v = mejor["CAGR"].idxmax()
            inf.append(f"\n  El {C.OBJETIVO_ANUAL:.0%} anual NO se alcanza sin pasar una caída del {limite:.0%}. "
                       f"Lo mejor dentro del límite: vol objetivo {v:.2f} -> {mejor.loc[v, 'CAGR']:.1%} anual, "
                       f"caída {mejor.loc[v, 'caida_max']:.1%}.")
        else:
            inf.append(f"\n  Ninguna configuración respeta la caída máxima del {limite:.0%}.")
    inf.append("\n  Recordá: elegir parámetros mirando el pasado es ajuste al pasado. El testnet decide.")

    texto = "\n".join(inf)
    print("\n" + texto)
    with open(os.path.join(C.CARPETA_REPORTES, "informe_v25.txt"), "w", encoding="utf-8") as f:
        f.write(texto)

    # ---------- gráfico ----------
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    series = {"factores (v2.5)": factores}
    if rupt is not None:
        series = {"rupturas (v2)": r1, "factores (v2.5)": r2, "combinada": comb}
    for nombre, r in series.items():
        a1.plot((1 + r).cumprod() * C.CAPITAL_INICIAL, label=nombre)
    a1.axhline(C.CAPITAL_INICIAL, color="black", linewidth=0.6, linestyle=":")
    a1.set_title("Rogelio v2.5 - motores y cuenta combinada")
    a1.set_ylabel("Capital (USDT)")
    a1.legend()
    a1.grid(alpha=0.3)
    curva = (1 + comb).cumprod()
    a2.fill_between(curva.index, (curva / curva.cummax() - 1) * 100, 0, color="crimson", alpha=0.5)
    a2.axhline(-limite * 100, color="black", linestyle="--", linewidth=0.8)
    a2.set_ylabel("Caída % (combinada)")
    a2.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(C.CARPETA_REPORTES, "curva_v25.png"), dpi=110)
    plt.close()
    print(f"\nListo: {C.CARPETA_REPORTES}/informe_v25.txt y {C.CARPETA_REPORTES}/curva_v25.png")


if __name__ == "__main__":
    main()
