"""
BACKTEST DE CARTERA + GESTIÓN DE RIESGO (v2: tres estrategias)
Recorre en orden cronológico todas las operaciones candidatas de las 20 monedas
y de las tres estrategias, y decide, como lo haría Rogelio en vivo, cuáles abrir
y con qué tamaño.

Dos niveles de control:
  - Por estrategia: su propio riesgo por operación, presupuesto de riesgo y máximo de posiciones.
  - De la cuenta: máximo de posiciones, riesgo total abierto, misma dirección, pérdida diaria, corte.

Además mide si el batacazo le quita lugar a las otras estrategias (tu condición para mantenerlo).
"""
import math
import numpy as np
import pandas as pd
import config as C


def tamano_kelly(p, b, cfg):
    """Kelly: f* = p - (1-p)/b. Se usa una fracción (1/4) y se limita al riesgo máximo de la estrategia.
    p = probabilidad de ganar, b = ganancia media / pérdida media."""
    if pd.isna(p) or pd.isna(b) or b <= 0:
        return cfg["riesgo_base"]
    f = p - (1 - p) / b
    return float(np.clip(C.FRACCION_KELLY * f, 0, cfg["riesgo_max"]))


def apalancamiento_seguro(dist_stop):
    """El mayor apalancamiento (hasta el máximo) que deja la liquidación lejos del stop.
    Liquidación aprox. a (1/apalancamiento - margen de mantenimiento) del precio."""
    lev = 1 / (C.DISTANCIA_LIQUIDACION_MIN * dist_stop + C.MARGEN_MANTENIMIENTO)
    return max(1, min(C.APALANCAMIENTO_MAXIMO, math.floor(lev)))


def configuraciones_escaladas(escala):
    """Copia de las estrategias con el riesgo multiplicado por 'escala'."""
    return {n: {**cfg, "riesgo_base": cfg["riesgo_base"] * escala, "riesgo_max": cfg["riesgo_max"] * escala,
                "presupuesto_riesgo": cfg["presupuesto_riesgo"] * escala}
            for n, cfg in C.ESTRATEGIAS.items()}


