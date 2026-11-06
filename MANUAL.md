# Manual de Rogelio — versión 2.7

Agente de análisis y trading de futuros cripto (Binance USDT-M, velas de 4 horas, 20 monedas).

## Versión 2.7: el veterano

Una rutina diaria en lugar de reaccionar a cada señal (`python veterano.py`, después de `python rogelio.py`):
- **08:00 UTC (05:00 en Argentina), apertura de Londres:** Rogelio mira la volatilidad de BTC y decide el tipo de día.
  - **Tranquilo** (volatilidad bajo el percentil 60): hasta 3 operaciones, pueden durar hasta 3 días, objetivo 2,5R.
  - **Movido** (percentil 60–90): hasta 2 operaciones cortas (hasta 1 día), objetivo 1,5R.
  - **Turbulento** (sobre el percentil 90): no opera.
- **Candidatas:** las señales de las últimas 24 h de vendedor, batacazo y comprador que no tocaron el stop, que el precio no "corrió" más de 1 ATR y que el modelo aprueba.
- **Selección por calidad:** primero vendedor, después batacazo, después comprador; dentro de cada una, por probabilidad del modelo. Es la respuesta a la lección de v2.6 (no repartir por orden de llegada).
- **Riesgo medio:** 1,5% por operación, máximo 6 abiertas, una por moneda.
- Compara 20 monedas contra 40 y deja `informe_veterano.txt` y `curva_veterano.png` en reportes.

Todo se ajusta en la sección 10 de config.py (`VETERANO`).

## Versión 2.6: 40 monedas, objetivo 30% anual

- **Mismas reglas, el doble de mercado:** se suman 20 monedas líquidas que Rogelio nunca vio (`MONEDAS_NUEVAS`). Ninguna regla se ajustó con ellas, así que su resultado es una **prueba fuera de muestra genuina**, además de más oportunidades de operar.
- **Nueva sección 1b del informe:** resultados de las monedas originales contra las nuevas, por estrategia y antes/después de 2024.
- **Objetivo 30%** (`OBJETIVO_ANUAL`), con `ESCALA_RIESGO = 1.5` de partida. `calibrar.py` dice qué escala alcanza el objetivo.
- **Corrección:** las monedas en las que una estrategia no daba ninguna señal podían cortar el programa. Ahora se manejan bien.
- El motor de factores de v2.5 queda archivado (no tuvo ventaja fuera de muestra).

## Versión 2.5: dos motores (rupturas + factores), objetivo 25% anual

**Motor 1 — rupturas (v2):** vendedor, comprador y batacazo en 4h, exactamente como en v2 (batacazo a 30 días: los 60 días empeoraron la caída en v2.4). Se corre con `python rogelio.py`.

**Motor 2 — factores (nuevo):** en vez de esperar una señal puntual, cada pocos días ordena las 20 monedas y arma una cartera.
- **Carry** (BIS, "Crypto carry", 2023): el funding alto refleja especuladores apalancados en compra, y el carry alto anticipa caídas. Rogelio vende las monedas con funding más cargado (más del doble de lo normal) y cobra ese funding mientras espera. Rebalanceo cada 3 días.
- **Momentum relativo** (Liu, Tsyvinski y Wu, "Common Risk Factors in Cryptocurrency"): las monedas más débiles del último mes tienden a seguir débiles. Rogelio vende las 4 más débiles cuando BTC está bajo su media de 50 días. Rebalanceo semanal.
- **Sesgo** configurable por factor: "bajista" (solo cortos, el nicho detectado) o "neutral" (cortos + largos, cubierto contra el mercado).
- **Pesos por paridad de riesgo:** cada moneda pesa en proporción inversa a su volatilidad.
- **Stop por posición:** 15% en contra; la moneda queda afuera hasta el próximo rebalanceo.
- **Objetivo de volatilidad** (Moreira y Muir, 2017): la exposición se ajusta cada lunes según la volatilidad de los 60 días anteriores. Más exposición en calma, menos en turbulencia. Tope: 3 veces el capital del motor.

**Cuenta combinada:** 50% del capital en cada motor. Si se mueven distinto, la curva total se suaviza y se puede apuntar más alto con la misma caída.

