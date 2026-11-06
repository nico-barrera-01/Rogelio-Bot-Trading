"""
FACTORES (v2.5): arma el "panel" diario de las 20 monedas y calcula las carteras objetivo.

Panel diario (a partir de las velas de 4h):
  - el día D va de las 00:00 a las 24:00 UTC; su cierre es el precio a las 24:00.
  - el funding del día D suma los cobros de las 08:00, las 16:00 y las 24:00 de ese día:
    es lo que paga (o cobra) una posición mantenida durante el día D, y se conoce al cierre de D.

Todas las señales del día D usan SOLO información disponible al cierre de D.
La cartera armada al cierre de D gana o pierde con lo que pasa el día D+1.
"""
import os
import numpy as np
import pandas as pd
import config as C


def _leer(ruta):
    df = pd.read_csv(ruta)
    df["fecha"] = pd.to_datetime(df["fecha"], utc=True, format="mixed")
    return df.sort_values("fecha")


def panel_diario():
    cierre, maximo, minimo, funding = {}, {}, {}, {}
    for moneda in C.MONEDAS:
        ruta = os.path.join(C.CARPETA_DATOS, f"{moneda}USDT_4h.csv")
        if not os.path.exists(ruta):
            continue
        v = _leer(ruta).set_index("fecha")
        dia = v.resample("1D")
        completo = dia["cierre"].count() == 6                 # solo días con las 6 velas
        cierre[moneda] = dia["cierre"].last().where(completo)
        maximo[moneda] = dia["maximo"].max().where(completo)
        minimo[moneda] = dia["minimo"].min().where(completo)

        ruta_f = os.path.join(C.CARPETA_DATOS, f"{moneda}USDT_funding.csv")
        if os.path.exists(ruta_f):
            f = _leer(ruta_f)
            # un cobro a las 24:00 pertenece al día que termina: se corre 1 microsegundo hacia atrás
            dia_f = (f["fecha"] - pd.Timedelta(microseconds=1)).dt.floor("D")
            funding[moneda] = f.groupby(dia_f)["funding"].sum()

    P = {
        "cierre": pd.DataFrame(cierre),
        "maximo": pd.DataFrame(maximo),
        "minimo": pd.DataFrame(minimo),
    }
    idx = P["cierre"].index
    fund = pd.DataFrame(funding).reindex(index=idx, columns=P["cierre"].columns)
    P["funding"] = fund.fillna(3 * C.FUNDING_POR_DEFECTO).where(P["cierre"].notna())
    return P


def _inverso_vol(seleccion, vol, total):
    """Reparte 'total' entre las monedas elegidas en proporción inversa a su volatilidad
    (paridad de riesgo: cada moneda aporta un riesgo parecido)."""
    if not seleccion:
        return {}
    inv = 1 / vol[seleccion].clip(lower=1e-4)
    return (total * inv / inv.sum()).to_dict()


def carteras_objetivo(P, nombre, cfg):
    """Devuelve un DataFrame (días x monedas) con los pesos objetivo del factor en cada día
    de rebalanceo (NaN en los días intermedios). Exposición bruta = 1."""
    cierre = P["cierre"]
    rend = cierre.pct_change(fill_method=None)
    vol = rend.rolling(30, min_periods=20).std()
    btc = cierre[C.MONEDA_REFERENCIA]
    bajista_btc = btc < btc.rolling(C.REGIMEN_DIAS).mean()

    if nombre == "carry":
        puntaje = P["funding"].rolling(cfg["ventana_dias"], min_periods=cfg["ventana_dias"]).mean()
    elif nombre == "momentum":
        # puntaje alto = fuerte; los cortos van a las más débiles
        puntaje = cierre.shift(1) / cierre.shift(1 + cfg["ventana_dias"]) - 1
    else:
        raise ValueError(nombre)

    inicio = max(60, cfg["ventana_dias"] + 31)
    pesos = pd.DataFrame(np.nan, index=cierre.index, columns=cierre.columns)
    for i in range(inicio, len(cierre), cfg["rebalanceo_dias"]):
        dia = cierre.index[i]
        validas = puntaje.iloc[i].dropna()
        validas = validas[vol.iloc[i].reindex(validas.index).notna()]
        fila = dict.fromkeys(cierre.columns, 0.0)
        if len(validas) >= 2 * cfg["cantidad"]:
            k = cfg["cantidad"]
            if nombre == "carry":
                cortos = validas[validas > cfg["umbral_diario"]].nlargest(k).index.tolist()
                largos = validas.nsmallest(k).index.tolist()
            else:
                cortos = validas.nsmallest(k).index.tolist()
                largos = validas.nlargest(k).index.tolist()
            largos = [m for m in largos if m not in cortos]

            activo_corto = (not cfg["filtro_regimen"]) or bool(bajista_btc.iloc[i])
            if cfg["sesgo"] == "bajista":
                if activo_corto:
                    fila.update({m: -w for m, w in _inverso_vol(cortos, vol.iloc[i], 1.0).items()})
            else:   # neutral: mitad cortos, mitad largos (si no hay cortos, no hay largos)
                if cortos and activo_corto:
                    fila.update({m: -w for m, w in _inverso_vol(cortos, vol.iloc[i], 0.5).items()})
                    fila.update(_inverso_vol(largos, vol.iloc[i], 0.5))
        pesos.loc[dia] = pd.Series(fila)
    return pesos
