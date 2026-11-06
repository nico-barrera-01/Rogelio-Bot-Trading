"""
MODELO PREDICTIVO: META-ETIQUETADO (López de Prado, "Advances in Financial Machine Learning")

Idea: las reglas (senales.py) deciden DÓNDE podría haber una operación.
El modelo aprende, a partir de miles de operaciones pasadas en las 20 monedas,
QUÉ PROBABILIDAD tiene cada una de terminar ganadora, según el contexto.

Esa probabilidad (p) alimenta dos decisiones:
  1. Filtro: si p es baja, no se opera.
  2. Tamaño: con p y la relación ganancia/pérdida (b) se calcula Kelly fraccional.

Validación walk-forward con embargo: el modelo se entrena SOLO con operaciones que
terminaron antes del período que predice, dejando un margen de separación. Así cada
predicción del backtest se hizo "sin conocer el futuro", igual que en vivo.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
import config as C

CARACTERISTICAS = [
    "lado", "rr_plan", "dist_stop_atr",
    "adx", "di_dif", "rsi", "macd_hist_atr", "eficiencia", "pendiente_ema50",
    "dist_ema50_atr", "dist_ema200_atr", "estructura",
    "dist_soporte_atr", "fuerza_soporte", "dist_resistencia_atr", "fuerza_resistencia", "dist_poc_atr",
    "vol_z", "obv_pendiente", "bb_ancho_pct", "vol_pct", "atr_pct",
    "retorno_1d", "retorno_7d", "funding_medio",
    "btc_tendencia", "btc_retorno_7d", "btc_vol_pct",
    "hora", "dia_semana",
    "setup_pullback", "setup_ruptura", "setup_reversion",
]


def preparar_caracteristicas(df):
    """Columnas derivadas, todas normalizadas por ATR para que sirvan en cualquier moneda."""
    df["di_dif"] = df["di_mas"] - df["di_menos"]
    df["macd_hist_atr"] = df["macd_hist"] / df["atr"]
    df["dist_ema50_atr"] = (df["cierre"] - df["ema50"]) / df["atr"]
    df["dist_ema200_atr"] = (df["cierre"] - df["ema200"]) / df["atr"]
    return df


def unir_caracteristicas(operaciones, df):
    """Agrega a cada operación el contexto de mercado en la vela de la señal."""
    columnas = [c for c in CARACTERISTICAS if c in df.columns and c not in ("lado", "rr_plan")]
    contexto = df.iloc[operaciones["idx_senal"].to_numpy()][columnas].reset_index(drop=True)
    ops = pd.concat([operaciones.reset_index(drop=True), contexto], axis=1)
    ops["dist_stop_atr"] = ops["dist_stop_pct"] * ops["precio_entrada"] / df["atr"].iloc[ops["idx_senal"]].to_numpy()
    for s in ("pullback", "ruptura", "reversion"):
        ops[f"setup_{s}"] = (ops["setup"] == s).astype(int)
    # Para el contexto, las variables "a favor" se miran desde el lado de la operación
    for col in ("btc_tendencia", "estructura", "di_dif", "macd_hist_atr", "retorno_1d", "retorno_7d",
                "btc_retorno_7d", "pendiente_ema50", "dist_ema50_atr", "dist_ema200_atr", "funding_medio"):
        if col in ops:
            ops[col] = ops[col] * ops["lado"]
    return ops


def _nuevo_modelo():
    return HistGradientBoostingClassifier(
        max_depth=3, learning_rate=0.05, max_iter=250, min_samples_leaf=40,
        l2_regularization=1.0, random_state=42)


def walk_forward(ops):
    """Agrega a cada operación p_modelo (probabilidad de ganar) y b_estimado
    (ganancia media / pérdida media), calculados solo con el pasado."""
    ops = ops.sort_values("fecha_entrada").reset_index(drop=True)
    ops["ganadora"] = (ops["R"] > 0).astype(int)
    ops["p_modelo"], ops["b_estimado"], ops["p_base"] = np.nan, np.nan, np.nan
    ops["bloque"] = ""

    inicio = ops["fecha_entrada"].min() + pd.DateOffset(months=C.MESES_ENTRENAMIENTO_MIN)
    fin_total = ops["fecha_entrada"].max()
    embargo = pd.Timedelta(hours=4 * C.EMBARGO_VELAS)
    ultimo = None

    while inicio <= fin_total:
        fin = inicio + pd.DateOffset(months=C.MESES_POR_BLOQUE)
        prueba = (ops["fecha_entrada"] >= inicio) & (ops["fecha_entrada"] < fin)
        entrenamiento = (ops["fecha_salida"] < inicio - embargo) & ops["completa"]
        tr = ops[entrenamiento]

        if prueba.any() and len(tr) >= C.MIN_OPERACIONES_ENTRENAMIENTO:
            modelo = _nuevo_modelo().fit(tr[CARACTERISTICAS], tr["ganadora"])
            ops.loc[prueba, "p_modelo"] = modelo.predict_proba(ops.loc[prueba, CARACTERISTICAS])[:, 1]
            ganancias = tr.loc[tr["R"] > 0, "R"]
            perdidas = -tr.loc[tr["R"] <= 0, "R"]
            ops.loc[prueba, "b_estimado"] = ganancias.mean() / perdidas.mean() if len(perdidas) else np.nan
            ops.loc[prueba, "p_base"] = tr["ganadora"].mean()
            ops.loc[prueba, "bloque"] = f"{inicio.date()} a {fin.date()}"
            print(f"  Bloque {inicio.date()} -> {fin.date()}: entrenado con {len(tr):5} operaciones, "
                  f"predice {prueba.sum():4}")
            ultimo = (modelo, tr)
        inicio = fin
    return ops, ultimo


def importancia_variables(modelo, datos, repeticiones=5):
    """¿Qué variables mira más el modelo? (importancia por permutación)."""
    muestra = datos.tail(3000)
    r = permutation_importance(modelo, muestra[CARACTERISTICAS], muestra["ganadora"],
                               n_repeats=repeticiones, random_state=0, scoring="roc_auc")
    return (pd.DataFrame({"variable": CARACTERISTICAS, "importancia": r.importances_mean})
            .sort_values("importancia", ascending=False).reset_index(drop=True))


def entrenar_modelo_final(ops):
    """Modelo con TODA la historia, para usar en vivo (paper trading / testnet)."""
    datos = ops[ops["completa"]]
    return _nuevo_modelo().fit(datos[CARACTERISTICAS], (datos["R"] > 0).astype(int))
