"""
CONFIGURACIÓN CENTRAL DE ROGELIO
================================
Todos los parámetros del sistema están acá. Para cambiar el comportamiento
de Rogelio, se modifica este archivo y nada más.
"""

# ---------------------------------------------------------------
# 1. UNIVERSO Y DATOS
# ---------------------------------------------------------------
# Las 20 con las que se diseñaron y probaron todas las reglas
MONEDAS_ORIGINALES = [
    "BTC", "ETH", "XRP", "BNB", "SOL", "DOGE", "ADA", "TRX", "LINK", "AVAX",
    "SUI", "XLM", "BCH", "HBAR", "LTC", "DOT", "TON", "UNI", "AAVE", "NEAR",
]
# v2.6: 20 monedas líquidas que Rogelio NUNCA vio. Las reglas no se tocan: si funcionan acá,
# es una prueba fuera de muestra genuina (y además duplica las oportunidades).
# Si alguna no tiene futuros en Binance, datos.py la omite sola.
MONEDAS_NUEVAS = [
    "ETC", "FIL", "ATOM", "ICP", "APT", "ARB", "OP", "INJ", "ALGO", "VET",
    "SAND", "MANA", "AXS", "CRV", "GRT", "THETA", "XTZ", "ZEC", "LDO", "FET",
]
MONEDAS = MONEDAS_ORIGINALES
MONEDA_REFERENCIA = "BTC"      # el "termómetro" del mercado
TEMPORALIDAD = "4h"
TEMPORALIDADES = ["4h"]        # temporalidades que descarga datos.py (v2.4: solo 4h)
VELAS_POR_DIA = 6
DESDE = "2020-01-01T00:00:00Z"
CARPETA_DATOS = "datos"
CARPETA_REPORTES = "reportes"

# ---------------------------------------------------------------
# 2. PERFIL DE RIESGO (el corazón del sistema)
# ---------------------------------------------------------------
CAPITAL_INICIAL = 1000.0       # USDT
RIESGO_MINIMO = 0.0025         # por debajo de esto no vale la pena operar
# (el riesgo por operación de cada estrategia está en la sección 5)
FRACCION_KELLY = 0.25          # se usa 1/4 de Kelly (Kelly completo es demasiado agresivo)
APALANCAMIENTO_MAXIMO = 5
MARGEN_MANTENIMIENTO = 0.005   # 0,5% aprox. en Binance para posiciones chicas
DISTANCIA_LIQUIDACION_MIN = 2.0  # la liquidación debe quedar al menos 2x más lejos que el stop

MAX_POSICIONES = 6             # posiciones abiertas a la vez, sumando las tres estrategias
MAX_MISMA_DIRECCION = 4        # máximo de longs (o shorts) simultáneos: las criptos se mueven juntas
RIESGO_ABIERTO_MAXIMO = 0.05   # suma del riesgo de todas las posiciones abiertas
PERDIDA_DIARIA_MAXIMA = 0.03   # si se pierde 3% en un día, no se abren más posiciones ese día
DRAWDOWN_CORTE = 0.20          # caída del 20% desde el máximo: Rogelio se apaga (margen para el riesgo calibrado)

# ---------------------------------------------------------------
# 2b. OBJETIVO DE RENDIMIENTO (v2.4)
# ---------------------------------------------------------------
# ESCALA_RIESGO multiplica el riesgo de TODAS las estrategias y el riesgo total de la cuenta.
# 1.0 = posiciones estándar de v2. La elige calibrar.py: el menor valor que alcanza el
# objetivo sin pasar la caída máxima tolerada.
ESCALA_RIESGO = 1.5            # elegida en v2.5 (23,7% anual con 20 monedas)
OBJETIVO_ANUAL = 0.30          # rendimiento anual buscado (v2.6: 30%)
CAIDA_MAXIMA_TOLERADA = 0.15   # caída máxima aceptada en el backtest al calibrar
META_CAPITAL = 10000.0         # meta de capital (USDT)
APORTE_MENSUAL = 0.0           # lo que pensás agregar cada mes (para plan_capital.py)
MODO_INVESTIGACION = True      # True: el backtest NO se detiene en el corte (solo lo registra),
                               # para evaluar los 5 años completos. En vivo siempre se corta.