**La cuenta del 25%:** rendimiento ≈ Sharpe × volatilidad. Con Sharpe 1 hace falta ~25% de volatilidad; con Sharpe 1,25, ~20%. Por eso v2.5 busca subir el Sharpe combinando motores distintos, y después calibra la volatilidad.

Flujo: `python rogelio.py` → `python v25.py` → poner la VOLATILIDAD_OBJETIVO recomendada en config.py → `python v25.py`.

Prueba anti-trampa: en datos aleatorios sin ventaja (6 semillas, funding de media cero), las cuatro variantes del motor de factores dan rendimiento cero o negativo, como corresponde.

## Versión 2.4: volver a la base validada (v2) + calibración

v2.3 rindió 8,9% anual (contra 15,9% de v2) porque arrastraba cambios de v2.1 que nunca se habían probado por separado (riesgo en rampa, límite de dirección por riesgo, modelos sin el día de la semana) y había sacado al comprador, que aportaba diversificación.

v2.4 parte del código EXACTO de v2 (vendedor, comprador y batacazo en 4h, con su gestión de riesgo original) y suma solo:
- **Batacazo con plazo de hasta 60 días** (la única mejora medida en v2.2).
- **ESCALA_RIESGO, calibrar.py y plan_capital.py** para apuntar al 18% anual y a la meta de USD 10.000.
- **Corte por caída del 20%** y datos.py incremental (solo 4h).

## Versión 2.3: el candidato para el testnet

**Meta:** llegar a USD 10.000 con un rendimiento sostenible de 15–20% anual (ideal: 18%).

- **Estrategias activas:** vendedor 4h (el núcleo, con mejor evidencia) y batacazo 4h con plazo de hasta 60 días (la mejora real de v2.2).
- **En pausa** (configuración guardada): comprador (sin ventaja propia fuera de muestra), vendedor 1h y híbrido (en 1 hora la ventaja cae a menos de la mitad).
- **ESCALA_RIESGO** (config.py): multiplica el riesgo de todas las estrategias y los límites de la cuenta. Es la palanca para alcanzar el objetivo de rendimiento.
- **calibrar.py:** prueba escalas de 1,0 a 2,5 sobre las operaciones del último backtest y recomienda la menor que alcanza el 18% anual sin pasar el 15% de caída máxima. Si no existe, lo dice.
- **plan_capital.py:** proyecta cuándo se llega a la meta de USD 10.000 según capital inicial, aporte mensual y rendimiento (objetivo y prudente).
- **Corte por caída:** 20%, para dar margen al riesgo calibrado.

Flujo: `python rogelio.py` → `python calibrar.py` → poner la escala recomendada en config.py → `python rogelio.py` → `python plan_capital.py 200` (con tu aporte mensual).

## Cambios de la versión 2.2: foco en ventas, con frecuencia de 1 hora

- **Nueva estrategia principal "vendedor_1h":** las mismas reglas del vendedor de v2 (ruptura bajista, filtro de funding, parcial al 60%, break-even a +1R), en velas de 1 hora. Tiene el mayor presupuesto (4% de riesgo, hasta 4 posiciones).
- **Posiciones estándar:** todas las estrategias vuelven al riesgo de v2 (1% de base, hasta 1,25% con alta convicción del modelo). El batacazo sigue en 0,5%.
- **Comprador con menos peso:** presupuesto de 2% y hasta 2 posiciones.
- **Batacazo con plazo más largo:** puede mantener una operación hasta 60 días si la tendencia sigue (antes, 30).
- **Híbrido en observación** (`"activa": False`): en v2.1 subió la ganancia pero con caídas del 28% y casi todo concentrado en 2024.
- **Cuenta:** corte por caída de vuelta al 15% y 6% de riesgo total abierto.
- **Corrección en optimizar.py:** las variantes que cambian el objetivo ahora recalculan las señales (en v2.1 esa variante quedaba mal armada).

## Cambios de la versión 2.1: el híbrido en velas de 1 hora

