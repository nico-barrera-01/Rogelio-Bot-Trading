"""
DATOS: descarga velas (en todas las temporalidades de config.TEMPORALIDADES)
e historial de funding de Binance Futuros.
La descarga es INCREMENTAL: si ya tenés datos, solo baja lo nuevo.
Uso:  python datos.py
"""
import os
import ccxt
import pandas as pd
import config as C

exchange = ccxt.binanceusdm({"enableRateLimit": True})


def descargar_velas(par, temporalidad, desde):
    """Todas las velas desde una fecha hasta hoy, de a 1000 por pedido."""
    inicio = exchange.parse8601(desde)
    ahora = exchange.milliseconds()
    duracion_ms = exchange.parse_timeframe(temporalidad) * 1000
    todas = []
    while True:
        velas = exchange.fetch_ohlcv(par, timeframe=temporalidad, since=inicio, limit=1000)
        if not velas:
            break
        todas.extend(velas)
        inicio = velas[-1][0] + duracion_ms
        print(f"  {par}: {len(todas)} velas...", end="\r")
        if inicio >= ahora:
            break

    df = pd.DataFrame(todas, columns=["fecha", "apertura", "maximo", "minimo", "cierre", "volumen"])
    df = df.drop_duplicates(subset="fecha")
    df = df[df["fecha"] + duracion_ms <= ahora]          # solo velas cerradas
    df["fecha"] = pd.to_datetime(df["fecha"], unit="ms", utc=True)
    return df


def descargar_funding(par, desde):
    """Historial de la tasa de funding (se cobra cada 8 horas)."""
    inicio = exchange.parse8601(desde)
    ahora = exchange.milliseconds()
    filas = []
    while True:
        try:
            lote = exchange.fetch_funding_rate_history(par, since=inicio, limit=1000)
        except Exception as error:
            print(f"  No se pudo bajar el funding de {par}: {error}")
            break
        if not lote:
            break
        filas.extend((x["timestamp"], x["fundingRate"]) for x in lote)
        inicio = lote[-1]["timestamp"] + 1
        if inicio >= ahora or len(lote) < 1000:
            break
    df = pd.DataFrame(filas, columns=["fecha", "funding"]).drop_duplicates("fecha")
    df["fecha"] = pd.to_datetime(df["fecha"], unit="ms", utc=True)
    return df


def actualizar(ruta, descargar, desde_defecto):
    """Si el archivo existe, baja solo lo nuevo y lo agrega; si no, baja todo."""
    if os.path.exists(ruta):
        viejo = pd.read_csv(ruta)
        viejo["fecha"] = pd.to_datetime(viejo["fecha"], utc=True, format="mixed")
        desde = viejo["fecha"].max().strftime("%Y-%m-%dT%H:%M:%SZ")
        nuevo = descargar(desde)
        df = pd.concat([viejo, nuevo]).drop_duplicates("fecha", keep="last").sort_values("fecha")
    else:
        df = descargar(desde_defecto)
    df.to_csv(ruta, index=False)
    return df


if __name__ == "__main__":
    os.makedirs(C.CARPETA_DATOS, exist_ok=True)
    exchange.load_markets()
    resumen = []
    for moneda in C.MONEDAS:
        par = f"{moneda}/USDT:USDT"
        if par not in exchange.markets:
            print(f"AVISO: {moneda} no tiene futuros en Binance, se omite.")
            continue
        fila = [moneda]
        for temp in C.TEMPORALIDADES:
            print(f"Descargando {par} {temp}...")
            ruta = os.path.join(C.CARPETA_DATOS, f"{moneda}USDT_{temp}.csv")
            velas = actualizar(ruta, lambda d: descargar_velas(par, temp, d), C.DESDE)
            fila.append(f"{temp}: {len(velas)} velas")
            print()
        funding = actualizar(os.path.join(C.CARPETA_DATOS, f"{moneda}USDT_funding.csv"),
                             lambda d: descargar_funding(par, d), C.DESDE)
        fila.append(f"funding: {len(funding)}")
        resumen.append(fila)

    print("\n================ RESUMEN ================")
    for fila in resumen:
        print(f"{fila[0]:6} " + "  |  ".join(fila[1:]))
