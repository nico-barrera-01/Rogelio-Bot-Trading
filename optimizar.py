"""
OPTIMIZACIÓN HONESTA, POR ESTRATEGIA (v2)
Para cada estrategia prueba algunas variantes de SALIDA (las entradas no se tocan).
La mejor se elige SOLO con los datos anteriores a FECHA_CORTE_VALIDACION y después
se mira cómo le fue en los datos posteriores, que no participaron de la elección.

Uso:  python optimizar.py              (todas las estrategias)
      python optimizar.py batacazo     (solo una)
"""
import sys
import copy
import warnings
import numpy as np
import pandas as pd
import config as C
from indicadores import cargar
from estructura import agregar_estructura
from senales import agregar_contexto, generar_senales
from simulador import simular_senales
from eventos import bandera_eventos
from metricas import t_mensual

warnings.filterwarnings("ignore", message="Converting to PeriodArray")
pd.set_option("display.width", 220)

# Variantes de salida a probar para cada estrategia (cambian solo estas claves)
VARIANTES = {
    "vendedor": [
        {"parcial": 0.6, "cierre_parcial": 0.5, "break_even_R": 1.0},
        {"parcial": 0.8, "cierre_parcial": 0.5, "break_even_R": 1.0},
        {"parcial": None, "cierre_parcial": 0.0, "break_even_R": 1.0},
        {"parcial": 0.6, "cierre_parcial": 0.5, "break_even_R": None},
    ],
    "comprador": [
        {"parcial": 0.6, "cierre_parcial": 0.5, "break_even_R": 1.0},
        {"parcial": 0.8, "cierre_parcial": 0.5, "break_even_R": 1.0},
        {"parcial": None, "cierre_parcial": 0.0, "break_even_R": 1.0},
        {"parcial": 0.6, "cierre_parcial": 0.5, "break_even_R": None},
    ],
    "batacazo": [
        {"break_even_R": 2.0, "trailing_atr": 3.5},
        {"break_even_R": 1.5, "trailing_atr": 3.0},
        {"break_even_R": 2.0, "trailing_atr": 5.0},
        {"break_even_R": 3.0, "trailing_atr": 4.0},
    ],
}


def preparar_todo():
    ref = cargar(C.MONEDA_REFERENCIA)
    datos = []
    for moneda in C.MONEDAS:
        try:
            df = agregar_contexto(agregar_estructura(cargar(moneda)), ref)
        except FileNotFoundError:
            continue
        df, senales = generar_senales(df, excluir=bandera_eventos(df["fecha"]))
        datos.append((moneda, df, senales))
        print(f"  {moneda} listo")
    return datos


def evaluar(ops, corte):
    filas = {}
    for nombre, parte in (("antes", ops[ops["fecha_entrada"] < corte]),
                          ("despues", ops[ops["fecha_entrada"] >= corte])):
        filas[f"ops_{nombre}"] = len(parte)
        filas[f"wr_{nombre}"] = (parte["R"] > 0).mean() if len(parte) else np.nan
        filas[f"expR_{nombre}"] = parte["R"].mean() if len(parte) else np.nan
        filas[f"t_mensual_{nombre}"] = t_mensual(parte)
    return filas


if __name__ == "__main__":
    elegidas = [sys.argv[1]] if len(sys.argv) > 1 else list(VARIANTES)
    corte = pd.Timestamp(C.FECHA_CORTE_VALIDACION, tz="UTC")
    print("Preparando señales...")
    datos = preparar_todo()
    original = copy.deepcopy(C.ESTRATEGIAS)
    total_variantes = 0

    for nombre in elegidas:
        if nombre not in C.ESTRATEGIAS or not C.ESTRATEGIAS[nombre]["activa"]:
            continue
        filas = []
        for variante in VARIANTES[nombre]:
            C.ESTRATEGIAS[nombre] = {**original[nombre], **variante}
            partes = [simular_senales(df, s[s["estrategia"] == nombre], m) for m, df, s in datos]
            ops = pd.concat([p for p in partes if len(p)], ignore_index=True)
            ops = ops[ops["completa"]]
            filas.append({"variante": ", ".join(f"{k}={v}" for k, v in variante.items()), **evaluar(ops, corte)})
            total_variantes += 1
        C.ESTRATEGIAS[nombre] = original[nombre]

        tabla = pd.DataFrame(filas).sort_values("expR_antes", ascending=False)
        print(f"\n================ {nombre.upper()} (ordenado por datos ANTERIORES a {corte.date()}) ================")
        print(tabla.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
        mejor = tabla.iloc[0]
        print(f"Elegida con datos anteriores: {mejor['variante']}")
        print(f"Fuera de muestra: expectativa {mejor['expR_despues']:+.3f}R, "
              f"t mensual {mejor['t_mensual_despues']:.2f}  (mayor a 2 = señal razonable)")

    print(f"\nSe probaron {total_variantes} variantes: sumalas a CANTIDAD_PRUEBAS_REALIZADAS en config.py.")
