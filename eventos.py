"""
ESTUDIO DE EVENTOS
Para cada suceso de eventos.csv mide qué pasó con el precio antes y después:
  - retorno acumulado antes del evento (¿el mercado lo anticipó?)
  - retorno el día del evento y en los días siguientes
  - retorno ANORMAL: lo que se movió por encima de su comportamiento normal
  - cambio de volatilidad (¿el evento sacudió el mercado?)
Y luego agrupa por categoría para ver qué tipo de suceso mueve más el precio.

Uso:  python eventos.py           (analiza BTC)
      python eventos.py ETH       (analiza otra moneda)
Para sumar eventos: agregá filas a eventos.csv (fecha, evento, categoría...).
"""
import sys
import numpy as np
import pandas as pd
import config as C
from indicadores import cargar

pd.set_option("display.width", 220)
pd.set_option("display.max_colwidth", 55)


def precios_diarios(moneda):
    df = cargar(moneda, con_indicadores=False)
    return df.set_index("fecha")["cierre"].resample("1D").last().dropna()


def estudio_eventos(moneda=C.MONEDA_REFERENCIA, antes=C.DIAS_ANTES_EVENTO, despues=C.DIAS_DESPUES_EVENTO):
    precio = precios_diarios(moneda)
    rend = np.log(precio).diff()
    eventos = pd.read_csv(C.ARCHIVO_EVENTOS, parse_dates=["fecha"])
    eventos["fecha"] = eventos["fecha"].dt.tz_localize("UTC")
    filas = []
    for _, ev in eventos.iterrows():
        if ev["fecha"] not in rend.index:
            continue
        i = rend.index.get_loc(ev["fecha"])
        if i < 60 + antes or i + despues >= len(rend):
            continue
        normal = rend.iloc[i - 60 - antes:i - antes]           # comportamiento "normal" previo
        media, desvio = normal.mean(), normal.std()
        car_antes = rend.iloc[i - antes:i].sum() - media * antes
        dia = rend.iloc[i] - media
        car_despues = rend.iloc[i + 1:i + 1 + despues].sum() - media * despues
        vol_despues = rend.iloc[i:i + despues].std()
        filas.append({
            "fecha": ev["fecha"].date(), "evento": ev["evento"], "categoria": ev["categoria"],
            f"anormal_{antes}d_antes": np.expm1(car_antes),
            "anormal_dia": np.expm1(dia),
            f"anormal_{despues}d_despues": np.expm1(car_despues),
            "dia_en_desvios": dia / desvio if desvio > 0 else np.nan,   # cuán extremo fue
            "cambio_volatilidad": vol_despues / desvio if desvio > 0 else np.nan,
        })
    tabla = pd.DataFrame(filas)
    if tabla.empty:
        return tabla, tabla
    resumen = tabla.groupby("categoria").agg(
        eventos=("evento", "size"),
        anormal_dia_medio=("anormal_dia", "mean"),
        anormal_despues_medio=(f"anormal_{despues}d_despues", "mean"),
        pct_negativos=("anormal_dia", lambda x: (x < 0).mean()),
        volatilidad_relativa=("cambio_volatilidad", "mean"),
    ).sort_values("volatilidad_relativa", ascending=False)
    return tabla, resumen


def bandera_eventos(fechas, ventana_horas=24):
    """Marca las velas cercanas a un evento PROGRAMADO (para no abrir posiciones ahí)."""
    ev = pd.read_csv(C.ARCHIVO_EVENTOS, parse_dates=["fecha"])
    ev = ev[ev["programado"] == "si"]["fecha"].dt.tz_localize("UTC")
    marca = pd.Series(False, index=fechas.index)
    for f in ev:
        marca |= (fechas >= f - pd.Timedelta(hours=ventana_horas)) & (fechas <= f + pd.Timedelta(hours=ventana_horas))
    return marca


if __name__ == "__main__":
    moneda = sys.argv[1].upper() if len(sys.argv) > 1 else C.MONEDA_REFERENCIA
    tabla, resumen = estudio_eventos(moneda)
    if tabla.empty:
        print("No hay eventos dentro del rango de datos.")
        sys.exit()
    formato = {c: "{:+.1%}".format for c in tabla.columns if c.startswith("anormal")}
    print(f"\n===== ESTUDIO DE EVENTOS: {moneda} =====\n")
    print(tabla.to_string(index=False, formatters={**formato,
          "dia_en_desvios": "{:+.1f}".format, "cambio_volatilidad": "{:.2f}x".format}))
    print("\n===== RESUMEN POR CATEGORÍA =====\n")
    print(resumen.to_string(formatters={
        "anormal_dia_medio": "{:+.2%}".format, "anormal_despues_medio": "{:+.2%}".format,
        "pct_negativos": "{:.0%}".format, "volatilidad_relativa": "{:.2f}x".format}))
    print("\nvolatilidad_relativa > 1 significa que después del evento el mercado se movió más que lo normal.")