- **Nueva estrategia "hibrido" (1 hora):** disparador del batacazo (compresión extrema + volumen muy alto) con la precisión del vendedor (filtro de funding y modelo predictivo propio), en ambos lados y sin techo de ganancia. Objetivo: muchas más operaciones, idealmente cerca de una por día.
- **Apuesta según convicción:** con modelo, el riesgo sube en rampa desde 1% (cuando P(ganar) es el mínimo) hasta el máximo (cuando P(ganar) ≥ 70%), sin superar nunca lo que permite Kelly fraccional. Máximos: híbrido 2,5%, vendedor y comprador 2%. El batacazo de 4h sigue en 0,5% fijo (no tiene modelo).
- **Límite de dirección por riesgo:** como máximo 5% de riesgo total en compras (o en ventas), en lugar de contar posiciones. Resuelve que el batacazo ocupara lugar de más.
- **Cuenta:** hasta 8 posiciones, 7% de riesgo total abierto y corte por caída del 20%.
- **Modelos sin día ni hora** de la semana (no tienen lógica económica y el modelo los usaba como ruido).
- **datos.py** baja 4h y 1h, y ahora es incremental: si ya tenés datos, solo descarga lo nuevo.
- `python graficos.py BTC 7 1h` muestra las señales del híbrido en velas de 1 hora.

## Cambios de la versión 2.0: tres estrategias medidas por separado

- **Vendedor:** ventas en rupturas bajistas cuando los compradores están sobrecargados (filtro de funding). Riesgo 1%.
- **Comprador:** compras en rupturas alcistas con BTC en tendencia alcista; solo se evita el funding muy alto. Riesgo 1%.
- **Batacazo:** rupturas de compresiones extremas con volumen muy alto, sin techo de ganancia (stop dinámico a 3,5 ATR, break-even a +2R, hasta 30 días). Riesgo 0,5%, máximo 2 posiciones y 1% de riesgo total.
- Se retiraron el pullback y la reversión: no mostraron ventaja fuera de muestra.
- Cada estrategia tiene su propio modelo predictivo, presupuesto de riesgo, informe antes/después de 2024, alarma de deterioro y optimización de salidas.
- El informe mide cuántas operaciones de vendedor/comprador frenó el batacazo por ocupar lugar. Si supera el 10%, recomienda achicarlo o sacarlo.
- La cuenta permite hasta 6 posiciones (4 en la misma dirección) y 5% de riesgo total abierto.

## Cambios de la versión 1.1 (feedback del primer backtest real)

- **Filtro de funding** (`FILTRO_FUNDING`): no se opera cuando nuestro lado viene pagando funding. En el diagnóstico de 3.191 señales, operar con el funding a favor fue mejor todos los años desde 2021.
- **Break-even a +1R** (`BREAK_EVEN_EN_R`): al alcanzar +1R a favor, el stop pasa a la entrada. El 21% de las perdedoras había llegado a +1R antes de perder.
- **Modo investigación** (`MODO_INVESTIGACION`): el backtest registra cuándo se habría activado el corte del 15%, pero sigue hasta el final para evaluar los 5 años completos.
- **Test t mensual**: las operaciones de un mismo mes están correlacionadas (las criptos se mueven juntas), así que el test por operación exagera la confianza. El test mensual es el que hay que mirar.
- **optimizar.py** ahora compara 12 combinaciones de toma parcial, break-even y filtro de funding, eligiendo con 2020–2023 y validando con 2024–2026.

## 1. Cómo se usa (en este orden)

| Paso | Comando | Qué hace |
|---|---|---|
| 1 | `pip install -r requirements.txt` | Instala las librerías nuevas (una sola vez) |
| 2 | `python datos.py` | Descarga velas y funding de las 20 monedas |
| 3 | `python rogelio.py` | Corre todo: señales, modelo, backtest, estadística y feedback |
| 4 | `python graficos.py BTC 60` | Velas japonesas con swings, niveles y señales |
| 5 | `python eventos.py BTC` | Estudio de eventos históricos |
| 6 | `python optimizar.py` | Prueba variantes de salida de cada estrategia (o `python optimizar.py batacazo`) |
| 7 | `python feedback.py` | Vuelve a analizar el registro de operaciones |
| 8 | `python calibrar.py` | Elige la escala de riesgo para el objetivo anual |
| 9 | `python plan_capital.py 200` | Proyecta cuándo se llega a la meta con un aporte mensual |
| 10 | `python v25.py` | Motor de factores (archivado) |
| 11 | `python veterano.py` | La rutina diaria del veterano, con 20 y 40 monedas |

Todo lo que se puede ajustar está en **config.py**. Los resultados quedan en la carpeta **reportes**.

## 2. Los módulos

