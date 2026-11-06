"""
exportar_web.py — Prepara los datos de la página de repetición de Rogelio.

No modifica nada de Rogelio: solo LEE lo que ya dejó en las carpetas
`reportes/` (operaciones del backtest) y `datos/` (velas de 4 horas), y
escribe archivos nuevos en `docs/replay/`, que es lo que usa la página.

Uso:
    python exportar_web.py                  # busca todo solo
    python exportar_web.py --operaciones reportes/operaciones.csv
    python exportar_web.py --demo           # datos inventados, para probar la página

Después de correrlo, abrí docs/index.html con doble clic para ver la página.
"""

import argparse
import glob
import json
import math
import os
import sys
import unicodedata
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 1. Ajustes (lo único que puede hacer falta tocar)
# ---------------------------------------------------------------------------

CARPETA_DATOS = "datos"
CARPETA_REPORTES = "reportes"
CARPETA_SALIDA = os.path.join("docs", "replay")

VERSION = "v2.5"

# Métricas oficiales del backtest (historial de versiones de Rogelio).
METRICAS_OFICIALES = {
    "rendimiento_anual": 23.7,   # %
    "caida_maxima": -13.2,       # %
    "sharpe": 1.18,
    "t_mensual": 2.44,
    "sharpe_deflactado": 0.83,
    "anios_positivos": "6 de 6",
    "pruebas_realizadas": 68,
    "periodo": "2021–2026",
}

# Riesgo por operación (% de la cuenta) si el registro no lo trae.
# v2.5 = riesgo base de v2 multiplicado por ESCALA_RIESGO 1,5.
RIESGO_POR_ESTRATEGIA = {"vendedor": 1.5, "comprador": 1.5, "batacazo": 0.75}
RIESGO_POR_DEFECTO = 1.5

# Año en que empieza la parte "fuera de muestra" (datos nuevos para Rogelio).
INICIO_FUERA_DE_MUESTRA = 2024

# Tus enlaces. Cambiá solo lo que está entre comillas y después corré
#     python exportar_web.py
# para que la página los tome (la página NO lee este archivo directamente).
USUARIO_GITHUB = "nico-barrera-01"
REPOSITORIO = "rogelio-bot-trading"
LINKEDIN = "https://www.linkedin.com/in/nicolas-barrera-216524241"


def _armar_enlaces():
    linkedin = LINKEDIN.strip().rstrip("/")
    if linkedin and not linkedin.startswith("http"):
        # Se aceptan también "linkedin.com/in/tu-nombre" o solo "tu-nombre".
        linkedin = ("https://www." + linkedin) if "linkedin.com" in linkedin \
            else "https://www.linkedin.com/in/" + linkedin
    usuario = USUARIO_GITHUB.strip().strip("/").split("/")[-1]
    return {"github": f"https://github.com/{usuario}/{REPOSITORIO.strip()}", "linkedin": linkedin}


ENLACES = _armar_enlaces()
AUTOR = "Nicolás Barrera"