# ---------------------------------------------------------------
# 3. COSTOS REALES (Binance USDT-M, cuenta estándar)
# ---------------------------------------------------------------
COMISION_TAKER = 0.0005        # 0,05% por orden a mercado
COMISION_MAKER = 0.0002        # 0,02% por orden límite
DESLIZAMIENTO = 0.0003         # 0,03% de precio peor al ejecutar a mercado
FUNDING_POR_DEFECTO = 0.0001   # 0,01% cada 8 h (si no hay historial descargado)

# ---------------------------------------------------------------
# 4. INDICADORES Y ESTRUCTURA
# ---------------------------------------------------------------
EMA_RAPIDA = 50
EMA_LENTA = 200
PERIODO_RSI = 14
PERIODO_ATR = 14
PERIODO_ADX = 14
PERIODO_DONCHIAN = 20
PERIODO_BOLLINGER = 20

VELAS_SWING = 5                # un swing necesita 5 velas a cada lado (se confirma 5 velas después)
VENTANA_NIVELES = 600          # velas hacia atrás para buscar soportes/resistencias (~100 días)
TOLERANCIA_NIVEL_ATR = 0.5     # toques a menos de 0,5 ATR forman el mismo nivel
RECALCULO_NIVELES = 6          # recalcular niveles cada 6 velas (1 día)
VENTANA_PERFIL_VOLUMEN = 180   # velas para el perfil de volumen (~30 días)

ADX_TENDENCIA = 22             # ADX por encima: mercado en tendencia
ADX_RANGO = 18                 # ADX por debajo: mercado en rango

# ---------------------------------------------------------------
# 5. LAS TRES ESTRATEGIAS (v2)
# ---------------------------------------------------------------
# Cada estrategia tiene sus propias reglas, salidas, riesgo y modelo, y se mide por separado.
# Para apagar una: "activa": False.
#
# Parámetros de entrada (las tres usan rupturas de compresión, el setup que ganó en v1.1):
#   lados            -> 1 compras, -1 ventas
#   compresion_pct   -> las bandas de Bollinger tienen que haber estado en el X% más angosto de su historia
#   vol_z_min        -> volumen mínimo de la vela de ruptura (en desvíos sobre su media)
#   funding_max      -> funding medio que se tolera PAGAR desde nuestro lado (None = sin filtro)
#   exigir_btc       -> solo operar si BTC está en tendencia a favor
# Parámetros de salida:
#   parcial          -> % del recorrido al objetivo donde se cierra una parte (None = sin parcial)
#   cierre_parcial   -> qué parte se cierra ahí
#   break_even_R     -> a cuántos R a favor el stop pasa a la entrada (None = nunca)
#   trailing_atr     -> distancia del stop dinámico
#   sin_objetivo     -> True: no hay techo, solo sale por stop dinámico o por tiempo
#   max_velas        -> cierre por tiempo
# Riesgo:
#   riesgo_base / riesgo_max -> % del capital por operación
#   presupuesto_riesgo       -> riesgo total abierto que puede tener esta estrategia
#   max_posiciones           -> posiciones simultáneas de esta estrategia
#   usar_modelo / prob_min   -> filtro del modelo predictivo propio

