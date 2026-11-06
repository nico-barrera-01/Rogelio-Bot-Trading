"""
ESTRUCTURA DE MERCADO
- Swings (máximos y mínimos relevantes), confirmados SIN mirar el futuro.
- Estructura: máximos y mínimos crecientes (alcista) o decrecientes (bajista).
- Soportes y resistencias por agrupamiento de swings, con medida de fuerza.
- Perfil de volumen: POC (precio con más volumen) y zona de valor (70% del volumen).
"""
import numpy as np
import pandas as pd
import config as C


def detectar_swings(df, n=C.VELAS_SWING):
    """Un swing high es un máximo más alto que las n velas de cada lado.
    Se confirma recién n velas después: ese es el momento en que Rogelio se entera."""
    ventana = 2 * n + 1
    es_sh = df["maximo"] == df["maximo"].rolling(ventana, center=True).max()
    es_sl = df["minimo"] == df["minimo"].rolling(ventana, center=True).min()
    df["swing_high"] = es_sh            # solo para graficar (posición real del swing)
    df["swing_low"] = es_sl

    # Versión "en vivo": el precio del swing aparece n velas después
    sh_conf = df["maximo"].where(es_sh).shift(n)
    sl_conf = df["minimo"].where(es_sl).shift(n)
    for nombre, serie in (("sh", sh_conf), ("sl", sl_conf)):
        eventos = serie.dropna()
        df[f"ult_{nombre}"] = eventos.reindex(df.index).ffill()
        df[f"prev_{nombre}"] = eventos.shift(1).reindex(df.index).ffill()

    sube = (df["ult_sh"] > df["prev_sh"]) & (df["ult_sl"] > df["prev_sl"])
    baja = (df["ult_sh"] < df["prev_sh"]) & (df["ult_sl"] < df["prev_sl"])
    df["estructura"] = np.select([sube, baja], [1, -1], 0)   # 1 alcista, -1 bajista, 0 mixta
    return df


def _agrupar_niveles(precios, posiciones, inicio_ventana, tolerancia):
    """Agrupa toques cercanos. Devuelve lista de (precio, toques, fuerza)."""
    orden = np.argsort(precios)
    precios, posiciones = precios[orden], posiciones[orden]
    niveles, grupo = [], [0]
    for i in range(1, len(precios) + 1):
        if i == len(precios) or precios[i] - precios[grupo[0]] > tolerancia:
            if len(grupo) >= 2:                     # un solo toque no es un nivel
                p = precios[grupo]
                recencia = (posiciones[grupo] - inicio_ventana) / C.VENTANA_NIVELES
                fuerza = float(np.sum(0.5 + recencia))   # cada toque suma; los recientes más
                niveles.append((float(p.mean()), len(grupo), fuerza))
            grupo = [i]
        else:
            grupo.append(i)
    return niveles


def detectar_niveles(df):
    """Para cada vela: soporte más cercano debajo y resistencia más cercana arriba,
    usando SOLO swings ya confirmados en ese momento."""
    n = C.VELAS_SWING
    idx_sh = np.where(df["swing_high"].to_numpy())[0]
    idx_sl = np.where(df["swing_low"].to_numpy())[0]
    piv_idx = np.concatenate([idx_sh, idx_sl])
    piv_precio = np.concatenate([df["maximo"].to_numpy()[idx_sh], df["minimo"].to_numpy()[idx_sl]])
    piv_conf = piv_idx + n                          # cuándo se conoce cada swing

    cierre = df["cierre"].to_numpy()
    atr_ = df["atr"].to_numpy()
    largo = len(df)
    sop_p, sop_f, res_p, res_f = (np.full(largo, np.nan) for _ in range(4))
    ultimos_niveles = []

    for t in range(C.VENTANA_NIVELES // 4, largo, C.RECALCULO_NIVELES):
        if np.isnan(atr_[t]):
            continue
        inicio = t - C.VENTANA_NIVELES
        mascara = (piv_conf <= t) & (piv_idx >= inicio)
        if mascara.sum() < 2:
            continue
        niveles = _agrupar_niveles(piv_precio[mascara], piv_idx[mascara], inicio,
                                   atr_[t] * C.TOLERANCIA_NIVEL_ATR)
        if not niveles:
            continue
        ultimos_niveles = niveles
        precios_niv = np.array([x[0] for x in niveles])
        fuerzas = np.array([x[2] for x in niveles])
        for k in range(t, min(t + C.RECALCULO_NIVELES, largo)):
            abajo = precios_niv < cierre[k]
            arriba = ~abajo
            if abajo.any():
                j = np.argmax(np.where(abajo, precios_niv, -np.inf))
                sop_p[k], sop_f[k] = precios_niv[j], fuerzas[j]
            if arriba.any():
                j = np.argmin(np.where(arriba, precios_niv, np.inf))
                res_p[k], res_f[k] = precios_niv[j], fuerzas[j]

    df["soporte"], df["fuerza_soporte"] = sop_p, sop_f
    df["resistencia"], df["fuerza_resistencia"] = res_p, res_f
    df["dist_soporte_atr"] = (df["cierre"] - df["soporte"]) / df["atr"]
    df["dist_resistencia_atr"] = (df["resistencia"] - df["cierre"]) / df["atr"]
    df.attrs["niveles_actuales"] = ultimos_niveles
    return df


def perfil_volumen(df, ventana=C.VENTANA_PERFIL_VOLUMEN, cajas=40):
    """POC: precio donde más se negoció. VAH/VAL: límites del 70% del volumen."""
    tipico = ((df["maximo"] + df["minimo"] + df["cierre"]) / 3).to_numpy()
    volumen = df["volumen"].to_numpy()
    largo = len(df)
    poc, vah, val = (np.full(largo, np.nan) for _ in range(3))
    for t in range(ventana, largo, C.RECALCULO_NIVELES):
        p, v = tipico[t - ventana:t + 1], volumen[t - ventana:t + 1]
        hist, bordes = np.histogram(p, bins=cajas, weights=v)
        centros = (bordes[:-1] + bordes[1:]) / 2
        i_poc = int(np.argmax(hist))
        # expandir desde el POC hasta juntar el 70% del volumen
        lo = hi = i_poc
        acumulado, total = hist[i_poc], hist.sum()
        while acumulado < 0.7 * total and (lo > 0 or hi < cajas - 1):
            abajo = hist[lo - 1] if lo > 0 else -1
            arriba = hist[hi + 1] if hi < cajas - 1 else -1
            if arriba >= abajo:
                hi += 1
                acumulado += hist[hi]
            else:
                lo -= 1
                acumulado += hist[lo]
        fin = min(t + C.RECALCULO_NIVELES, largo)
        poc[t:fin], vah[t:fin], val[t:fin] = centros[i_poc], bordes[hi + 1], bordes[lo]
    df["poc"], df["vah"], df["val"] = poc, vah, val
    df["dist_poc_atr"] = (df["cierre"] - df["poc"]) / df["atr"]
    return df


def agregar_estructura(df):
    df = detectar_swings(df)
    df = detectar_niveles(df)
    df = perfil_volumen(df)
    return df
