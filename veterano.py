"""
EL VETERANO (v2.7): una rutina diaria de trader experimentado.

Cada mañana a las 08:00 UTC (apertura de Londres) Rogelio:
  1. Mira la volatilidad de BTC y decide qué tipo de día es (tranquilo, movido o turbulento).
  2. Junta las señales de las últimas 24 h de sus estrategias probadas (vendedor, batacazo, comprador).
  3. Descarta las que ya tocaron el stop, las que el precio ya "corrió" y las que el modelo desaprueba.
  4. Las ordena por calidad (primero el vendedor, después el batacazo, después el comprador;
     dentro de cada una, por la probabilidad del modelo) y abre las mejores hasta el cupo del día.
  5. En días tranquilos deja correr hasta 3 días; en días movidos, cierra en el día.

No hay reglas de entrada nuevas: cambia CUÁNDO y CUÁLES se toman. Por eso responde a la
lección de v2.6 (elegir por calidad en vez de por orden de llegada).

Uso (después de correr rogelio.py, que deja reportes/candidatas.csv):
    python veterano.py
"""
import os
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import config as C
from indicadores import cargar
from simulador import simular_operacion
from v25 import estadisticas, antes_despues, prob_caida, fmt_tabla

warnings.filterwarnings("ignore")
pd.set_option("display.width", 220)
V = C.VETERANO
CORTE = pd.Timestamp(C.FECHA_CORTE_VALIDACION, tz="UTC")


def leer_candidatas():
    ruta = os.path.join(C.CARPETA_REPORTES, "candidatas.csv")
    if not os.path.exists(ruta):
        raise SystemExit("Primero corré: python rogelio.py")
    c = pd.read_csv(ruta)
    c = c[c["estrategia"].isin(V["prioridad"])]
    if "grupo" not in c:
        c["grupo"] = "originales"
    return c


def preparar_monedas(monedas):
    datos = {}
    for m in monedas:
        try:
            df = cargar(m)
        except FileNotFoundError:
            continue
        arr = {k: df[k].to_numpy(dtype=float) for k in ("apertura", "maximo", "minimo", "cierre", "atr", "funding")}
        arr["fecha"] = df["fecha"].to_numpy()
        arr["fraccion_funding"] = 0.5          # velas de 4 h: media ventana de funding (8 h)
        arr["indice"] = {f: i for i, f in enumerate(df["fecha"])}
        datos[m] = arr
    return datos


def tipo_de_dia(vol):
    if pd.isna(vol) or float(vol) > V["vol_turbulento"]:
        return "turbulento", None
    if vol > V["vol_movido"]:
        return "movido", V["dia_movido"]
    return "tranquilo", V["dia_tranquilo"]


