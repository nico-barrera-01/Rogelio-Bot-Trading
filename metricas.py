"""
MÉTRICAS Y ESTADÍSTICA
Las tres variables centrales y todo lo que se deriva de ellas:

  win rate (p)       -> qué proporción de operaciones gana
  relación b         -> cuánto se gana en promedio al ganar vs. cuánto se pierde al perder
  riesgo por op.     -> qué % del capital se arriesga en cada operación

  Expectativa (en R) = p * ganancia_media - (1 - p) * pérdida_media
  Win rate mínimo para no perder = 1 / (1 + b)
  Kelly óptimo = p - (1 - p) / b

Además: intervalos de confianza (Wilson, bayesiano, bootstrap), test t,
Sharpe probabilístico y "deflactado" (López de Prado), Monte Carlo de riesgo de ruina.
"""
import numpy as np
import pandas as pd
from scipy import stats
import config as C


# ============== NIVEL OPERACIÓN (en R) ==============
def wilson(ganadas, n, z=1.96):
    if n == 0:
        return np.nan, np.nan
    p = ganadas / n
    centro = (p + z**2 / (2 * n)) / (1 + z**2 / n)
    margen = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / (1 + z**2 / n)
    return centro - margen, centro + margen


def metricas_operaciones(R, fechas=None):
    """Estadística completa de una serie de resultados en R.
    Si se pasan las fechas, agrega un test t por MES (más honesto: las operaciones del mismo
    mes están correlacionadas porque todas las criptos se mueven juntas)."""
    t_mensual = np.nan
    if fechas is not None:
        serie = pd.Series(np.asarray(R), index=pd.DatetimeIndex(fechas).tz_localize(None))
        mensual = serie.dropna().resample("ME").sum()
        mensual = mensual[mensual != 0]
        if len(mensual) > 2:
            t_mensual = mensual.mean() / mensual.std() * np.sqrt(len(mensual))
    R = pd.Series(R).dropna().to_numpy()
    n = len(R)
    if n < 2:
        return {"operaciones": n}
    gan, per = R[R > 0], R[R <= 0]
    p = len(gan) / n
    g_media = gan.mean() if len(gan) else 0.0
    p_media = -per.mean() if len(per) else 0.0
    b = g_media / p_media if p_media > 0 else np.inf
    expectativa = R.mean()

    # Bayesiano: win rate ~ Beta(1 + ganadas, 1 + perdidas)
    post = stats.beta(1 + len(gan), 1 + len(per))
    wr_equilibrio = 1 / (1 + b) if np.isfinite(b) else 0.0

    # Bootstrap de la expectativa
    rng = np.random.default_rng(0)
    muestras = rng.choice(R, size=(2000, n), replace=True).mean(axis=1)

    # Rachas perdedoras
    racha = maxima = 0
    for r in R:
        racha = racha + 1 if r <= 0 else 0
        maxima = max(maxima, racha)

    t, p_valor = stats.ttest_1samp(R, 0, alternative="greater")
    return {
        "operaciones": n,
        "win_rate": p,
        "win_rate_IC95_wilson": wilson(len(gan), n),
        "win_rate_IC95_bayes": (post.ppf(0.025), post.ppf(0.975)),
        "ganancia_media_R": g_media,
        "perdida_media_R": p_media,
        "relacion_b": b,
        "win_rate_equilibrio": wr_equilibrio,
        "P(win_rate > equilibrio)": 1 - post.cdf(wr_equilibrio),
        "expectativa_R": expectativa,
        "expectativa_IC95_bootstrap": (np.percentile(muestras, 2.5), np.percentile(muestras, 97.5)),
        "test_t": t, "p_valor": p_valor,
        "test_t_mensual (más confiable)": t_mensual,
        "profit_factor": gan.sum() / -per.sum() if len(per) and per.sum() < 0 else np.inf,
        "SQN": np.sqrt(min(n, 100)) * expectativa / R.std(ddof=1),
        "kelly_completo": p - (1 - p) / b if np.isfinite(b) and b > 0 else np.nan,
        "racha_perdedora_maxima": maxima,
    }


# ============== NIVEL CARTERA ==============
def sharpe_probabilistico(rend, sr_ref=0.0):
    """PSR: probabilidad de que el Sharpe verdadero supere sr_ref, corrigiendo
    por asimetría y colas gordas (Bailey y López de Prado, 2012)."""
    n = len(rend)
    if n < 10 or rend.std() == 0:
        return np.nan
    sr = rend.mean() / rend.std()
    g3, g4 = stats.skew(rend), stats.kurtosis(rend, fisher=False)
    denom = np.sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr**2, 1e-12))
    return stats.norm.cdf((sr - sr_ref) * np.sqrt(n - 1) / denom)


def sharpe_deflactado(rend, pruebas=C.CANTIDAD_PRUEBAS_REALIZADAS):
    """DSR: como el PSR, pero exige más cuantas más variantes se probaron
    (si probás 100 estrategias, alguna va a salir bien por suerte)."""
    n = len(rend)
    if n < 10 or pruebas <= 1:
        return sharpe_probabilistico(rend)
    sr = rend.mean() / rend.std()
    g3, g4 = stats.skew(rend), stats.kurtosis(rend, fisher=False)
    var_sr = (1 - g3 * sr + (g4 - 1) / 4 * sr**2) / (n - 1)
    euler = 0.5772156649
    sr_max = np.sqrt(var_sr) * ((1 - euler) * stats.norm.ppf(1 - 1 / pruebas)
                                + euler * stats.norm.ppf(1 - 1 / (pruebas * np.e)))
    return sharpe_probabilistico(rend, sr_max)


