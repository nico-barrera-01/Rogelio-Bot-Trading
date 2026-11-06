"""
PLAN DE CAPITAL: ¿cuándo llego a la meta?
Proyecta mes a mes el capital con el rendimiento objetivo y con un escenario prudente,
sumando los aportes mensuales. Todo se configura en config.py
(CAPITAL_INICIAL, APORTE_MENSUAL, OBJETIVO_ANUAL, META_CAPITAL).

Uso:  python plan_capital.py
      python plan_capital.py 200        (probar con otro aporte mensual)
"""
import sys
import config as C

ESCENARIOS = {
    "objetivo": C.OBJETIVO_ANUAL,
    "prudente (2/3 del objetivo)": C.OBJETIVO_ANUAL * 2 / 3,
}


def proyectar(capital, aporte, anual, meta, max_meses=240):
    r = (1 + anual) ** (1 / 12) - 1
    filas = []
    for mes in range(1, max_meses + 1):
        capital = capital * (1 + r) + aporte
        filas.append((mes, capital, capital * r))
        if capital >= meta:
            break
    return filas


if __name__ == "__main__":
    aporte = float(sys.argv[1]) if len(sys.argv) > 1 else C.APORTE_MENSUAL
    print(f"Capital inicial ${C.CAPITAL_INICIAL:,.0f} | aporte mensual ${aporte:,.0f} | meta ${C.META_CAPITAL:,.0f}\n")
    for nombre, anual in ESCENARIOS.items():
        filas = proyectar(C.CAPITAL_INICIAL, aporte, anual, C.META_CAPITAL)
        mes, final, ganancia = filas[-1]
        print(f"--- Escenario {nombre}: {anual:.1%} anual ---")
        for m, cap, gan in filas:
            if m % 12 == 0:
                print(f"  año {m // 12:2}: capital ${cap:>10,.0f}   ganancia del mes ~${gan:,.0f}")
        if final >= C.META_CAPITAL:
            print(f"  -> Meta alcanzada en {mes} meses ({mes / 12:.1f} años). "
                  f"En ese momento gana ~${ganancia:,.0f} por mes.\n")
        else:
            print("  -> Con estos números la meta no se alcanza en 20 años: hace falta aportar más.\n")
    print("Son proyecciones con rendimiento constante: en la realidad hay meses negativos y meses buenos.")