# Nombres de columna que se reconocen (sin tildes ni mayúsculas).
ALIAS = {
    "moneda": ["moneda", "simbolo", "symbol", "coin", "par", "activo", "ticker"],
    "estrategia": ["estrategia", "setup", "strategy", "tipo", "sistema"],
    "lado": ["lado", "direccion", "side", "dir", "sentido"],
    "entrada_t": ["fecha_entrada", "entrada_fecha", "t_entrada", "entry_time", "tiempo_entrada",
                  "hora_entrada", "apertura", "inicio", "abierta", "fecha_apertura", "fecha"],
    "salida_t": ["fecha_salida", "salida_fecha", "t_salida", "exit_time", "tiempo_salida",
                 "hora_salida", "cierre", "fin", "cerrada", "fecha_cierre"],
    "entrada_p": ["precio_entrada", "entrada", "entry", "entry_price", "p_entrada", "px_entrada"],
    "salida_p": ["precio_salida", "salida", "exit", "exit_price", "p_salida", "px_salida"],
    "stop": ["stop", "stop_inicial", "sl", "stop_loss", "precio_stop"],
    "objetivo": ["objetivo", "tp", "take_profit", "target", "precio_objetivo"],
    "r": ["resultado_r", "r", "r_neto", "r_final", "pnl_r", "r_multiple", "resultado"],
    "motivo": ["motivo", "motivo_salida", "salida_motivo", "exit_reason", "razon", "razon_salida"],
    "prob": ["prob", "probabilidad", "p_ganar", "prob_modelo", "proba", "prob_ganar"],
    "riesgo": ["riesgo_pct", "riesgo", "risk", "riesgo_porcentaje", "riesgo_cuenta"],
    "usd": ["ganancia_usdt", "pnl_usdt", "resultado_usdt", "ganancia_usd", "pnl", "ganancia", "beneficio"],
}
CAPITAL_INICIAL = 1000.0
ALIAS_VELAS = {
    "t": ["fecha", "open_time", "timestamp", "tiempo", "time", "date", "datetime", "t"],
    "o": ["apertura", "open", "apertura_precio", "o", "abre"],
    "h": ["high", "maximo", "h", "max"],
    "l": ["low", "minimo", "l", "min"],
    "c": ["close", "cierre", "c", "cierra"],
}
COLUMNAS_TIEMPO = {"entrada_t", "salida_t"}
COLUMNAS_NUMERO = {"entrada_p", "salida_p", "stop", "objetivo", "r", "prob", "riesgo", "usd"}


# ---------------------------------------------------------------------------
# 2. Utilidades
# ---------------------------------------------------------------------------

def normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return texto.strip().lower().replace(" ", "_").replace("-", "_")


def a_tiempo(serie):
    """Convierte números (s o ms) o textos a fechas UTC."""
    if pd.api.types.is_datetime64_any_dtype(serie):
        s = pd.to_datetime(serie, utc=True)
    elif pd.api.types.is_numeric_dtype(serie):
        mediana = float(pd.Series(serie).dropna().median())
        unidad = "ms" if mediana > 1e11 else "s"
        s = pd.to_datetime(serie, unit=unidad, utc=True)
    else:
        s = pd.to_datetime(serie, utc=True, errors="coerce", format="mixed")
    return s


def es_tiempo(serie):
    try:
        if pd.api.types.is_numeric_dtype(serie):
            mediana = float(pd.Series(serie).dropna().median())
            return 1e9 < mediana < 1e14
        s = a_tiempo(serie)
        return s.notna().mean() > 0.9 and s.dt.year.between(2015, 2035).mean() > 0.9
    except Exception:
        return False


def es_numero(serie):
    serie = pd.Series(serie)
    presentes = serie[serie.notna() & (serie.astype(str).str.strip() != "")]
    if len(presentes) == 0:
        return False
    return pd.to_numeric(presentes, errors="coerce").notna().mean() > 0.9


def buscar_columnas(df, alias, tiempos=(), numeros=()):
    columnas = {normalizar(c): c for c in df.columns}
    encontradas, usadas = {}, set()
    for campo, nombres in alias.items():
        for nombre in nombres:
            real = columnas.get(nombre)
            if real is None or real in usadas:
                continue
            if campo in tiempos and not es_tiempo(df[real]):
                continue
            if campo in numeros and not es_numero(df[real]):
                continue
            encontradas[campo] = real
            usadas.add(real)
            break
    return encontradas


def leer_tabla(ruta):
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".csv":
        df = pd.read_csv(ruta, sep=None, engine="python")
    elif ext == ".parquet":
        df = pd.read_parquet(ruta)
    elif ext == ".feather":
        df = pd.read_feather(ruta)
    elif ext in (".pkl", ".pickle"):
        df = pd.read_pickle(ruta)
    else:
        raise ValueError(f"formato no soportado: {ruta}")
    if isinstance(df.index, pd.DatetimeIndex):
        df = df.reset_index()
    return df