def simular_veterano(cand, datos):
    btc = cargar(C.MONEDA_REFERENCIA)
    # vela que empieza 4 h antes de la decisión: cierra justo a la hora de decidir
    hora_vela = (V["hora_decision_utc"] - 4) % 24
    decisiones = btc[btc["fecha"].dt.hour == hora_vela][["fecha", "vol_pct"]].reset_index(drop=True)
    velas_ventana = V["ventana_senales_h"] // 4
    orden = {e: i for i, e in enumerate(V["prioridad"])}
    cfg_estr = C.ESTRATEGIAS

    capital, maximo = C.CAPITAL_INICIAL, C.CAPITAL_INICIAL
    abiertas, operaciones, dias = [], [], []
    curva = [(decisiones["fecha"].iloc[0], capital)]
    # por moneda: candidatas ordenadas por vela, para buscar rápido las de las últimas 24 h
    por_moneda = {}
    for m, g in cand.groupby("moneda"):
        g = g.sort_values("idx_senal")
        por_moneda[m] = (g["idx_senal"].to_numpy(), g.to_dict("records"))

    for d in decisiones.to_dict("records"):
        ahora = d["fecha"] + pd.Timedelta(hours=4)          # momento de la decisión
        for op in sorted([o for o in abiertas if o["fecha_salida"] <= ahora], key=lambda o: o["fecha_salida"]):
            capital += op["pnl"]
            maximo = max(maximo, capital)
            curva.append((op["fecha_salida"], capital))
            abiertas.remove(op)

        tipo, reglas = tipo_de_dia(d["vol_pct"])
        if reglas is None:
            dias.append((d["fecha"], tipo, 0, 0))
            continue

        # ---- juntar candidatas vigentes ----
        vigentes = []
        for m, arr in datos.items():
            if m not in por_moneda:
                continue
            t = arr["indice"].get(d["fecha"])
            if t is None:
                continue
            if t + 1 >= len(arr["cierre"]):
                continue
            idx, filas = por_moneda[m]
            desde, hasta = np.searchsorted(idx, t - velas_ventana, "right"), np.searchsorted(idx, t, "right")
            for s in filas[desde:hasta]:
                lado, si = int(s["lado"]), int(s["idx_senal"])
                stop = s["stop_inicial"]
                tramo_h, tramo_l = arr["maximo"][si + 1:t + 1], arr["minimo"][si + 1:t + 1]
                if lado == -1 and len(tramo_h) and tramo_h.max() >= stop:
                    continue                                   # ya tocó el stop
                if lado == 1 and len(tramo_l) and tramo_l.min() <= stop:
                    continue
                a, c = arr["atr"][t], arr["cierre"][t]
                if lado * (c - arr["cierre"][si]) > V["max_corrida_atr"] * a:
                    continue                                   # el precio ya corrió: llegar tarde es mal precio
                p = s.get("p_modelo", np.nan)
                if cfg_estr[s["estrategia"]]["usar_modelo"] and pd.notna(p) and p < cfg_estr[s["estrategia"]]["prob_min"]:
                    continue                                   # el modelo la desaprueba
                dist = np.clip(lado * (c - stop) / a, C.STOP_MIN_ATR, C.STOP_MAX_ATR)
                vigentes.append({"moneda": m, "t": t, "lado": lado, "estrategia": s["estrategia"],
                                 "stop": c - lado * dist * a, "riesgo_precio": dist * a, "precio": c,
                                 "p": p if pd.notna(p) else 0.5, "grupo": s["grupo"]})
        if not vigentes:
            dias.append((d["fecha"], tipo, 0, 0))
            continue

        vigentes.sort(key=lambda x: (orden[x["estrategia"]], -x["p"]))
        abiertas_hoy, revisadas, vistas = 0, 0, set()
        for v in vigentes:
            if abiertas_hoy >= reglas["operaciones"] or len(abiertas) >= V["max_abiertas"]:
                break
            if v["moneda"] in vistas or any(o["moneda"] == v["moneda"] for o in abiertas):
                continue
            vistas.add(v["moneda"])
            revisadas += 1
            objetivo = v["precio"] + v["lado"] * v["riesgo_precio"] * reglas["rr"]
            p = {**V["salida"], "max_velas": reglas["max_velas"]}
            res = simular_operacion(datos[v["moneda"]], v["t"], v["lado"], v["stop"], objetivo, p)
            if not res or not res["completa"]:
                continue
            riesgo_usd = capital * V["riesgo"]
            res.update({k: v[k] for k in ("moneda", "lado", "estrategia", "grupo")})
            res.update({"tipo_dia": tipo, "p_modelo": v["p"], "riesgo_usd": riesgo_usd,
                        "pnl": riesgo_usd * res["R"], "capital_antes": capital})
            abiertas.append(res)
            operaciones.append(res)
            abiertas_hoy += 1
        dias.append((d["fecha"], tipo, len(vigentes), abiertas_hoy))

    for op in sorted(abiertas, key=lambda o: o["fecha_salida"]):
        capital += op["pnl"]
        curva.append((op["fecha_salida"], capital))
    ops = pd.DataFrame(operaciones)
    ops["fecha_entrada"] = pd.to_datetime(ops["fecha_entrada"], utc=True)
    ops["fecha_salida"] = pd.to_datetime(ops["fecha_salida"], utc=True)
    curva = pd.DataFrame(curva, columns=["fecha", "capital"])
    curva["fecha"] = pd.to_datetime(curva["fecha"], utc=True)
    diaria = curva.sort_values("fecha").set_index("fecha")["capital"].resample("1D").last().ffill()
    return ops, diaria.pct_change().fillna(0), pd.DataFrame(dias, columns=["fecha", "tipo", "candidatas", "abiertas"])


def resumen_ops(ops, columna):
    g = ops.groupby(columna)
    t = pd.DataFrame({"operaciones": g.size(), "win_rate": g["R"].apply(lambda x: (x > 0).mean()),
                      "expectativa_R": g["R"].mean(), "ganancia_usdt": g["pnl"].sum(),
                      "velas_medias": g["velas"].mean()})
    return t.to_string(float_format=lambda x: f"{x:.3f}")


