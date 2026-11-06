"""
SEÑALES v2: régimen de mercado + señales de cada estrategia.

Las tres estrategias (config.ESTRATEGIAS) usan rupturas de compresión, el setup que
mostró ventaja dentro y fuera de muestra en v1.1:
  1. El mercado estuvo "dormido" (bandas de Bollinger muy angostas).
  2. El precio rompe el canal de las últimas 20 velas, con volumen alto y ADX subiendo.
  3. Cada estrategia agrega sus filtros (lado, funding, tendencia de BTC) y su forma de salir.

La decisión se toma al CIERRE de una vela y la entrada es en la APERTURA de la siguiente.
(El pullback y la reversión de v1 se retiraron: no mostraron ventaja fuera de muestra.)
"""
import numpy as np
import pandas as pd
import config as C


def agregar_contexto(df, df_ref):
    """Suma la situación de BTC (el termómetro del mercado) a cada moneda."""
    ref = df_ref[["fecha", "cierre", "ema50", "ema200", "retorno_7d", "vol_pct"]].copy()
    ref["btc_tendencia"] = np.select(
        [(ref["cierre"] > ref["ema200"]) & (ref["ema50"] > ref["ema200"]),
         (ref["cierre"] < ref["ema200"]) & (ref["ema50"] < ref["ema200"])], [1, -1], 0)
    ref = ref.rename(columns={"retorno_7d": "btc_retorno_7d", "vol_pct": "btc_vol_pct"})
    ref = ref[["fecha", "btc_tendencia", "btc_retorno_7d", "btc_vol_pct"]]
    df = df.drop(columns=[c for c in ref.columns if c != "fecha" and c in df.columns])
    return df.merge(ref, on="fecha", how="left")


def clasificar_regimen(df):
    alcista = (df["ema50"] > df["ema200"]) & (df["cierre"] > df["ema200"])
    bajista = (df["ema50"] < df["ema200"]) & (df["cierre"] < df["ema200"])
    fuerte = df["adx"] > C.ADX_TENDENCIA
    df["regimen"] = np.select(
        [alcista & fuerte, bajista & fuerte, df["adx"] < C.ADX_RANGO],
        ["tendencia_alcista", "tendencia_bajista", "rango"], "transicion")
    return df


def senales_estrategia(df, nombre, cfg):
    """Devuelve una tabla con las señales de UNA estrategia:
    índice de vela, lado, stop, objetivo y relación riesgo/beneficio planeada."""
    c, a = df["cierre"], df["atr"]
    comprimido = df["bb_ancho_pct"].shift(1).rolling(6).min() < cfg["compresion_pct"]
    con_volumen = df["vol_z"] > cfg["vol_z_min"]
    adx_sube = df["adx"] > df["adx"].shift(3)
    medio_canal = (df["donchian_max"] + df["donchian_min"]) / 2
    validas = pd.Series(True, index=df.index)
    validas.iloc[: C.EMA_LENTA + 100] = False            # indicadores aún sin datos suficientes

    partes = []
    for lado in cfg["lados"]:
        if lado == 1:
            rompe = (c > df["donchian_max"]) & (c > df["ema200"])
        else:
            rompe = (c < df["donchian_min"]) & (c < df["ema200"])
        senal = comprimido & con_volumen & adx_sube & rompe & validas

        if cfg["funding_max"] is not None:               # no operar si NUESTRO lado viene pagando funding
            senal &= lado * df["funding_medio"] <= cfg["funding_max"]
        if cfg["exigir_btc"]:                            # BTC tiene que acompañar
            senal &= df["btc_tendencia"] == lado

        # Stop: en la mitad del canal que se rompió, entre 1 y 4 ATR
        distancia = (lado * (c - medio_canal) / a).clip(C.STOP_MIN_ATR, C.STOP_MAX_ATR)
        riesgo = distancia * a
        stop = c - lado * riesgo

        if cfg["sin_objetivo"]:
            rr = pd.Series(cfg["rr_defecto"], index=df.index)
        else:
            # Objetivo: un poco antes del próximo nivel fuerte, o el R por defecto si no hay nivel
            nivel = df["resistencia"] if lado == 1 else df["soporte"]
            rr_nivel = (lado * (nivel - c) - 0.1 * a) / riesgo
            rr = pd.Series(np.where(nivel.isna(), cfg["rr_defecto"], rr_nivel.clip(upper=cfg["rr_max"])),
                           index=df.index)
            senal &= rr >= cfg["rr_min"]

        idx = np.where(senal.fillna(False).to_numpy())[0]
        if len(idx):
            partes.append(pd.DataFrame({
                "idx_senal": idx, "lado": lado, "estrategia": nombre, "setup": "ruptura",
                "stop_plan": stop.iloc[idx].to_numpy(),
                "objetivo_plan": (c + lado * riesgo * rr).iloc[idx].to_numpy(),
                "rr_plan": rr.iloc[idx].to_numpy(),
            }))
    if not partes:
        return pd.DataFrame(columns=["idx_senal", "lado", "estrategia", "setup",
                                     "stop_plan", "objetivo_plan", "rr_plan"])
    return pd.concat(partes, ignore_index=True)


def generar_senales(df, excluir=None):
    """Señales de todas las estrategias activas. 'excluir' marca velas donde no se opera
    (por ejemplo, alrededor de eventos programados). Agrega una columna 'senal' al df
    solo para graficar (1 compra, -1 venta)."""
    df = clasificar_regimen(df)
    tablas = []
    for nombre, cfg in C.ESTRATEGIAS.items():
        if cfg["activa"]:
            s = senales_estrategia(df, nombre, cfg)
            if excluir is not None and len(s):
                s = s[~excluir.to_numpy()[s["idx_senal"].to_numpy()]]
            tablas.append(s)
    tablas = [t for t in tablas if len(t)]          # las tablas vacías no tienen tipos y rompen la unión
    senales = pd.concat(tablas, ignore_index=True) if tablas else pd.DataFrame(
        columns=["idx_senal", "lado", "estrategia", "setup", "stop_plan", "objetivo_plan", "rr_plan"])
    if len(senales):
        senales = senales.astype({"idx_senal": int, "lado": int})
    df["senal"] = 0
    if len(senales):
        df.loc[df.index[senales["idx_senal"].to_numpy()], "senal"] = senales["lado"].to_numpy()
    return df, senales