ESTRATEGIAS = {
    "vendedor": {
        "activa": True,
        "descripcion": "Ventas en rupturas bajistas cuando los compradores están sobrecargados",
        "lados": [-1], "compresion_pct": 0.30, "vol_z_min": 1.0,
        "funding_max": 0.0, "exigir_btc": False,
        "parcial": 0.6, "cierre_parcial": 0.5, "break_even_R": 1.0, "trailing_atr": 2.5,
        "sin_objetivo": False, "rr_defecto": 2.5, "rr_min": 1.5, "rr_max": 4.0, "max_velas": 60,
        "riesgo_base": 0.01, "riesgo_max": 0.0125, "presupuesto_riesgo": 0.03, "max_posiciones": 3,
        "usar_modelo": True, "prob_min": 0.45, "prioridad": 1,
    },
    "comprador": {
        "activa": True,
        "descripcion": "Compras en rupturas alcistas con BTC en tendencia alcista",
        "lados": [1], "compresion_pct": 0.30, "vol_z_min": 1.0,
        "funding_max": 0.0003, "exigir_btc": True,      # en compras el funding casi siempre es positivo:
                                                         # solo se evita cuando está muy alto
        "parcial": 0.6, "cierre_parcial": 0.5, "break_even_R": 1.0, "trailing_atr": 2.5,
        "sin_objetivo": False, "rr_defecto": 2.5, "rr_min": 1.5, "rr_max": 4.0, "max_velas": 60,
        "riesgo_base": 0.01, "riesgo_max": 0.0125, "presupuesto_riesgo": 0.03, "max_posiciones": 3,
        "usar_modelo": True, "prob_min": 0.45, "prioridad": 1,
    },
    "batacazo": {
        "activa": True,
        "descripcion": "Rupturas de compresiones extremas con volumen muy alto, sin techo de ganancia",
        "lados": [1, -1], "compresion_pct": 0.10, "vol_z_min": 2.0,
        "funding_max": 0.0001, "exigir_btc": False,
        "parcial": None, "cierre_parcial": 0.0, "break_even_R": 2.0, "trailing_atr": 3.5,
        "sin_objetivo": True, "rr_defecto": 20.0, "rr_min": 0.0, "rr_max": 20.0,
        "max_velas": 180,                                  # 30 días (60 días empeoró en v2.4)
        "riesgo_base": 0.005, "riesgo_max": 0.005, "presupuesto_riesgo": 0.01, "max_posiciones": 2,
        "usar_modelo": False, "prob_min": 0.0, "prioridad": 2,   # si la misma ruptura dispara A/B y batacazo, entra primero A/B
    },
}

STOP_MIN_ATR = 1.0             # el stop nunca a menos de 1 ATR (el ruido lo sacaría)
STOP_MAX_ATR = 4.0             # ni a más de 4 ATR (el riesgo por unidad sería enorme)
MOVER_STOP_A_ENTRADA = True    # al tomar la parcial, el stop pasa a la entrada

# ---------------------------------------------------------------
# 6. MODELO PREDICTIVO (meta-etiquetado)
# ---------------------------------------------------------------
USAR_MODELO = True             # interruptor general (cada estrategia además tiene el suyo)
MESES_ENTRENAMIENTO_MIN = 12   # el modelo necesita al menos 1 año de historia para empezar
MESES_POR_BLOQUE = 6           # walk-forward: se reentrena cada 6 meses
EMBARGO_VELAS = 60             # separación entre entrenamiento y prueba (evita contaminación)
MIN_OPERACIONES_ENTRENAMIENTO = 120

# ---------------------------------------------------------------
# 7. ESTADÍSTICA Y FEEDBACK
# ---------------------------------------------------------------
SIMULACIONES_MONTECARLO = 5000
NIVEL_CONFIANZA = 0.95
CANTIDAD_PRUEBAS_REALIZADAS = 68 # variantes probadas hasta v2.7 (el veterano cuenta como una)
FECHA_CORTE_VALIDACION = "2024-01-01"  # antes: datos para decidir; después: prueba fuera de muestra
VENTANA_DEGRADACION = 30         # operaciones recientes para detectar si la estrategia se deterioró

# ---------------------------------------------------------------
# 8. EVENTOS
# ---------------------------------------------------------------
ARCHIVO_EVENTOS = "eventos.csv"
DIAS_ANTES_EVENTO = 5
DIAS_DESPUES_EVENTO = 10


# ---------------------------------------------------------------
# 9. MOTOR DE FACTORES (v2.5) - ARCHIVADO: no tuvo ventaja fuera de muestra. Se conserva como referencia.
# ---------------------------------------------------------------
# Un segundo motor, distinto de las rupturas: cada pocos días ordena las 20 monedas
# según un factor y arma una cartera (cortos y, si es neutral, largos), con stop por posición.
#   - CARRY (BIS 2023, "Crypto carry"): el funding alto = especuladores apalancados en compra;
#     el carry alto anticipa caídas. Se vende lo más cargado y se COBRA el funding.
#   - MOMENTUM RELATIVO (Liu, Tsyvinski y Wu): las monedas que vienen más débiles que el resto
#     tienden a seguir más débiles. Se venden las más débiles (y en neutral, se compran las más fuertes).
# Después, un OBJETIVO DE VOLATILIDAD (Moreira y Muir, 2017) ajusta la exposición total:
# más exposición cuando el mercado está tranquilo, menos cuando está turbulento.
#
# sesgo:  "bajista" = solo cortos (el nicho que detectamos) | "neutral" = cortos + largos (cubierto)
# filtro_regimen: los cortos operan solo si BTC está por debajo de su media de REGIMEN_DIAS días