def main():
    cand = leer_candidatas()
    universos = {"20 monedas originales": cand[cand["grupo"] == "originales"]}
    if (cand["grupo"] == "nuevas").any():
        universos["40 monedas"] = cand
    datos = preparar_monedas(sorted(cand["moneda"].unique()))

    inf = ["=" * 78, "ROGELIO v2.7 - EL VETERANO (rutina diaria a las 08:00 UTC)", "=" * 78,
           f"Riesgo por operación {V['riesgo']:.1%} | día tranquilo: hasta {V['dia_tranquilo']['operaciones']} ops, "
           f"hasta {V['dia_tranquilo']['max_velas'] * 4 // 24} días | día movido: hasta {V['dia_movido']['operaciones']} ops, "
           f"hasta {V['dia_movido']['max_velas'] * 4 // 24} día | turbulento: no opera"]
    resultados = {}
    for nombre, c in universos.items():
        print(f"Simulando al veterano con {nombre}...")
        ops, rend, dias = simular_veterano(c, {m: datos[m] for m in c["moneda"].unique() if m in datos})
        resultados[nombre] = (ops, rend)
        ops.to_csv(os.path.join(C.CARPETA_REPORTES, f"veterano_{len(c['moneda'].unique())}monedas.csv"), index=False)
        e = estadisticas(rend)
        ad = antes_despues(rend)
        n_dias = len(dias)
        inf.append(f"\n######## {nombre.upper()} ########")
        inf.append(f"  Días evaluados: {n_dias} | tranquilos {(dias['tipo'] == 'tranquilo').mean():.0%}, "
                   f"movidos {(dias['tipo'] == 'movido').mean():.0%}, turbulentos {(dias['tipo'] == 'turbulento').mean():.0%}")
        inf.append(f"  Días con al menos una operación: {(dias['abiertas'] > 0).mean():.0%} | "
                   f"operaciones por día (promedio): {len(ops) / n_dias:.2f} | candidatas vigentes por día: "
                   f"{dias['candidatas'].mean():.2f}")
        inf.append(f"  Operaciones: {len(ops)} | win rate {(ops['R'] > 0).mean():.1%} | "
                   f"expectativa {ops['R'].mean():+.3f}R")
        inf.append(f"  CAGR {e['CAGR']:.1%} | caída máxima {e['caida_max']:.1%} | Sharpe {e['sharpe']:.2f} | "
                   f"t mensual {e['t_mensual']:.2f} | P(caída > {C.DRAWDOWN_CORTE:.0%}) {prob_caida(rend, C.DRAWDOWN_CORTE):.0%}")
        inf.append(f"  Antes de 2024: CAGR {ad['CAGR_antes']:.1%}, Sharpe {ad['sharpe_antes']:.2f} | "
                   f"Después de 2024: CAGR {ad['CAGR_despues']:.1%}, Sharpe {ad['sharpe_despues']:.2f}, "
                   f"t mensual {ad['t_mensual_despues']:.2f}")
        inf.append("\n  Por tipo de día:\n" + resumen_ops(ops, "tipo_dia"))
        inf.append("\n  Por estrategia de origen:\n" + resumen_ops(ops, "estrategia"))
        anual = ops.assign(anio=ops["fecha_entrada"].dt.year).groupby("anio")["pnl"].sum()
        inf.append("\n  Ganancia por año (USDT): " + ", ".join(f"{a}: {v:+,.0f}" for a, v in anual.items()))

    inf.append("\n######## COMPARACIÓN DE REFERENCIA ########")
    inf.append("  v2.5 (20 monedas, escala 1,5): CAGR 23,7% | caída −13,2% | Sharpe 1,18 | t mensual 2,44")
    inf.append("  El veterano gana la comparación solo si mejora el Sharpe (ganancia por unidad de riesgo),")
    inf.append("  sobre todo DESPUÉS de 2024. Más ganancia con más caída no es una mejora.")

    texto = "\n".join(inf)
    print("\n" + texto)
    with open(os.path.join(C.CARPETA_REPORTES, "informe_veterano.txt"), "w", encoding="utf-8") as f:
        f.write(texto)

    fig, ax = plt.subplots(figsize=(13, 6))
    for nombre, (_, rend) in resultados.items():
        ax.plot((1 + rend).cumprod() * C.CAPITAL_INICIAL, label=f"veterano - {nombre}")
    ax.axhline(C.CAPITAL_INICIAL, color="black", linewidth=0.6, linestyle=":")
    ax.set_title("Rogelio v2.7 - el veterano")
    ax.set_ylabel("Capital (USDT)")
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(C.CARPETA_REPORTES, "curva_veterano.png"), dpi=110)
    plt.close()
    print(f"\nListo: {C.CARPETA_REPORTES}/informe_veterano.txt y {C.CARPETA_REPORTES}/curva_veterano.png")


if __name__ == "__main__":
    main()