def limpiar_moneda(texto):
    m = str(texto).upper().strip()
    for basura in ("/USDT:USDT", ":USDT", "/USDT", "USDT", "-PERP", "PERP"):
        if m.endswith(basura) and len(m) > len(basura):
            m = m[: -len(basura)]
    return m


def lado_numerico(valor):
    v = normalizar(valor)
    if v in ("1", "1.0", "long", "compra", "buy", "largo", "alcista", "c"):
        return 1
    if v in ("-1", "-1.0", "short", "venta", "sell", "corto", "bajista", "v"):
        return -1
    return 0


def redondear(x, cifras=6):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return None
    if x == 0:
        return 0
    d = cifras - int(math.floor(math.log10(abs(x)))) - 1
    return round(float(x), max(d, 0))


def escribir_js(ruta, variable_o_funcion, datos, es_funcion=False, clave=None):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    texto = json.dumps(datos, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    with open(ruta, "w", encoding="utf-8") as f:
        if es_funcion:
            f.write(f'{variable_o_funcion}({json.dumps(clave)},{texto});\n')
        else:
            f.write(f"window.{variable_o_funcion}={texto};\n")
    return os.path.getsize(ruta)


# ---------------------------------------------------------------------------
# 3. Operaciones
# ---------------------------------------------------------------------------

def encontrar_operaciones(carpeta, ruta_forzada=None):
    candidatos = [ruta_forzada] if ruta_forzada else sorted(
        glob.glob(os.path.join(carpeta, "**", "*.csv"), recursive=True)
        + glob.glob(os.path.join(carpeta, "**", "*.parquet"), recursive=True))
    mejor, mejor_puntaje = None, 0
    for ruta in candidatos:
        try:
            df = leer_tabla(ruta)
        except Exception:
            continue
        if len(df) < 5:
            continue
        cols = buscar_columnas(df, ALIAS, COLUMNAS_TIEMPO, COLUMNAS_NUMERO)
        if not {"moneda", "entrada_t", "r"} <= cols.keys():
            continue
        nombre = normalizar(os.path.basename(ruta))
        puntaje = len(cols)
        if nombre == "operaciones.csv":
            puntaje += 10
        elif "operacion" in nombre:
            puntaje += 2
        if any(x in nombre for x in ("veterano", "candidat", "senal", "factor", "v25")):
            puntaje -= 10
        if puntaje > mejor_puntaje and puntaje > 0:
            mejor, mejor_puntaje = (ruta, df, cols), puntaje
    return mejor


def preparar_operaciones(df, cols):
    t = pd.DataFrame()
    t["m"] = df[cols["moneda"]].map(limpiar_moneda)
    t["e"] = (df[cols["estrategia"]].map(normalizar) if "estrategia" in cols else "rogelio")
    t["te"] = a_tiempo(df[cols["entrada_t"]])
    t["ts"] = a_tiempo(df[cols["salida_t"]]) if "salida_t" in cols else pd.NaT
    for campo, destino in (("entrada_p", "pe"), ("salida_p", "ps"), ("stop", "sl"),
                           ("objetivo", "tp"), ("r", "r"), ("prob", "p"), ("riesgo", "rg")):
        t[destino] = pd.to_numeric(df[cols[campo]], errors="coerce") if campo in cols else np.nan
    t["usd"] = pd.to_numeric(df[cols["usd"]], errors="coerce") if "usd" in cols else np.nan
    t["motivo"] = df[cols["motivo"]].astype(str) if "motivo" in cols else ""

    if "lado" in cols:
        t["lado"] = df[cols["lado"]].map(lado_numerico)
    else:
        t["lado"] = 0
    sin_lado = t["lado"] == 0
    # Si no hay columna de lado, se deduce del stop: stop debajo = compra.
    t.loc[sin_lado & (t["sl"] < t["pe"]), "lado"] = 1
    t.loc[sin_lado & (t["sl"] > t["pe"]), "lado"] = -1

    # Precio de salida aproximado si falta (para poder dibujarla).
    falta = t["ps"].isna() & t["pe"].notna() & t["sl"].notna()
    t.loc[falta, "ps"] = t["pe"] + t["r"] * (t["pe"] - t["sl"])

    # Probabilidad en 0–1.
    t.loc[t["p"] > 1, "p"] = t["p"] / 100
    # Riesgo en % de la cuenta.
    t.loc[t["rg"] < 0.2, "rg"] = t["rg"] * 100
    falta_rg = t["rg"].isna()
    t.loc[falta_rg, "rg"] = t.loc[falta_rg, "e"].map(RIESGO_POR_ESTRATEGIA).fillna(RIESGO_POR_DEFECTO)

    t = t.dropna(subset=["te", "r"]).sort_values("te").reset_index(drop=True)

    # Si el registro trae la ganancia en USDT, se deduce el riesgo real de cada
    # operación (% de la cuenta en ese momento), para que el simulador coincida.
    if t["usd"].notna().mean() > 0.9:
        fin = t["ts"].fillna(t["te"])
        capital = CAPITAL_INICIAL
        for i in np.argsort(fin.values, kind="stable"):
            usd, r = t.at[i, "usd"], t.at[i, "r"]
            if pd.notna(usd) and abs(r) > 0.1:
                implicito = usd / capital / r * 100
                if 0.05 <= implicito <= 6:
                    t.at[i, "rg"] = implicito
            capital += 0 if pd.isna(usd) else usd
    return t


# ---------------------------------------------------------------------------
# 4. Velas
# ---------------------------------------------------------------------------

def encontrar_velas(carpeta, moneda):
    patrones = ["*.csv", "*.parquet", "*.feather", "*.pkl"]
    archivos = []
    for p in patrones:
        archivos += glob.glob(os.path.join(carpeta, "**", p), recursive=True)
    m = moneda.lower()
    candidatos = []
    for ruta in archivos:
        nombre = normalizar(os.path.basename(ruta))
        partes = nombre.replace(".", "_").split("_")
        coincide = any(parte in (m, m + "usdt") for parte in partes) or nombre.startswith(m + "usdt")
        if not coincide or "funding" in nombre:
            continue
        otro_marco = any(x in nombre for x in ("1h", "15m", "5m", "1d", "1m_"))
        puntaje = (2 if "4h" in nombre else 0) - (3 if otro_marco else 0)
        candidatos.append((puntaje, ruta))
    for _, ruta in sorted(candidatos, reverse=True):
        try:
            df = leer_tabla(ruta)
            cols = buscar_columnas(df, ALIAS_VELAS, tiempos={"t"}, numeros={"o", "h", "l", "c"})
            if len(cols) == 5:
                v = pd.DataFrame({k: (a_tiempo(df[c]) if k == "t" else pd.to_numeric(df[c], errors="coerce"))
                                  for k, c in cols.items()})
                v = v.dropna().drop_duplicates("t").sort_values("t").reset_index(drop=True)
                if len(v) > 50:
                    return v, ruta
        except Exception:
            continue
    return None, None


def paquete_moneda(velas, ops):
    epoca = pd.Timestamp("1970-01-01", tz="UTC")
    horas = ((velas["t"] - epoca) // pd.Timedelta(hours=1)).astype(int).tolist()
    ohlc = []
    for o, h, l, c in velas[["o", "h", "l", "c"]].itertuples(index=False):
        ohlc += [redondear(o), redondear(h), redondear(l), redondear(c)]
    return {"t": horas, "ohlc": ohlc, "ops": [op_compacta(o) for _, o in ops.iterrows()]}


def op_compacta(o):
    def num(x, cifras=6):
        return None if pd.isna(x) else redondear(float(x), cifras)

    def hora(x):
        return None if pd.isna(x) else int(x.value // 10**9 // 3600)

    return {
        "m": o["m"], "e": o["e"], "lado": int(o["lado"]),
        "te": hora(o["te"]), "ts": hora(o["ts"]),
        "pe": num(o["pe"]), "ps": num(o["ps"]), "sl": num(o["sl"]), "tp": num(o["tp"]),
        "r": num(o["r"], 4), "p": num(o["p"], 3), "rg": num(o["rg"], 3),
        "motivo": (o["motivo"] if o["motivo"] not in ("nan", "None") else ""),
    }


# ---------------------------------------------------------------------------
# 5. Curva de capital y estadísticas
# ---------------------------------------------------------------------------

def curva_desde_operaciones(ops):
    fin = ops["ts"].fillna(ops["te"])
    orden = np.argsort(fin.values, kind="stable")
    usa_usd = ops["usd"].notna().mean() > 0.9
    capital, puntos = 100.0, []
    for i in orden:
        if usa_usd:
            capital += 0 if pd.isna(ops["usd"].iloc[i]) else ops["usd"].iloc[i] / CAPITAL_INICIAL * 100
        else:
            capital *= 1 + ops["r"].iloc[i] * ops["rg"].iloc[i] / 100
        puntos.append((fin.iloc[i], capital))
    serie = pd.Series([p[1] for p in puntos], index=pd.DatetimeIndex([p[0] for p in puntos]))
    serie = serie.groupby(serie.index.normalize()).last()
    inicio = ops["te"].min().normalize() - pd.Timedelta(days=1)
    serie = pd.concat([pd.Series([100.0], index=[inicio]), serie])
    return serie.resample("D").last().ffill()


def encontrar_curva_oficial(carpeta):
    for ruta in sorted(glob.glob(os.path.join(carpeta, "**", "*.csv"), recursive=True)):
        nombre = normalizar(os.path.basename(ruta))
        if not any(x in nombre for x in ("curva", "capital", "equity")):
            continue
        try:
            df = leer_tabla(ruta)
        except Exception:
            continue
        cols = buscar_columnas(df, {"t": ALIAS_VELAS["t"],
                                    "v": ["capital", "equity", "saldo", "valor", "cuenta", "patrimonio"]},
                               tiempos={"t"}, numeros={"v"})
        if len(cols) == 2:
            s = pd.Series(pd.to_numeric(df[cols["v"]], errors="coerce").values,
                          index=pd.DatetimeIndex(a_tiempo(df[cols["t"]]))).dropna()
            s = s.groupby(s.index.normalize()).last().resample("D").last().ffill()
            return s / s.iloc[0] * 100, ruta
    return None, None


def estadisticas(curva):
    anios = (curva.index[-1] - curva.index[0]).days / 365.25
    cagr = (curva.iloc[-1] / curva.iloc[0]) ** (1 / anios) - 1 if anios > 0 else 0
    caida = (curva / curva.cummax() - 1).min()
    por_anio = curva.groupby(curva.index.year).last()
    previo = curva.groupby(curva.index.year).first()
    rend_anio = []
    anterior = None
    for anio, valor in por_anio.items():
        base = anterior if anterior is not None else previo[anio]
        rend_anio.append({"anio": int(anio), "rend": round((valor / base - 1) * 100, 2)})
        anterior = valor
    return {"cagr": round(cagr * 100, 2), "caida": round(caida * 100, 2), "por_anio": rend_anio}


def resumen_operaciones(ops):
    def bloque(d):
        return {"n": int(len(d)), "ganadoras": round(float((d["r"] > 0).mean() * 100), 1),
                "r_medio": round(float(d["r"].mean()), 3), "r_total": round(float(d["r"].sum()), 2)}

    por_estrategia = [{"e": e, **bloque(d)} for e, d in ops.groupby("e")]
    por_estrategia.sort(key=lambda x: -x["n"])
    por_moneda = [{"m": m, **bloque(d)} for m, d in ops.groupby("m")]
    por_moneda.sort(key=lambda x: -x["n"])
    corte = pd.Timestamp(f"{INICIO_FUERA_DE_MUESTRA}-01-01", tz="UTC")
    return {
        "total": bloque(ops),
        "antes": bloque(ops[ops["te"] < corte]) if (ops["te"] < corte).any() else None,
        "despues": bloque(ops[ops["te"] >= corte]) if (ops["te"] >= corte).any() else None,
        "por_estrategia": por_estrategia,
        "por_moneda": por_moneda,
    }


def serie_compacta(serie):
    serie = serie.dropna()
    return {"t": [int(x.value // 10**9 // 86400) for x in serie.index],
            "v": [redondear(float(v), 5) for v in serie.values]}


# ---------------------------------------------------------------------------
# 6. Datos de demostración (inventados)
# ---------------------------------------------------------------------------

def crear_demo(carpeta):
    """Velas sintéticas con períodos quietos seguidos de tendencias, y
    operaciones simuladas sobre ellas. NO son resultados de Rogelio."""
    rng = np.random.default_rng(7)
    os.makedirs(os.path.join(carpeta, "datos"), exist_ok=True)
    os.makedirs(os.path.join(carpeta, "reportes"), exist_ok=True)
    tiempos = pd.date_range("2020-01-01", "2026-10-31", freq="4h", tz="UTC")
    n = len(tiempos)
    monedas = {"BTC": 7200, "ETH": 130, "SOL": 1.5, "LINK": 1.8, "DOGE": 0.002}
    filas = []
    for moneda, precio0 in monedas.items():
        ret = np.zeros(n)
        i = 0
        while i < n:
            quieto = rng.integers(40, 160)
            ret[i:i + quieto] = rng.normal(0, 0.006, min(quieto, n - i))
            i += quieto
            if i >= n:
                break
            activo = rng.integers(30, 140)
            deriva = rng.choice([-1, 1], p=[0.5, 0.5]) * rng.uniform(0.002, 0.006)
            ret[i:i + activo] = rng.normal(deriva, 0.016, min(activo, n - i))
            i += activo
        cierre = precio0 * np.exp(np.cumsum(ret))
        apertura = np.r_[precio0, cierre[:-1]]
        rango = np.abs(rng.normal(0, 0.006, n)) * cierre + np.abs(cierre - apertura) * 0.2
        maximo = np.maximum(apertura, cierre) + rango * rng.uniform(0.2, 1, n)
        minimo = np.minimum(apertura, cierre) - rango * rng.uniform(0.2, 1, n)
        velas = pd.DataFrame({"open_time": (tiempos - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(milliseconds=1),
                              "open": apertura,
                              "high": maximo, "low": minimo, "close": cierre,
                              "volume": rng.uniform(1, 2, n)})
        velas.to_csv(os.path.join(carpeta, "datos", f"{moneda}USDT_4h.csv"), index=False)

        atr = pd.Series(maximo - minimo).rolling(14).mean().values
        ancho = (pd.Series(maximo).rolling(20).max() - pd.Series(minimo).rolling(20).min()).values
        ancho_rel = pd.Series(ancho / cierre).rolling(300).rank(pct=True).values
        libre = 0
        for j in range(320, n - 2):
            if j < libre or ancho_rel[j - 1] > 0.3:
                continue
            techo, piso = maximo[j - 20:j].max(), minimo[j - 20:j].min()
            lado = 1 if cierre[j] > techo else (-1 if cierre[j] < piso else 0)
            if lado == 0:
                continue
            estrategia = "batacazo" if rng.random() < 0.18 else ("comprador" if lado == 1 else "vendedor")
            entrada = apertura[j + 1]
            stop = (techo + piso) / 2
            dist = np.clip(abs(entrada - stop), atr[j], 4 * atr[j])
            stop = entrada - lado * dist
            objetivo = None if estrategia == "batacazo" else entrada + lado * dist * 2.5
            trailing = (3.5 if estrategia == "batacazo" else 2.5) * atr[j]
            mejor, stop_act, motivo, k = entrada, stop, "tiempo", j + 1
            limite = min(n - 1, j + 1 + (180 if estrategia == "batacazo" else 60))
            salida = cierre[limite]
            for k in range(j + 1, limite + 1):
                toca_stop = minimo[k] <= stop_act if lado == 1 else maximo[k] >= stop_act
                if toca_stop:
                    salida = stop_act
                    if stop_act == stop:
                        motivo = "stop"
                    elif abs(stop_act - entrada) < 1e-12:
                        motivo = "break_even"
                    else:
                        motivo = "trailing"
                    break
                if objetivo is not None:
                    toca_obj = maximo[k] >= objetivo if lado == 1 else minimo[k] <= objetivo
                    if toca_obj:
                        salida, motivo = objetivo, "objetivo"
                        break
                mejor = max(mejor, maximo[k]) if lado == 1 else min(mejor, minimo[k])
                if lado * (mejor - entrada) >= dist * (2 if estrategia == "batacazo" else 1):
                    if lado * (stop_act - entrada) < 0:
                        stop_act = entrada
                    candidato = mejor - lado * trailing
                    if lado * (candidato - stop_act) > 0:
                        stop_act = candidato
            r = lado * (salida - entrada) / dist - 0.06
            filas.append({
                "moneda": f"{moneda}USDT", "estrategia": estrategia,
                "lado": "compra" if lado == 1 else "venta",
                "fecha_entrada": tiempos[j + 1].isoformat(), "fecha_salida": tiempos[k].isoformat(),
                "precio_entrada": entrada, "precio_salida": salida, "stop": stop,
                "objetivo": objetivo, "resultado_r": round(r, 3), "motivo": motivo,
                "prob": round(float(np.clip(0.52 + 0.08 * np.tanh(r) + rng.normal(0, 0.05), 0.4, 0.8)), 3)
                if estrategia != "batacazo" else None,
            })
            libre = k + 1
    pd.DataFrame(filas).to_csv(os.path.join(carpeta, "reportes", "operaciones.csv"), index=False)
    print(f"  demo: {len(filas)} operaciones inventadas en {len(monedas)} monedas")


# ---------------------------------------------------------------------------
# 7. Programa principal
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Prepara los datos de la página de Rogelio.")
    ap.add_argument("--operaciones", help="archivo con el registro de operaciones del backtest")
    ap.add_argument("--datos", default=CARPETA_DATOS, help="carpeta con las velas")
    ap.add_argument("--reportes", default=CARPETA_REPORTES, help="carpeta con los reportes")
    ap.add_argument("--salida", default=CARPETA_SALIDA, help="carpeta donde se escriben los datos web")
    ap.add_argument("--demo", action="store_true", help="usar datos inventados para probar la página")
    args = ap.parse_args()

    print("Rogelio → página web")
    if args.demo:
        carpeta_demo = "_demo_web"
        crear_demo(carpeta_demo)
        args.datos = os.path.join(carpeta_demo, "datos")
        args.reportes = os.path.join(carpeta_demo, "reportes")
        args.operaciones = None

    encontrado = encontrar_operaciones(args.reportes, args.operaciones)
    if not encontrado:
        print(f"\nNo encontré el registro de operaciones en '{args.reportes}'.")
        print("Necesito un CSV con, al menos, columnas de moneda, fecha de entrada y resultado en R.")
        print("Si sabés cuál es, indicalo:  python exportar_web.py --operaciones reportes/ARCHIVO.csv")
        sys.exit(1)
    ruta_ops, df_ops, cols = encontrado
    print(f"\nOperaciones: {ruta_ops}")
    for campo in ALIAS:
        print(f"  {campo:<11} ← {cols.get(campo, '(no está; se estima o se omite)')}")
    ops = preparar_operaciones(df_ops, cols)
    print(f"  {len(ops)} operaciones en {ops['m'].nunique()} monedas")

    # Monedas: velas + operaciones
    os.makedirs(os.path.join(args.salida, "monedas"), exist_ok=True)
    for viejo in glob.glob(os.path.join(args.salida, "monedas", "*.js")):
        os.remove(viejo)
    monedas, velas_btc = [], None
    print("\nVelas de 4h:")
    for moneda in ops["m"].value_counts().index:
        velas, ruta = encontrar_velas(args.datos, moneda)
        if velas is None:
            print(f"  {moneda:<8} sin velas en '{args.datos}' (se omite de la repetición)")
            continue
        if moneda == "BTC":
            velas_btc = velas
        ops_m = ops[ops["m"] == moneda]
        peso = escribir_js(os.path.join(args.salida, "monedas", f"{moneda}.js"),
                           "ROGELIO_MONEDA", paquete_moneda(velas, ops_m), es_funcion=True, clave=moneda)
        monedas.append({"m": moneda, "n": int(len(ops_m)), "r": round(float(ops_m["r"].sum()), 2),
                        "desde": int(velas["t"].iloc[0].value // 10**9 // 3600),
                        "hasta": int(velas["t"].iloc[-1].value // 10**9 // 3600)})
        print(f"  {moneda:<8} {len(velas):>6} velas, {len(ops_m):>4} operaciones  ({peso / 1e6:.1f} MB)  ← {ruta}")
    if not monedas:
        print("\nNo pude leer ninguna vela. Mandale a Claude una captura de la carpeta 'datos'")
        print("y de las primeras filas de un archivo de velas (por ejemplo BTCUSDT_4h.csv).")
    if velas_btc is None:
        velas_btc, _ = encontrar_velas(args.datos, "BTC")

    # Curva
    curva_oficial, ruta_curva = encontrar_curva_oficial(args.reportes)
    curva_calc = curva_desde_operaciones(ops)
    curva = curva_oficial if curva_oficial is not None else curva_calc
    origen = ("ganancia en USDT de cada operación" if ops["usd"].notna().mean() > 0.9
              else "resultado en R × riesgo por operación")
    print(f"\nCurva de capital: {ruta_curva or 'calculada con la ' + origen}")
    print(f"  Rendimiento anual {estadisticas(curva)['cagr']:.1f}% | peor caída {estadisticas(curva)['caida']:.1f}%"
          f"  (el informe oficial dice {METRICAS_OFICIALES['rendimiento_anual']}% y {METRICAS_OFICIALES['caida_maxima']}%)")

    btc = None
    if velas_btc is not None:
        diario = velas_btc.set_index("t")["c"].resample("D").last().ffill()
        diario = diario[(diario.index >= curva.index[0]) & (diario.index <= curva.index[-1])]
        if len(diario):
            btc = serie_compacta(diario / diario.iloc[0] * 100)

    resumen = {
        "generado": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "demo": bool(args.demo),
        "version": VERSION,
        "autor": AUTOR,
        "enlaces": ENLACES,
        "oficiales": METRICAS_OFICIALES,
        "fuera_de_muestra": INICIO_FUERA_DE_MUESTRA,
        "curva_oficial": curva_oficial is not None,
        "curva": serie_compacta(curva),
        "btc": btc,
        "calculadas": estadisticas(curva),
        "operaciones": resumen_operaciones(ops),
        "monedas": monedas,
        "ops": [{k: v for k, v in op_compacta(o).items() if k in ("m", "e", "te", "ts", "r", "rg")}
                for _, o in ops.iterrows()],
    }
    peso = escribir_js(os.path.join(args.salida, "resumen.js"), "ROGELIO_RESUMEN", resumen)
    print("\nEnlaces de la página:")
    for nombre, url in ENLACES.items():
        aviso = "  <- falta completarlo en exportar_web.py" if "TU_" in url else ""
        print(f"  {nombre:<9} {url}{aviso}")
    print(f"\nListo: {os.path.join(args.salida, 'resumen.js')} ({peso / 1e6:.2f} MB) y {len(monedas)} monedas.")
    if args.demo:
        print("ATENCIÓN: son datos inventados. La página lo avisa arriba.")
    print("Abrí docs/index.html para ver la página.")


if __name__ == "__main__":
    main()