| Archivo | Función |
|---|---|
| config.py | Todos los parámetros: universo, perfil de riesgo, costos, reglas, modelo |
| datos.py | Descarga de Binance (velas cerradas + historial de funding) |
| indicadores.py | EMA, RSI, ATR, ADX/DMI, MACD, Bollinger, Donchian, OBV, volumen relativo, eficiencia de Kaufman, volatilidad y percentiles |
| estructura.py | Swings confirmados sin mirar el futuro, estructura (máximos/mínimos crecientes), soportes y resistencias con fuerza, perfil de volumen (POC y zona de valor) |
| senales.py | Régimen de mercado y los 3 setups de entrada, con stop y objetivo |
| simulador.py | Simula cada señal vela por vela y mide el resultado en R, con comisiones, deslizamiento y funding |
| modelo.py | Modelo predictivo (meta-etiquetado con gradient boosting) validado en walk-forward |
| cartera.py | Backtest de cartera con todas las reglas de riesgo y tamaño por Kelly fraccional |
| metricas.py | Estadística: intervalos de confianza, test t, Sharpe probabilístico y deflactado, Monte Carlo |
| eventos.py + eventos.csv | Base de 47 sucesos (2020–2026) y estudio de su impacto en el precio |
| feedback.py | Análisis del registro: qué funciona, MAE/MFE, calibración del modelo, detección de deterioro y recomendaciones |
| optimizar.py | Prueba de variantes de salida con separación dentro/fuera de muestra |
| graficos.py | Velas japonesas, curva de capital, distribución de resultados |
| rogelio.py | Programa principal que une todo |

## 3. Las estrategias

Todas parten de la **ruptura de compresión**, el setup que mostró ventaja dentro y fuera de muestra:
1. Las bandas de Bollinger estuvieron en su zona más angosta (el mercado "dormido").
2. El precio rompe el canal de las últimas 20 velas a favor de la EMA 200.
3. La vela de ruptura tiene volumen alto y el ADX está subiendo.

La decisión se toma al cierre de la vela y la entrada es en la apertura de la siguiente. El stop va en la mitad del canal roto (entre 1 y 4 ATR).

| | Vendedor | Comprador | Batacazo |
|---|---|---|---|
| Lado | Ventas | Compras | Ambos |
| Compresión | 30% más angosto | 30% más angosto | 10% más angosto |
| Volumen mínimo | +1 desvío | +1 desvío | +2 desvíos |
| Filtro | No pagar funding | BTC alcista y funding no extremo | Funding normal |
| Objetivo | Antes del próximo nivel (máx. 4R) | Antes del próximo nivel (máx. 4R) | Sin techo |
| Salida | Parcial 50% al 60% del recorrido + break-even a +1R + trailing 2,5 ATR | Igual | Break-even a +2R + trailing 3,5 ATR |
| Riesgo por operación | 1% (hasta 1,25% con modelo) | 1% (hasta 1,25%) | 0,5% fijo |
| Modelo predictivo | Propio | Propio | No (pocas operaciones) |

**Híbrido (1 hora):** compresión 10% más angosta, volumen +2 desvíos, ambos lados, no pagar funding, sin techo (break-even a +2R, trailing 3,5 ATR, hasta 5 días), riesgo 1% a 2,5% según la convicción del modelo (mínimo P(ganar) 50%).

Todo se ajusta en `config.ESTRATEGIAS`. Para apagar una estrategia: `"activa": False`.

## 4. Las tres variables centrales

- **Win rate (p):** proporción de operaciones ganadoras. (Win rate y tasa de acierto son lo mismo.)
- **Relación b:** ganancia media ÷ pérdida media.
- **Riesgo por operación:** % del capital que se pierde si toca el stop.

De ellas se derivan:
- **Expectativa** = p × ganancia media − (1 − p) × pérdida media. Es la métrica principal: si es negativa, la estrategia pierde plata, sin importar el win rate.
- **Win rate de equilibrio** = 1 / (1 + b).
- **Kelly** = p − (1 − p) / b. Rogelio usa **un cuarto** de Kelly, limitado a 2% por operación.

## 5. Gestión de riesgo (tiene poder de veto)