def backtest_cartera(ops, usar_modelo=C.USAR_MODELO, escala=None):
    escala = C.ESCALA_RIESGO if escala is None else escala
    cfgs = configuraciones_escaladas(escala)
    riesgo_abierto_max = C.RIESGO_ABIERTO_MAXIMO * escala
    prioridad = {k: v["prioridad"] for k, v in C.ESTRATEGIAS.items()}
    ops = ops.assign(_prio=ops["estrategia"].map(prioridad)) \
             .sort_values(["fecha_entrada", "_prio"]).drop(columns="_prio").reset_index(drop=True)
    capital = C.CAPITAL_INICIAL
    maximo = capital
    abiertas = []
    ejecutadas, rechazos = [], {}
    bloqueos_batacazo = 0                 # operaciones de A/B frenadas mientras el batacazo ocupaba lugar
    curva = [(ops["fecha_entrada"].min(), capital)]
    dia_actual, perdida_dia, capital_inicio_dia = None, 0.0, capital
    corte = None

    def rechazar(motivo, op):
        nonlocal bloqueos_batacazo
        clave = f"{op['estrategia']}: {motivo}"
        rechazos[clave] = rechazos.get(clave, 0) + 1
        if (op["estrategia"] != "batacazo" and motivo in ("max_posiciones", "max_misma_direccion",
                                                           "riesgo_cuenta_lleno", "margen_insuficiente")
                and any(o["estrategia"] == "batacazo" for o in abiertas)):
            bloqueos_batacazo += 1

    def cerrar_hasta(fecha):
        nonlocal capital, maximo, perdida_dia
        for op in sorted([o for o in abiertas if o["fecha_salida"] <= fecha], key=lambda o: o["fecha_salida"]):
            capital += op["pnl"]
            maximo = max(maximo, capital)
            if op["fecha_salida"].date() == dia_actual and op["pnl"] < 0:
                perdida_dia += -op["pnl"]
            op["capital_despues"] = capital
            curva.append((op["fecha_salida"], capital))
            abiertas.remove(op)

    for _, op in ops.iterrows():
        cfg = cfgs[op["estrategia"]]
        fecha = op["fecha_entrada"]
        if fecha.date() != dia_actual:
            dia_actual, perdida_dia, capital_inicio_dia = fecha.date(), 0.0, capital
        cerrar_hasta(fecha)
        propias = [o for o in abiertas if o["estrategia"] == op["estrategia"]]

        # ---------------- VETOS DE LA CUENTA ----------------
        if capital <= maximo * (1 - C.DRAWDOWN_CORTE):
            corte = corte or fecha
            if not C.MODO_INVESTIGACION:
                break
        if perdida_dia >= C.PERDIDA_DIARIA_MAXIMA * capital_inicio_dia:
            rechazar("limite_perdida_diaria", op); continue
        if len(abiertas) >= C.MAX_POSICIONES:
            rechazar("max_posiciones", op); continue
        if any(o["moneda"] == op["moneda"] for o in abiertas):
            rechazar("moneda_ya_abierta", op); continue
        if sum(o["lado"] == op["lado"] for o in abiertas) >= C.MAX_MISMA_DIRECCION:
            rechazar("max_misma_direccion", op); continue

        # ---------------- VETOS DE LA ESTRATEGIA ----------------
        if len(propias) >= cfg["max_posiciones"]:
            rechazar("max_posiciones_estrategia", op); continue

        # ---------------- MODELO ----------------
        p = op.get("p_modelo", np.nan)
        con_modelo = usar_modelo and cfg["usar_modelo"]
        if con_modelo and not pd.isna(p) and p < cfg["prob_min"]:
            rechazar("filtro_modelo", op); continue
        riesgo = tamano_kelly(p, op.get("b_estimado", np.nan), cfg) if con_modelo else cfg["riesgo_base"]

        libre_estrategia = cfg["presupuesto_riesgo"] - sum(o["riesgo_pct"] for o in propias)
        libre_cuenta = riesgo_abierto_max - sum(o["riesgo_pct"] for o in abiertas)
        if libre_cuenta < C.RIESGO_MINIMO:
            rechazar("riesgo_cuenta_lleno", op); continue
        riesgo = min(riesgo, libre_estrategia, libre_cuenta)
        if riesgo < C.RIESGO_MINIMO:
            rechazar("presupuesto_estrategia_lleno", op); continue

        # ---------------- TAMAÑO, MARGEN Y APALANCAMIENTO ----------------
        riesgo_usd = capital * riesgo
        nocional = riesgo_usd / op["dist_stop_pct"]
        lev = apalancamiento_seguro(op["dist_stop_pct"])
        margen_libre = capital - sum(o["margen"] for o in abiertas)
        margen = nocional / lev
        if margen > margen_libre:                       # no alcanza: se achica la posición
            factor = max(margen_libre, 0) / margen
            nocional, margen, riesgo_usd = nocional * factor, margen * factor, riesgo_usd * factor
            riesgo *= factor
            if riesgo < C.RIESGO_MINIMO:
                rechazar("margen_insuficiente", op); continue

        registro = op.to_dict()
        registro.update({"riesgo_pct": riesgo, "riesgo_usd": riesgo_usd, "nocional": nocional,
                         "apalancamiento": lev, "margen": margen, "capital_antes": capital,
                         "pnl": riesgo_usd * op["R"]})
        abiertas.append(registro)
        ejecutadas.append(registro)

    cerrar_hasta(pd.Timestamp.max.tz_localize("UTC"))
    tabla = pd.DataFrame(ejecutadas)
    curva = pd.DataFrame(curva, columns=["fecha", "capital"]).sort_values("fecha")
    extra = {"bloqueos_por_batacazo": bloqueos_batacazo}
    return tabla, curva, rechazos, corte, extra
