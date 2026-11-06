"""
MOTOR DE FACTORES (v2.5): simula día a día una cartera de factor.

Supuestos (conservadores, como en el resto de Rogelio):
  - La cartera armada al cierre del día D opera durante D+1 (nunca con información del futuro).
  - Entre rebalanceos los pesos "flotan" con los precios (no se reajustan gratis).
  - Cada cambio de posición paga comisión taker + deslizamiento.
  - Los cortos COBRAN el funding cuando es positivo y lo pagan cuando es negativo (al revés los largos).
  - Stop por posición: si el máximo (cortos) o el mínimo (largos) del día toca el stop, se sale a ese
    precio con deslizamiento, y la moneda queda afuera hasta el próximo rebalanceo.
"""
import numpy as np
import pandas as pd
import config as C

COSTO = C.COMISION_TAKER + C.DESLIZAMIENTO


def simular_factor(P, objetivo, stop):
    """Devuelve un DataFrame diario con: rendimiento, exposición bruta, costos y funding cobrado."""
    cierre = P["cierre"].to_numpy(dtype=float)
    maximo = P["maximo"].to_numpy(dtype=float)
    minimo = P["minimo"].to_numpy(dtype=float)
    fund = P["funding"].fillna(0).to_numpy(dtype=float)
    obj = objetivo.to_numpy(dtype=float)
    n, m = cierre.shape

    w = np.zeros(m)                 # peso actual de cada moneda (fracción del capital del factor)
    entrada = np.full(m, np.nan)    # precio de referencia para el stop
    filas = []
    for t in range(1, n):
        prev, hoy = cierre[t - 1], cierre[t]
        r = np.where(np.isfinite(hoy) & np.isfinite(prev), hoy / prev - 1, 0.0)
        r_ef = r.copy()
        costo = 0.0
        abiertas = w != 0

        # ---- stops ----
        if stop:
            cortos = abiertas & (w < 0) & np.isfinite(maximo[t]) & (maximo[t] >= entrada * (1 + stop))
            largos = abiertas & (w > 0) & np.isfinite(minimo[t]) & (minimo[t] <= entrada * (1 - stop))
            for mask, signo in ((cortos, 1), (largos, -1)):
                if mask.any():
                    salida = entrada[mask] * (1 + signo * stop) * (1 + signo * C.DESLIZAMIENTO)
                    r_ef[mask] = salida / prev[mask] - 1
                    costo += np.abs(w[mask]).sum() * C.COMISION_TAKER
        cerradas = (cortos | largos) if stop else np.zeros(m, bool)

        precio = float(np.sum(w * r_ef))
        funding = float(-np.sum(w * fund[t]))
        rend = precio + funding - costo

        # ---- los pesos flotan con los precios ----
        w = np.where(cerradas, 0.0, w * (1 + r) / (1 + rend if rend > -0.99 else 1))
        entrada = np.where(cerradas, np.nan, entrada)
        w = np.where(np.isfinite(hoy), w, 0.0)        # moneda sin dato: fuera

        # ---- rebalanceo al cierre del día ----
        if np.isfinite(obj[t]).all():
            nuevo = np.nan_to_num(obj[t])
            giro = np.abs(nuevo - w).sum()
            rend -= giro * COSTO
            costo += giro * COSTO
            w = nuevo
            entrada = np.where(w != 0, hoy, np.nan)

        filas.append((P["cierre"].index[t], rend, np.abs(w).sum(), costo, funding))
    return pd.DataFrame(filas, columns=["fecha", "rend", "bruta", "costo", "funding"]).set_index("fecha")


def objetivo_volatilidad(rend, bruta, vol_obj=None, ventana=None, tope=None):
    """Escala la exposición para apuntar a una volatilidad anual (Moreira y Muir, 2017).
    La escala de cada semana se calcula SOLO con la volatilidad de los días anteriores."""
    vol_obj = C.VOLATILIDAD_OBJETIVO if vol_obj is None else vol_obj
    ventana = C.VENTANA_VOLATILIDAD if ventana is None else ventana
    tope = C.EXPOSICION_MAXIMA if tope is None else tope
    vol = rend.rolling(ventana, min_periods=ventana // 2).std().shift(1) * np.sqrt(365)
    escala = (vol_obj / vol).clip(upper=tope)
    escala = escala.where(escala.index.dayofweek == 0).ffill().fillna(0)   # se ajusta los lunes
    costo_ajuste = escala.diff().abs().fillna(0) * bruta * COSTO
    return escala * rend - costo_ajuste, escala
