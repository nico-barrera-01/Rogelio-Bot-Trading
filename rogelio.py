"""
ROGELIO v2.6 - MOTOR DE RUPTURAS (vendedor, comprador, batacazo) en 40 monedas
Corre todo el análisis de punta a punta, con tres estrategias medidas por separado:
  1. Carga las 20 monedas: indicadores, estructura y perfil de volumen.
  2. Genera las señales de cada estrategia (vendedor, comprador, batacazo).
  3. Simula cada señal vela por vela con las salidas propias de su estrategia.
  4. Entrena un modelo predictivo POR ESTRATEGIA en walk-forward (sin mirar el futuro).
  5. Backtest de cartera con las tres juntas y la gestión de riesgo.
  6. Informe por estrategia: antes/después de 2024, test mensual, correlación,
     y si el batacazo le quita lugar a las otras.

Uso:  python rogelio.py
"""
import os
import time
import warnings
import joblib
import pandas as pd
import config as C
from indicadores import cargar
from estructura import agregar_estructura
from senales import agregar_contexto, generar_senales
from simulador import simular_senales
from modelo import (preparar_caracteristicas, unir_caracteristicas, walk_forward,
                    importancia_variables, entrenar_modelo_final)
from cartera import backtest_cartera
from metricas import (metricas_operaciones, metricas_cartera, montecarlo, desglose, formatear,
                      validacion_por_grupo, correlacion_mensual)
from eventos import bandera_eventos
from graficos import grafico_capital, grafico_distribucion
import feedback

pd.set_option("display.width", 220)
warnings.filterwarnings("ignore", message="Converting to PeriodArray")
FMT = lambda x: f"{x:.3f}"


def generar_candidatas():
    ref = cargar(C.MONEDA_REFERENCIA)
    todas = []
    for moneda in C.MONEDAS:
        ruta = os.path.join(C.CARPETA_DATOS, f"{moneda}USDT_{C.TEMPORALIDAD}.csv")
        if not os.path.exists(ruta):
            print(f"  {moneda}: sin datos, se omite (corré datos.py)")
            continue
        inicio = time.time()
        df = agregar_estructura(cargar(moneda))
        df = agregar_contexto(df, ref)
        df = preparar_caracteristicas(df)
        df, senales = generar_senales(df, excluir=bandera_eventos(df["fecha"]))
        if senales.empty:
            print(f"  {moneda}: sin señales")
            continue
        ops = simular_senales(df, senales, moneda)
        if ops.empty:
            continue
        ops = unir_caracteristicas(ops, df)
        ops["regimen"] = df["regimen"].iloc[ops["idx_senal"]].to_numpy()
        ops["grupo"] = "originales" if moneda in C.MONEDAS_ORIGINALES else "nuevas"
        todas.append(ops)
        conteo = ops["estrategia"].value_counts().to_dict()
        print(f"  {moneda:5}: {conteo}  ({time.time() - inicio:.1f} s)")
    return pd.concat(todas, ignore_index=True)