def metricas_cartera(curva, capital_inicial=C.CAPITAL_INICIAL):
    diaria = curva.set_index("fecha")["capital"].resample("1D").last().ffill()
    rend = diaria.pct_change().dropna()
    anios = max((diaria.index[-1] - diaria.index[0]).days / 365.25, 1e-9)
    final = diaria.iloc[-1]
    pico = diaria.cummax()
    dd = diaria / pico - 1
    # duración del peor período bajo el máximo
    bajo_agua = (dd < 0).astype(int)
    duracion = bajo_agua.groupby((bajo_agua == 0).cumsum()).sum().max()
    cagr = (final / capital_inicial) ** (1 / anios) - 1 if final > 0 else -1
    abajo = rend[rend < 0].std()
    return {
        "capital_final": final,
        "retorno_total": final / capital_inicial - 1,
        "CAGR": cagr,
        "drawdown_maximo": dd.min(),
        "dias_maximos_bajo_maximo": int(duracion),
        "sharpe_anual": rend.mean() / rend.std() * np.sqrt(365) if rend.std() > 0 else np.nan,
        "sortino_anual": rend.mean() / abajo * np.sqrt(365) if abajo and abajo > 0 else np.nan,
        "calmar": cagr / -dd.min() if dd.min() < 0 else np.nan,
        "sharpe_probabilistico": sharpe_probabilistico(rend.to_numpy()),
        "sharpe_deflactado": sharpe_deflactado(rend.to_numpy()),
    }, diaria, dd


def montecarlo(R, riesgos, simulaciones=C.SIMULACIONES_MONTECARLO):
    """Reordena al azar las operaciones miles de veces: ¿qué tan mal podría haber ido
    con la misma estrategia y otra suerte? Mide el riesgo de ruina."""
    R, riesgos = np.asarray(R), np.asarray(riesgos)
    n = len(R)
    if n < 10:
        return {}
    rng = np.random.default_rng(1)
    idx = rng.integers(0, n, size=(simulaciones, n))
    factores = 1 + R[idx] * riesgos[idx]
    curvas = np.cumprod(factores, axis=1)
    dd = (curvas / np.maximum.accumulate(curvas, axis=1) - 1).min(axis=1)
    final = curvas[:, -1] - 1
    return {
        "retorno_mediano": np.median(final),
        "retorno_percentil_5": np.percentile(final, 5),
        "retorno_percentil_95": np.percentile(final, 95),
        "P(terminar en pérdida)": (final < 0).mean(),
        "drawdown_mediano": np.median(dd),
        "drawdown_percentil_95": np.percentile(dd, 5),
        f"P(drawdown >= {C.DRAWDOWN_CORTE:.0%}, se activa el corte)": (dd <= -C.DRAWDOWN_CORTE).mean(),
    }


def desglose(tabla, columna):
    """Expectativa y win rate por grupo (setup, moneda, lado, régimen...)."""
    g = tabla.groupby(columna)["R"]
    res = pd.DataFrame({
        "operaciones": g.size(), "win_rate": g.apply(lambda x: (x > 0).mean()),
        "expectativa_R": g.mean(), "R_total": g.sum(),
    })
    return res.sort_values("R_total", ascending=False)


def formatear(diccionario):
    lineas = []
    for k, v in diccionario.items():
        if isinstance(v, tuple):
            v = f"[{v[0]:.3f} ; {v[1]:.3f}]"
        elif isinstance(v, (float, np.floating)):
            pct = any(s in k for s in ("win_rate", "retorno", "CAGR", "drawdown", "P(", "kelly", "estuvieron"))
            v = f"{v:.2%}" if pct and abs(v) < 100 else f"{v:,.3f}"
        lineas.append(f"  {k:45} {v}")
    return "\n".join(lineas)


def t_mensual(ops):
    """Test t sobre el R sumado de cada mes (las operaciones del mismo mes están correlacionadas)."""
    if len(ops) < 3:
        return np.nan
    fechas = pd.DatetimeIndex(ops["fecha_entrada"]).tz_localize(None)
    mensual = pd.Series(ops["R"].to_numpy(), index=fechas).resample("ME").sum()
    mensual = mensual[mensual != 0]
    return mensual.mean() / mensual.std() * np.sqrt(len(mensual)) if len(mensual) > 2 else np.nan


def validacion_por_grupo(ops, columna, fecha_corte=C.FECHA_CORTE_VALIDACION):
    """Para cada grupo (por ejemplo, cada estrategia): resultado ANTES y DESPUÉS de la fecha de corte.
    El 'después' son datos que no se usaron para diseñar las reglas: es la prueba que importa."""
    corte = pd.Timestamp(fecha_corte, tz="UTC")
    filas = []
    for grupo, g in ops.groupby(columna):
        fila = {columna: grupo}
        for nombre, parte in (("antes", g[g["fecha_entrada"] < corte]), ("despues", g[g["fecha_entrada"] >= corte])):
            fila[f"ops_{nombre}"] = len(parte)
            fila[f"wr_{nombre}"] = (parte["R"] > 0).mean() if len(parte) else np.nan
            fila[f"expR_{nombre}"] = parte["R"].mean() if len(parte) else np.nan
            fila[f"t_mensual_{nombre}"] = t_mensual(parte)
        filas.append(fila)
    return pd.DataFrame(filas).set_index(columna)


def correlacion_mensual(ops, columna="estrategia"):
    """¿Las estrategias ganan en momentos distintos? Correlación del R mensual entre ellas.
    Cerca de 0 o negativa = se complementan (bueno para suavizar la curva)."""
    d = ops.assign(mes=pd.DatetimeIndex(ops["fecha_entrada"]).tz_localize(None).to_period("M"))
    tabla = d.pivot_table(index="mes", columns=columna, values="R", aggfunc="sum").fillna(0)
    return tabla.corr() if tabla.shape[1] > 1 else None