- Riesgo por operación según la estrategia (ver tabla de la sección 3), ajustado por Kelly fraccional cuando hay modelo.
- Cada estrategia tiene su presupuesto de riesgo abierto y su máximo de posiciones.
- Apalancamiento máximo 5x, y la liquidación siempre al menos al doble de distancia que el stop.
- En la cuenta: máximo 6 posiciones abiertas, 4 en la misma dirección, 1 por moneda, 5% de riesgo total abierto.
- Si se pierde 3% en el día, no se abren más posiciones ese día.
- Si el capital cae 15% desde su máximo, Rogelio se apaga.
- No se abren posiciones 24 horas antes y después de eventos programados (eventos.csv con programado = si).

## 6. Modelo predictivo

**Meta-etiquetado** (López de Prado): las reglas proponen operaciones; un modelo de gradient boosting entrenado con todas las operaciones pasadas de las 20 monedas estima la probabilidad de que cada una gane, usando 33 variables de contexto (tendencia, momentum, distancia a niveles, volatilidad, volumen, funding, situación de BTC, hora, día).

**Validación walk-forward con embargo:** se reentrena cada 6 meses, solo con operaciones que terminaron antes del período a predecir y con 10 días de separación. Cada predicción del backtest se hizo sin conocer el futuro.

## 7. Cómo leer el informe

- **expectativa_IC95:** si el intervalo incluye el 0, no hay evidencia de que la estrategia gane.
- **test_t_mensual > 2:** la ganancia probablemente no es suerte (es más exigente y honesto que el p_valor por operación).
- **sharpe_deflactado > 0,95:** la estrategia probablemente es buena incluso descontando las variantes probadas.
- **Monte Carlo:** qué tan mal podría haber ido con otra suerte. Si la probabilidad de activar el corte es alta, bajar el riesgo.
- **Calibración:** si el modelo dice 60% y se gana el 45%, el modelo es optimista.

## 8. Bucle de feedback

Después de cada tanda de operaciones (backtest, testnet o reales):
1. Correr `python feedback.py`.
2. Revisar desglose por setup, moneda, régimen y motivo de salida.
3. Mirar MAE/MFE: ¿las perdedoras llegaron a estar en ganancia? ¿El stop está bien ubicado?
4. Revisar la calibración del modelo y la alarma de deterioro (CUSUM).
5. Aplicar los cambios en config.py, sumar las variantes probadas a CANTIDAD_PRUEBAS_REALIZADAS y volver a correr.

## 9. Límites honestos

- Más complejidad no garantiza más ganancia: cada regla y cada variable extra aumenta el riesgo de sobreajuste. Por eso todo se valida fuera de muestra.
- El backtest no modela la pérdida no realizada dentro de cada operación (el drawdown real puede ser algo mayor), ni la profundidad del libro de órdenes.
- Las noticias no se pueden anticipar; el sistema solo mide su impacto histórico y evita eventos programados.
- No se copian traders de los rankings de los exchanges: los rankings muestran a los que tuvieron suerte en un período corto (sesgo de supervivencia), con apalancamiento y sin historial completo.

## 10. Fuentes de las ideas

- Van K. Tharp, *Trade Your Way to Financial Freedom*: expectativa, múltiplos R, SQN, tamaño de posición.
- Ralph Vince y J. L. Kelly: tamaño óptimo de apuesta.
- Marcos López de Prado, *Advances in Financial Machine Learning*: meta-etiquetado, walk-forward con purga y embargo, Sharpe deflactado.
- Bailey y López de Prado (2012): Sharpe probabilístico.
- Robert Carver, *Systematic Trading*: diseño de sistemas y control del sobreajuste.
- Andreas Clenow, *Following the Trend*; Moskowitz, Ooi y Pedersen (2012): seguimiento de tendencia.
- Perry Kaufman, *Trading Systems and Methods*: ratio de eficiencia y regímenes.
- J. Welles Wilder: RSI, ATR y ADX.
- Al Brooks y Richard Wyckoff: estructura de mercado, swings, soportes y resistencias.
- MacKinlay (1997): metodología de estudio de eventos.
- Schmeling, Schrimpf y Todorov (BIS, 2023), "Crypto carry": el carry alto anticipa caídas.
- Liu, Tsyvinski y Wu, "Common Risk Factors in Cryptocurrency": mercado, tamaño y momentum.
- Moreira y Muir (2017), "Volatility-Managed Portfolios": ajustar la exposición a la volatilidad.