def main():
    os.makedirs(C.CARPETA_REPORTES, exist_ok=True)
    print("\n[1/5] Analizando monedas y generando señales de las tres estrategias...")
    candidatas = generar_candidatas()
    print(f"\n      Total: {len(candidatas)} operaciones candidatas")

    print("\n[2/5] Entrenando un modelo predictivo por estrategia (walk-forward)...")
    partes, modelos = [], {}
    for nombre, cfg in C.ESTRATEGIAS.items():
        sub = candidatas[candidatas["estrategia"] == nombre]
        if sub.empty:
            continue
        if cfg["usar_modelo"] and C.USAR_MODELO:
            print(f"  -- {nombre} --")
            sub, ultimo = walk_forward(sub)
            modelos[nombre] = ultimo
        else:
            sub = sub.assign(ganadora=(sub["R"] > 0).astype(int), p_modelo=float("nan"),
                             b_estimado=float("nan"), p_base=float("nan"), bloque="")
            print(f"  -- {nombre}: sin modelo (opera por reglas y riesgo fijo)")
        partes.append(sub)
    candidatas = pd.concat(partes, ignore_index=True)
    candidatas.to_csv(os.path.join(C.CARPETA_REPORTES, "candidatas.csv"), index=False)

    print("\n[3/5] Backtest de cartera con las tres estrategias...")
    # Se reserva el primer año para que los modelos aprendan. Desde ahí opera todo:
    # mientras el modelo de una estrategia no tenga datos suficientes, esa estrategia usa su riesgo base.
    inicio = candidatas["fecha_entrada"].min() + pd.DateOffset(months=C.MESES_ENTRENAMIENTO_MIN)
    periodo = candidatas[candidatas["fecha_entrada"] >= inicio]
    tabla, curva, rechazos, corte, extra = backtest_cartera(periodo, usar_modelo=C.USAR_MODELO)
    tabla_sin, curva_sin, _, corte_sin, _ = backtest_cartera(periodo, usar_modelo=False)
    if tabla.empty:
        print("El backtest no ejecutó ninguna operación. Revisá la configuración.")
        return
    tabla.to_csv(os.path.join(C.CARPETA_REPORTES, "operaciones.csv"), index=False)

    print("\n[4/5] Estadística...")
    m_cart, diaria, dd = metricas_cartera(curva)
    m_cart_sin, _, _ = metricas_cartera(curva_sin)
    completas = candidatas[candidatas["completa"]]
    inf = ["=" * 78,
           f"ROGELIO v2.7 - INFORME   ({tabla['fecha_entrada'].min().date()} a "
           f"{tabla['fecha_salida'].max().date()})",
           "=" * 78]

    inf.append("\n######## 1. CADA ESTRATEGIA POR SEPARADO ########")
    inf.append(f"\n--- Señales de cada estrategia ANTES de modelo y riesgo (corte de validación: "
               f"{C.FECHA_CORTE_VALIDACION}) ---")
    inf.append(validacion_por_grupo(completas, "estrategia").to_string(float_format=FMT))
    inf.append("\n--- Operaciones EJECUTADAS por Rogelio, por estrategia ---")
    inf.append(validacion_por_grupo(tabla, "estrategia").to_string(float_format=FMT))

    inf.append("\n######## 1b. PRUEBA FUERA DE MUESTRA: MONEDAS NUEVAS (las reglas nunca las vieron) ########")
    inf.append("\n--- Señales antes de modelo y riesgo, por grupo de monedas ---")
    inf.append(validacion_por_grupo(completas, "grupo").to_string(float_format=FMT))
    inf.append("\n--- Señales por estrategia y grupo ---")
    cruce = completas.assign(estrategia_grupo=completas["estrategia"] + " / " + completas["grupo"])
    inf.append(validacion_por_grupo(cruce, "estrategia_grupo").to_string(float_format=FMT))
    inf.append("\n--- Operaciones EJECUTADAS, por grupo ---")
    inf.append(validacion_por_grupo(tabla, "grupo").to_string(float_format=FMT))
    pnl_grupo = tabla.groupby("grupo")["pnl"].sum()
    inf.append("  Ganancia en USDT por grupo: " + ", ".join(f"{g}: {v:,.0f}" for g, v in pnl_grupo.items()))
    for nombre in C.ESTRATEGIAS:
        sub = tabla[tabla["estrategia"] == nombre]
        if len(sub) < 2:
            inf.append(f"\n>>> {nombre.upper()}: muy pocas operaciones ejecutadas ({len(sub)})")
            continue
        inf.append(f"\n>>> {nombre.upper()}  ({C.ESTRATEGIAS[nombre]['descripcion']})")
        inf.append(formatear(metricas_operaciones(sub["R"], sub["fecha_entrada"])))
        inf.append(f"  {'ganancia en USDT':45} {sub['pnl'].sum():,.1f}")
        inf.append(f"  {'riesgo medio por operación':45} {sub['riesgo_pct'].mean():.2%}")

    corr = correlacion_mensual(tabla)
    if corr is not None:
        inf.append("\n--- Correlación mensual entre estrategias (cerca de 0 o negativa = se complementan) ---")
        inf.append(corr.to_string(float_format=lambda x: f"{x:+.2f}"))

    inf.append("\n--- ¿El batacazo le quita lugar a las otras? ---")
    n_bloq = extra["bloqueos_por_batacazo"]
    n_ab = (tabla["estrategia"] != "batacazo").sum()
    inf.append(f"  Operaciones de vendedor/comprador frenadas mientras el batacazo ocupaba lugar: {n_bloq}")
    inf.append(f"  (sobre {n_ab} operaciones ejecutadas de vendedor/comprador)")
    if n_ab and n_bloq / max(n_ab, 1) > 0.10:
        inf.append("  ATENCIÓN: el batacazo frena más del 10%: considerar bajar su presupuesto o sacarlo.")
    else:
        inf.append("  El batacazo no interfiere de forma relevante.")

    inf.append("\n######## 2. LA CUENTA COMPLETA (las tres juntas) ########")
    inf.append("\n--- OPERACIONES EJECUTADAS ---")
    inf.append(formatear(metricas_operaciones(tabla["R"], tabla["fecha_entrada"])))
    inf.append(f"  {'apalancamiento medio usado':45} {tabla['apalancamiento'].mean():.1f}x")
    inf.append(f"\n--- CARTERA CON MODELOS (escala de riesgo {C.ESCALA_RIESGO:.2f}) ---")
    inf.append(formatear(m_cart))
    alcanza = "SÍ" if m_cart["CAGR"] >= C.OBJETIVO_ANUAL else "NO"
    inf.append(f"  {'¿alcanza el objetivo de ' + format(C.OBJETIVO_ANUAL, '.0%') + ' anual?':45} {alcanza}")
    inf.append("\n--- CARTERA SOLO REGLAS (sin modelos, riesgo fijo) ---")
    inf.append(formatear(m_cart_sin))
    if corte or corte_sin:
        modo = "(modo investigación: se registró y el backtest siguió)" if C.MODO_INVESTIGACION else ""
        inf.append(f"\n  CORTE POR DRAWDOWN {modo}: con modelos {corte}, sin modelos {corte_sin}")
    inf.append("\n--- MONTE CARLO (5.000 órdenes distintas de las mismas operaciones) ---")
    inf.append(formatear(montecarlo(tabla["R"], tabla["riesgo_pct"])))
    inf.append("\n--- RESULTADO POR AÑO ---")
    por_anio = tabla.assign(anio=tabla["fecha_entrada"].dt.year).pivot_table(
        index="anio", columns="estrategia", values="pnl", aggfunc="sum", margins=True, margins_name="TOTAL")
    inf.append(por_anio.to_string(float_format=lambda x: f"{x:,.0f}"))
    inf.append("\n--- OPERACIONES DESCARTADAS ---")
    inf += [f"  {k:50} {v}" for k, v in sorted(rechazos.items(), key=lambda x: -x[1])]
    for nombre, ultimo in modelos.items():
        if ultimo:
            inf.append(f"\n--- VARIABLES MÁS IMPORTANTES: modelo de {nombre} ---")
            inf.append(importancia_variables(*ultimo).head(8).to_string(float_format=lambda x: f"{x:.4f}"))

    texto = "\n".join(inf)
    print(texto)
    with open(os.path.join(C.CARPETA_REPORTES, "informe.txt"), "w", encoding="utf-8") as f:
        f.write(texto)

    print("\n[5/5] Feedback, gráficos y modelos finales...")
    feedback.informe(tabla)
    grafico_capital(curva, curva_sin, dd, os.path.join(C.CARPETA_REPORTES, "curva_capital.png"), tabla)
    grafico_distribucion(tabla, os.path.join(C.CARPETA_REPORTES, "distribucion_R.png"))
    for nombre, cfg in C.ESTRATEGIAS.items():
        sub = candidatas[candidatas["estrategia"] == nombre]
        if cfg["usar_modelo"] and C.USAR_MODELO and sub["completa"].sum() >= C.MIN_OPERACIONES_ENTRENAMIENTO:
            joblib.dump(entrenar_modelo_final(sub), os.path.join(C.CARPETA_REPORTES, f"modelo_{nombre}.pkl"))
    print(f"\nListo. Todo quedó en la carpeta '{C.CARPETA_REPORTES}'.")


if __name__ == "__main__":
    main()
