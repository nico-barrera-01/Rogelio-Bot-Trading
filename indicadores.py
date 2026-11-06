"""
INDICADORES TÉCNICOS
Todos se calculan SOLO con información pasada (sin mirar el futuro).
"""
import os
import numpy as np
import pandas as pd
import config as C


# ---------------- Medias y osciladores ----------------
def ema(serie, periodo):
    return serie.ewm(span=periodo, adjust=False).mean()


def rma(serie, periodo):
    """Media de Wilder (la que usan RSI, ATR y ADX)."""
    return serie.ewm(alpha=1 / periodo, adjust=False).mean()


def rsi(serie, periodo=C.PERIODO_RSI):
    cambio = serie.diff()
    subas = rma(cambio.clip(lower=0), periodo)
    bajas = rma(-cambio.clip(upper=0), periodo)
    return 100 - 100 / (1 + subas / bajas.replace(0, np.nan))


def rango_verdadero(df):
    cierre_prev = df["cierre"].shift(1)
    return pd.concat([df["maximo"] - df["minimo"],
                      (df["maximo"] - cierre_prev).abs(),
                      (df["minimo"] - cierre_prev).abs()], axis=1).max(axis=1)


def atr(df, periodo=C.PERIODO_ATR):
    return rma(rango_verdadero(df), periodo)


def adx(df, periodo=C.PERIODO_ADX):
    """ADX: fuerza de la tendencia (no su dirección). +DI/-DI: dirección."""
    sube = df["maximo"].diff()
    baja = -df["minimo"].diff()
    dm_mas = np.where((sube > baja) & (sube > 0), sube, 0.0)
    dm_menos = np.where((baja > sube) & (baja > 0), baja, 0.0)
    tr = rma(rango_verdadero(df), periodo)
    di_mas = 100 * rma(pd.Series(dm_mas, index=df.index), periodo) / tr
    di_menos = 100 * rma(pd.Series(dm_menos, index=df.index), periodo) / tr
    dx = 100 * (di_mas - di_menos).abs() / (di_mas + di_menos).replace(0, np.nan)
    return rma(dx, periodo), di_mas, di_menos


def macd(serie, rapida=12, lenta=26, senal=9):
    linea = ema(serie, rapida) - ema(serie, lenta)
    return linea, linea - ema(linea, senal)


def eficiencia_kaufman(serie, periodo=20):
    """1 = el precio fue en línea recta (tendencia limpia); 0 = puro ruido."""
    desplazamiento = (serie - serie.shift(periodo)).abs()
    recorrido = serie.diff().abs().rolling(periodo).sum()
    return desplazamiento / recorrido.replace(0, np.nan)


def percentil_movil(serie, ventana=500):
    """En qué percentil de su propia historia reciente está el valor (0 a 1)."""
    return serie.rolling(ventana, min_periods=100).rank(pct=True)


# ---------------- Funding ----------------
def agregar_funding(df, moneda):
    ruta = os.path.join(C.CARPETA_DATOS, f"{moneda}USDT_funding.csv")
    if os.path.exists(ruta):
        f = pd.read_csv(ruta)
        # Binance registra el funding con milisegundos variables: se leen todos los formatos
        f["fecha"] = pd.to_datetime(f["fecha"], utc=True, format="mixed").astype(df["fecha"].dtype)
        f = f.sort_values("fecha")
        df = pd.merge_asof(df.sort_values("fecha"), f, on="fecha", direction="backward")
        df["funding"] = df["funding"].fillna(C.FUNDING_POR_DEFECTO)
    else:
        df["funding"] = C.FUNDING_POR_DEFECTO
    # funding promedio de los últimos 3 días: mide si el mercado está "cargado" hacia un lado
    df["funding_medio"] = df["funding"].rolling(18, min_periods=1).mean()
    return df


# ---------------- Todo junto ----------------
def agregar_indicadores(df):
    c = df["cierre"]
    df["ema50"] = ema(c, C.EMA_RAPIDA)
    df["ema200"] = ema(c, C.EMA_LENTA)
    df["pendiente_ema50"] = (df["ema50"] - df["ema50"].shift(6)) / df["ema50"].shift(6)
    df["rsi"] = rsi(c)
    df["atr"] = atr(df)
    df["atr_pct"] = df["atr"] / c
    df["adx"], df["di_mas"], df["di_menos"] = adx(df)
    df["macd"], df["macd_hist"] = macd(c)

    media = c.rolling(C.PERIODO_BOLLINGER).mean()
    desvio = c.rolling(C.PERIODO_BOLLINGER).std()
    df["bb_ancho"] = 4 * desvio / media
    df["bb_ancho_pct"] = percentil_movil(df["bb_ancho"])       # compresión de volatilidad

    # Donchian de las velas ANTERIORES (para detectar rupturas sin trampa)
    df["donchian_max"] = df["maximo"].rolling(C.PERIODO_DONCHIAN).max().shift(1)
    df["donchian_min"] = df["minimo"].rolling(C.PERIODO_DONCHIAN).min().shift(1)

    df["vol_z"] = (df["volumen"] - df["volumen"].rolling(50).mean()) / df["volumen"].rolling(50).std()
    df["obv"] = (np.sign(c.diff()).fillna(0) * df["volumen"]).cumsum()
    df["obv_pendiente"] = df["obv"].diff(12) / df["volumen"].rolling(12).sum()

    df["eficiencia"] = eficiencia_kaufman(c)
    rend = np.log(c).diff()
    df["volatilidad"] = rend.rolling(42).std() * np.sqrt(6 * 365)     # anualizada
    df["vol_pct"] = percentil_movil(df["volatilidad"])
    df["retorno_1d"] = c.pct_change(6)
    df["retorno_7d"] = c.pct_change(42)

    df["hora"] = df["fecha"].dt.hour
    df["dia_semana"] = df["fecha"].dt.dayofweek
    return df


def cargar(moneda, con_indicadores=True):
    ruta = os.path.join(C.CARPETA_DATOS, f"{moneda}USDT_{C.TEMPORALIDAD}.csv")
    df = pd.read_csv(ruta)
    df["fecha"] = pd.to_datetime(df["fecha"], utc=True, format="mixed")
    df = df.sort_values("fecha").reset_index(drop=True)
    df = agregar_funding(df, moneda)
    return agregar_indicadores(df) if con_indicadores else df