FACTORES = {
    "carry": {
        "activa": True, "sesgo": "bajista", "filtro_regimen": False,
        "rebalanceo_dias": 3,          # cada cuántos días se rearma la cartera
        "cantidad": 4,                 # cuántas monedas por lado
        "ventana_dias": 3,             # funding promedio de los últimos 3 días
        "umbral_diario": 0.0006,       # solo se vende si el funding diario supera 0,06% (0,02% cada 8 h:
                                       # el doble de lo normal = compradores sobrecargados)
        "stop": 0.15,                  # si una posición va 15% en contra, se cierra hasta el próximo rebalanceo
    },
    "momentum": {
        "activa": True, "sesgo": "bajista", "filtro_regimen": True,
        "rebalanceo_dias": 7,
        "cantidad": 4,
        "ventana_dias": 28,            # rendimiento de 28 días (salteando el último día: evita el rebote de corto plazo)
        "stop": 0.15,
    },
}
ASIGNACION_FACTORES = {"carry": 0.5, "momentum": 0.5}   # peso de cada factor dentro del motor
REGIMEN_DIAS = 50                     # media móvil de BTC para el filtro de régimen
VOLATILIDAD_OBJETIVO = 0.25           # volatilidad anual buscada para el motor de factores
VENTANA_VOLATILIDAD = 60              # días para medir la volatilidad realizada
EXPOSICION_MAXIMA = 3.0               # tope de exposición bruta del motor (3 veces su capital)

# Cuenta combinada: qué parte del capital usa cada motor (se rebalancea mes a mes)
PESO_MOTOR_RUPTURAS = 0.5             # v2 (vendedor, comprador, batacazo)
PESO_MOTOR_FACTORES = 0.5             # v2.5 (carry + momentum)

# ---------------------------------------------------------------
# 10. EL VETERANO (v2.7)
# ---------------------------------------------------------------
# Una rutina, no una regla nueva: cada mañana, a la apertura de Londres (08:00 UTC = 05:00 en
# Argentina), Rogelio revisa las señales de las últimas 24 h (vendedor, batacazo, comprador),
# descarta las vencidas o ya "corridas", y elige las MEJORES hasta un máximo por día.
# Según la volatilidad de BTC decide qué tipo de día es:
#   - tranquilo  -> hasta 3 operaciones, pueden quedar abiertas hasta 3 días, objetivo 2,5R
#   - movido     -> hasta 2 operaciones, cortas (hasta 1 día), objetivo 1,5R
#   - turbulento -> no opera
VETERANO = {
    "hora_decision_utc": 8,          # apertura de Londres
    "ventana_senales_h": 24,         # considera señales de las últimas 24 horas
    "max_corrida_atr": 1.0,          # descarta la señal si el precio ya se movió más de 1 ATR a favor
    "riesgo": 0.015,                 # riesgo "medio" por operación (1,5% del capital)
    "max_abiertas": 6,
    "prioridad": ["vendedor", "batacazo", "comprador"],   # el veterano prefiere sus mejores jugadas
    "vol_turbulento": 0.90,          # percentil de volatilidad de BTC por encima del cual no opera
    "vol_movido": 0.60,              # entre 0,60 y 0,90: día movido
    "dia_tranquilo": {"operaciones": 3, "max_velas": 18, "rr": 2.5},
    "dia_movido": {"operaciones": 2, "max_velas": 6, "rr": 1.5},
    "salida": {"parcial": 0.6, "cierre_parcial": 0.5, "break_even_R": 1.0, "trailing_atr": 2.5},
}
