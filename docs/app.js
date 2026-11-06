/* Rogelio — página de repetición del backtest.
   No calcula señales: reproduce lo que Rogelio ya hizo, a partir de los
   archivos que genera exportar_web.py en la carpeta replay/. */
(function () {
  "use strict";

  const R = window.ROGELIO_RESUMEN;
  if (!R) {
    document.getElementById("cargando").textContent =
      "Faltan los datos: corré  python exportar_web.py  y volvé a abrir la página.";
    return;
  }

  // ------------------------------------------------------------------
  // Utilidades
  // ------------------------------------------------------------------
  const $ = (id) => document.getElementById(id);
  const nf = (d) => new Intl.NumberFormat("es-AR", { minimumFractionDigits: d, maximumFractionDigits: d });
  const f0 = nf(0), f1 = nf(1), f2 = nf(2);
  const signo = (x, fmt = f1) => (x > 0 ? "+" : x < 0 ? "−" : "") + fmt.format(Math.abs(x));
  const pct = (x, fmt = f1) => signo(x, fmt) + "%";
  const pctLibre = (x, fmt = f1) => (x < 0 ? "−" : "") + fmt.format(Math.abs(x)) + "%";
  const reducirMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  const fechaHora = (h) => {
    const d = new Date(h * 3600e3);
    return `${d.getUTCDate()} ${MESES[d.getUTCMonth()]} ${d.getUTCFullYear()}, ${String(d.getUTCHours()).padStart(2, "0")}:00`;
  };
  const fechaCorta = (h) => {
    const d = new Date(h * 3600e3);
    return `${d.getUTCDate()} ${MESES[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
  };

  function precio(x) {
    if (x == null) return "—";
    const a = Math.abs(x);
    const dec = a >= 1000 ? 0 : a >= 100 ? 1 : a >= 1 ? 2 : a >= 0.01 ? 4 : 6;
    return nf(dec).format(x);
  }

  function pasoLindo(rango, objetivo) {
    const bruto = rango / Math.max(1, objetivo);
    const mag = Math.pow(10, Math.floor(Math.log10(bruto)));
    const n = bruto / mag;
    return (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * mag;
  }

  function colores(el) {
    const cs = getComputedStyle(el);
    const v = (n) => cs.getPropertyValue(n).trim();
    return {
      fondo: v("--p-fondo"), tinta: v("--p-tinta"), tinta2: v("--p-tinta-2"), regla: v("--p-regla"),
      grilla: v("--p-grilla"), sube: v("--p-sube"), baja: v("--p-baja"), ema: v("--p-ema"),
      vendedor: v("--p-vendedor"), comprador: v("--p-comprador"), batacazo: v("--p-batacazo"),
      // colores de la página (gráficos claros)
      pFondo: v("--superficie"), pTinta: v("--tinta"), pTinta2: v("--tinta-2"), pTinta3: v("--tinta-3"),
      pRegla: v("--regla"), pSube: v("--sube"), pBaja: v("--baja"), pBtc: v("--btc"),
      pVendedor: v("--vendedor"), pComprador: v("--comprador"), pBatacazo: v("--batacazo"),
    };
  }
  function conAlfa(color, a) {
    const c = color.replace("#", "");
    if (c.length !== 6) return color;
    const r = parseInt(c.slice(0, 2), 16), g = parseInt(c.slice(2, 4), 16), b = parseInt(c.slice(4, 6), 16);
    return `rgba(${r},${g},${b},${a})`;
  }

  function prepararLienzo(canvas) {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, w, h };
  }

  // ------------------------------------------------------------------
  // Textos de las estrategias (sin revelar parámetros)
  // ------------------------------------------------------------------
  const ESTRATEGIAS = {
    vendedor: {
      nombre: "Vendedor",
      corto: "Vende cuando el precio rompe hacia abajo después de un período quieto, si los compradores ya están sobrecargados.",
      porque: "El precio venía quieto y rompió el rango hacia abajo con volumen alto, mientras los compradores pagaban de más por mantener sus posiciones.",
    },
    comprador: {
      nombre: "Comprador",
      corto: "Compra cuando el precio rompe hacia arriba después de un período quieto, con el mercado general a favor.",
      porque: "El precio venía quieto y rompió el rango hacia arriba con volumen alto, con Bitcoin en tendencia alcista.",
    },
    batacazo: {
      nombre: "Batacazo",
      corto: "Las rupturas más fuertes, con volumen excepcional. No tiene techo de ganancia: deja correr la tendencia.",
      porque: "Una calma muy marcada terminó con un volumen excepcional. Estas operaciones no tienen techo: el stop sigue al precio mientras la tendencia dure.",
    },
  };
  const nombreEstrategia = (e) => (ESTRATEGIAS[e] ? ESTRATEGIAS[e].nombre : e.charAt(0).toUpperCase() + e.slice(1));
  const colorEstrategia = (C, e, pantalla = true) => {
    const k = (pantalla ? "" : "p") + (pantalla ? e : e.charAt(0).toUpperCase() + e.slice(1));
    return C[k] || (pantalla ? C.tinta2 : C.pTinta2);
  };

  const MOTIVOS = {
    stop: "Tocó el stop",
    stop_loss: "Tocó el stop",
    sl: "Tocó el stop",
    objetivo: "Llegó al objetivo",
    tp: "Llegó al objetivo",
    take_profit: "Llegó al objetivo",
    trailing: "Lo cerró el stop que sigue al precio",
    trailing_stop: "Lo cerró el stop que sigue al precio",
    break_even: "Volvió al precio de entrada",
    breakeven: "Volvió al precio de entrada",
    be: "Volvió al precio de entrada",
    tiempo: "Se cumplió el plazo máximo",
    plazo: "Se cumplió el plazo máximo",
    timeout: "Se cumplió el plazo máximo",
    fin_datos: "Terminaron los datos",
  };
  const textoMotivo = (m) => {
    if (!m) return "—";
    const k = m.toString().toLowerCase().replace(/[\s-]+/g, "_");
    return MOTIVOS[k] || m.charAt(0).toUpperCase() + m.slice(1).replace(/_/g, " ");
  };

  // ------------------------------------------------------------------
  // Cabecera, enlaces y avisos
  // ------------------------------------------------------------------
  if (R.demo) $("aviso-demo").hidden = false;
  // Un enlace que todavía dice TU_USUARIO o TU_PERFIL no se muestra.
  const ponerEnlace = (id, url) => {
    const a = $(id);
    if (!url || /TU_(USUARIO|PERFIL)/.test(url)) a.hidden = true;
    else a.href = url;
  };
  ponerEnlace("enlace-github", R.enlaces.github);
  ponerEnlace("enlace-github-cab", R.enlaces.github);
  ponerEnlace("enlace-linkedin", R.enlaces.linkedin);
  document.querySelectorAll('[data-campo="version"]').forEach((e) => (e.textContent = R.version));
  document.querySelectorAll('[data-campo="fuera"]').forEach((e) => (e.textContent = R.fuera_de_muestra));
  document.querySelectorAll('[data-campo="autor"]').forEach((e) => (e.textContent = R.autor));
  $("pie-generado").textContent = `Datos generados el ${R.generado} por exportar_web.py a partir de los resultados del backtest.`;

  // ==================================================================
  // 1. REPETICIÓN
  // ==================================================================
  const monedas = {};
  window.ROGELIO_MONEDA = function (m, d) {
    const n = d.t.length;
    const o = new Float64Array(n), h = new Float64Array(n), l = new Float64Array(n), c = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      o[i] = d.ohlc[4 * i]; h[i] = d.ohlc[4 * i + 1]; l[i] = d.ohlc[4 * i + 2]; c[i] = d.ohlc[4 * i + 3];
    }
    // Media exponencial de 200 velas, arrancada con el promedio simple de las primeras 200.
    const ema = new Float64Array(n);
    const k = 2 / 201;
    let suma = 0;
    for (let i = 0; i < Math.min(200, n); i++) { suma += c[i]; ema[i] = NaN; }
    if (n >= 200) ema[199] = suma / 200;
    for (let i = 200; i < n; i++) ema[i] = c[i] * k + ema[i - 1] * (1 - k);
    const t = d.t;
    const buscar = (hora) => {
      let a = 0, b = n - 1;
      if (hora <= t[0]) return 0;
      if (hora > t[b]) return b;
      while (a < b) { const mid = (a + b) >> 1; if (t[mid] < hora) a = mid + 1; else b = mid; }
      return a;
    };
    const ops = d.ops.map((op, idx) => ({
      ...op, idx,
      ie: buscar(op.te),
      ix: op.ts == null ? null : buscar(op.ts),
      riesgoPrecio: op.sl != null && op.pe != null ? Math.abs(op.pe - op.sl) : null,
    })).sort((a, b) => a.ie - b.ie);
    monedas[m] = { m, n, t, o, h, l, c, ema, ops };
  };

  function cargarMoneda(m) {
    if (monedas[m]) return Promise.resolve(monedas[m]);
    return new Promise((ok, mal) => {
      const s = document.createElement("script");
      s.src = `replay/monedas/${encodeURIComponent(m)}.js`;
      s.onload = () => (monedas[m] ? ok(monedas[m]) : mal(new Error("sin datos")));
      s.onerror = () => mal(new Error("no se pudo cargar " + m));
      document.head.appendChild(s);
    });
  }

  const pantalla = $("pantalla");
  const lienzo = $("lienzo-velas");
  let C = colores(pantalla);

  const VELOCIDADES = [
    { nombre: "1×", velas: 6 },
    { nombre: "4×", velas: 24 },
    { nombre: "16×", velas: 96 },
    { nombre: "60×", velas: 360 },
  ];

  const E = {
    moneda: null,           // datos de la moneda actual
    cursor: 0,              // índice de la última vela visible (puede ser fraccionario mientras se reproduce)
    finVista: 0,            // índice en el borde derecho
    velasVisibles: 160,
    seguir: true,
    reproduciendo: false,
    velocidad: 1,
    filtro: new Set(Object.keys(ESTRATEGIAS)),
    seleccion: null,        // operación fijada por el usuario
    hover: null,            // índice de vela bajo el puntero
    hoverY: null,
    ultimoT: 0,
  };

  const cur = () => Math.floor(E.cursor);
  const opsVisibles = () => (E.moneda ? E.moneda.ops.filter((o) => E.filtro.has(o.e) || !ESTRATEGIAS[o.e]) : []);

  // --- selector de moneda
  const sel = $("sel-moneda");
  R.monedas.forEach((x) => {
    const op = document.createElement("option");
    op.value = x.m;
    op.textContent = `${x.m} (${x.n} operaciones)`;
    sel.appendChild(op);
  });
  sel.addEventListener("change", () => abrirMoneda(sel.value, true));

  // --- filtros
  const estrategiasPresentes = [...new Set(R.ops.map((o) => o.e))];
  estrategiasPresentes.forEach((e) => E.filtro.add(e));
  const filtros = $("filtros");
  estrategiasPresentes.forEach((e) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.setAttribute("aria-pressed", "true");
    b.style.setProperty("--c", colorEstrategia(C, e));
    b.innerHTML = `<i></i>${nombreEstrategia(e)}`;
    b.addEventListener("click", () => {
      const activo = E.filtro.has(e);
      if (activo && E.filtro.size === 1) return; // siempre queda una
      activo ? E.filtro.delete(e) : E.filtro.add(e);
      b.setAttribute("aria-pressed", String(!activo));
      if (E.seleccion && !E.filtro.has(E.seleccion.e)) E.seleccion = null;
      actualizarFicha();
      dibujar();
    });
    filtros.appendChild(b);
  });

  // --- velocidades
  const vel = $("velocidades");
  VELOCIDADES.forEach((v, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = v.nombre;
    b.setAttribute("aria-pressed", String(i === E.velocidad));
    b.addEventListener("click", () => {
      E.velocidad = i;
      [...vel.children].forEach((x, j) => x.setAttribute("aria-pressed", String(j === i)));
    });
    vel.appendChild(b);
  });

  // --- controles
  const btnPlay = $("btn-play");
  function setReproduciendo(si) {
    E.reproduciendo = si && E.moneda && cur() < E.moneda.n - 1;
    btnPlay.dataset.estado = E.reproduciendo ? "reproduciendo" : "pausa";
    btnPlay.setAttribute("aria-label", E.reproduciendo ? "Pausar" : "Reproducir");
    if (E.reproduciendo) {
      E.ultimoT = performance.now();
      if (!E.seguir) volverAlPresente();
      requestAnimationFrame(cuadro);
    }
  }
  btnPlay.addEventListener("click", () => setReproduciendo(!E.reproduciendo));
  $("btn-siguiente").addEventListener("click", () => saltar(1));
  $("btn-anterior").addEventListener("click", () => saltar(-1));
  $("btn-acercar").addEventListener("click", () => zoom(1 / 1.4));
  $("btn-alejar").addEventListener("click", () => zoom(1.4));
  $("btn-seguir").addEventListener("click", volverAlPresente);

  const linea = $("linea-tiempo");
  linea.addEventListener("input", () => {
    E.cursor = Number(linea.value);
    E.seguir = true;
    ajustarVista();
    actualizarFicha();
    dibujar();
  });

  pantalla.addEventListener("keydown", (ev) => {
    if (ev.target.tagName === "SELECT" || ev.target.tagName === "INPUT") return;
    if (ev.key === " ") { ev.preventDefault(); setReproduciendo(!E.reproduciendo); }
    else if (ev.key === "ArrowRight") { ev.preventDefault(); saltar(1); }
    else if (ev.key === "ArrowLeft") { ev.preventDefault(); saltar(-1); }
  });

  function margenDerecho() { return Math.max(3, E.velasVisibles * 0.12); }
  function ajustarVista() { if (E.seguir) E.finVista = E.cursor + 1 + margenDerecho(); }
  function volverAlPresente() {
    E.seguir = true;
    $("btn-seguir").hidden = true;
    ajustarVista();
    dibujar();
  }

  function saltar(dir) {
    const ops = opsVisibles();
    if (!ops.length) return;
    setReproduciendo(false);
    const ref = E.seleccion ? E.seleccion.ie : (dir > 0 ? cur() - 1 : cur());
    let destino = null;
    if (dir > 0) destino = ops.find((o) => o.ie > ref) || null;
    else for (let i = ops.length - 1; i >= 0; i--) if (ops[i].ie < ref) { destino = ops[i]; break; }
    if (!destino) return;
    E.seleccion = destino;
    const fin = destino.ix != null ? destino.ix : destino.ie + 30;
    E.cursor = Math.min(E.moneda.n - 1, fin + 6);
    const largo = fin - destino.ie;
    E.velasVisibles = Math.min(900, Math.max(90, largo * 2.6 + 60));
    E.seguir = true;
    ajustarVista();
    $("btn-seguir").hidden = true;
    actualizarFicha();
    dibujar();
  }

  function zoom(factor, anclaX) {
    if (!E.moneda) return;
    const { w } = dims();
    const anchoGraf = w - EJE_DER;
    const ancla = anclaX == null ? (E.seguir ? anchoGraf : anchoGraf / 2) : anclaX;
    const izq = E.finVista - E.velasVisibles;
    const iAncla = izq + (ancla / anchoGraf) * E.velasVisibles;
    const nuevas = Math.min(Math.max(E.velasVisibles * factor, 30), 2400);
    E.velasVisibles = nuevas;
    if (E.seguir) ajustarVista();
    else E.finVista = iAncla + (1 - ancla / anchoGraf) * nuevas;
    limitarVista();
    dibujar();
  }

  function limitarVista() {
    const max = E.cursor + 1 + E.velasVisibles * 0.5;
    const min = Math.min(E.velasVisibles * 0.25, max);
    E.finVista = Math.min(Math.max(E.finVista, min), max);
  }

  // --- puntero sobre el gráfico
  const EJE_DER = 70, EJE_INF = 24, MARGEN_SUP = 10;
  function dims() { return { w: lienzo.clientWidth, h: lienzo.clientHeight }; }
  let arrastre = null;
  lienzo.addEventListener("pointerdown", (ev) => {
    arrastre = { x: ev.clientX, y: ev.clientY, fin: E.finVista, movio: false, id: ev.pointerId };
  });
  window.addEventListener("pointermove", (ev) => {
    const r = lienzo.getBoundingClientRect();
    if (arrastre && ev.pointerId === arrastre.id) {
      const dx = ev.clientX - arrastre.x;
      if (!arrastre.movio && Math.abs(dx) > 4) {
        arrastre.movio = true;
        lienzo.setPointerCapture && lienzo.setPointerCapture(ev.pointerId);
        lienzo.classList.add("arrastrando");
        setReproduciendo(false);
        E.seguir = false;
        $("btn-seguir").hidden = false;
      }
      if (arrastre.movio) {
        const anchoVela = (r.width - EJE_DER) / E.velasVisibles;
        E.finVista = arrastre.fin - dx / anchoVela;
        limitarVista();
        dibujar();
        return;
      }
    }
    const x = ev.clientX - r.left, y = ev.clientY - r.top;
    if (x < 0 || y < 0 || x > r.width || y > r.height) {
      if (E.hover != null) { E.hover = null; dibujar(); }
      return;
    }
    const anchoVela = (r.width - EJE_DER) / E.velasVisibles;
    const izq = E.finVista - E.velasVisibles;
    E.hover = x < r.width - EJE_DER ? Math.floor(izq + x / anchoVela) : null;
    E.hoverY = y;
    if (!E.reproduciendo) dibujar();
  });
  window.addEventListener("pointerup", (ev) => {
    if (!arrastre || ev.pointerId !== arrastre.id) return;
    const fueClic = !arrastre.movio;
    arrastre = null;
    lienzo.classList.remove("arrastrando");
    if (fueClic) {
      const r = lienzo.getBoundingClientRect();
      const op = opEnPunto(ev.clientX - r.left, ev.clientY - r.top);
      if (op) { E.seleccion = op; actualizarFicha(); dibujar(); }
    }
  });
  lienzo.addEventListener("pointerleave", () => { if (!arrastre) { E.hover = null; dibujar(); } });
  lienzo.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    const r = lienzo.getBoundingClientRect();
    zoom(ev.deltaY > 0 ? 1.15 : 1 / 1.15, ev.clientX - r.left);
  }, { passive: false });

  // Geometría de la última pintada, para el clic
  let geo = null;
  function opEnPunto(x, y) {
    if (!geo) return null;
    let mejor = null;
    for (const z of geo.zonas) {
      if (x >= z.x0 - 4 && x <= z.x1 + 4 && y >= z.y0 - 4 && y <= z.y1 + 4) {
        if (!mejor || z.x1 - z.x0 < mejor.x1 - mejor.x0) mejor = z;
      }
    }
    return mejor ? mejor.op : null;
  }

  // --- animación
  function cuadro(ahora) {
    if (!E.reproduciendo) return;
    const dt = Math.min(0.1, (ahora - E.ultimoT) / 1000);
    E.ultimoT = ahora;
    const antes = cur();
    E.cursor = Math.min(E.moneda.n - 1, E.cursor + VELOCIDADES[E.velocidad].velas * dt);
    ajustarVista();
    if (cur() !== antes) {
      linea.value = cur();
      // al reproducir, la ficha muestra la operación más reciente
      if (E.seleccion && E.seleccion.ie > cur()) E.seleccion = null;
      actualizarFicha();
    }
    dibujar();
    if (cur() >= E.moneda.n - 1) { setReproduciendo(false); return; }
    requestAnimationFrame(cuadro);
  }

  // --- dibujo de velas
  function dibujar() {
    const D = E.moneda;
    if (!D) return;
    const { ctx, w, h } = prepararLienzo(lienzo);
    const W = w - EJE_DER, H = h - EJE_INF - MARGEN_SUP;
    const c0 = cur();
    const izq = E.finVista - E.velasVisibles;
    const anchoVela = W / E.velasVisibles;
    const i0 = Math.max(0, Math.floor(izq));
    const i1 = Math.min(c0, Math.ceil(E.finVista));
    const x = (i) => (i - izq + 0.5) * anchoVela;

    $("fecha-actual").textContent = fechaHora(D.t[c0]);

    ctx.fillStyle = C.fondo;
    ctx.fillRect(0, 0, w, h);

    if (i1 < i0) { geo = { zonas: [] }; return; }

    // operaciones que se ven
    const ops = opsVisibles().filter((o) => o.ie <= c0 && (o.ix == null ? c0 : Math.min(o.ix, c0)) >= i0 && o.ie <= i1);

    // rango de precios
    let lo = Infinity, hi = -Infinity;
    for (let i = i0; i <= i1; i++) { if (D.l[i] < lo) lo = D.l[i]; if (D.h[i] > hi) hi = D.h[i]; }
    const elegida = E.seleccion && ops.includes(E.seleccion) ? E.seleccion : null;
    for (const o of ops) {
      if (o.ie < i0) continue;
      for (const p of [o.sl, o.tp]) if (p != null) { lo = Math.min(lo, p); hi = Math.max(hi, p); }
    }
    if (elegida) for (const p of [elegida.sl, elegida.tp]) if (p != null) { lo = Math.min(lo, p); hi = Math.max(hi, p); }
    const pad = (hi - lo) * 0.07 || hi * 0.01;
    lo -= pad; hi += pad;
    const y = (p) => MARGEN_SUP + (1 - (p - lo) / (hi - lo)) * H;
    const precioEn = (py) => lo + (1 - (py - MARGEN_SUP) / H) * (hi - lo);

    // grilla y eje de precios
    ctx.font = "12px " + getComputedStyle(document.body).fontFamily;
    ctx.textBaseline = "middle";
    const paso = pasoLindo(hi - lo, Math.max(3, Math.floor(H / 56)));
    ctx.lineWidth = 1;
    for (let p = Math.ceil(lo / paso) * paso; p <= hi; p += paso) {
      const py = Math.round(y(p)) + 0.5;
      ctx.strokeStyle = C.grilla;
      ctx.beginPath(); ctx.moveTo(0, py); ctx.lineTo(W, py); ctx.stroke();
      ctx.fillStyle = C.tinta2;
      ctx.textAlign = "left";
      ctx.fillText(precio(p), W + 8, py);
    }

    // eje de fechas
    dibujarFechas(ctx, D, i0, i1, x, anchoVela, W, h);

    // zonas de las operaciones (detrás de las velas)
    const zonas = [];
    for (const o of ops) {
      const fin = o.ix == null || o.ix > c0 ? c0 : o.ix;
      const abierta = o.ix == null || o.ix > c0;
      const xa = x(o.ie) - anchoVela / 2, xb = x(fin) + anchoVela / 2;
      const alfa = o === elegida ? 0.30 : 0.17;
      if (o.pe != null && o.tp != null) {
        ctx.fillStyle = conAlfa(C.sube, alfa);
        ctx.fillRect(xa, Math.min(y(o.pe), y(o.tp)), xb - xa, Math.abs(y(o.tp) - y(o.pe)));
      }
      if (o.pe != null && o.sl != null) {
        ctx.fillStyle = conAlfa(C.baja, alfa);
        ctx.fillRect(xa, Math.min(y(o.pe), y(o.sl)), xb - xa, Math.abs(y(o.sl) - y(o.pe)));
      }
      if (o.pe != null && o.tp == null && o.sl != null) {
        // sin techo: una guía punteada hacia el lado de la operación
        ctx.strokeStyle = conAlfa(C.sube, 0.7);
        ctx.setLineDash([3, 4]);
        const yTecho = y(o.pe + o.lado * Math.abs(o.pe - o.sl) * 2);
        ctx.beginPath(); ctx.moveTo(xa, yTecho); ctx.lineTo(xb, yTecho); ctx.stroke();
        ctx.setLineDash([]);
      }
      if (o.pe != null) {
        ctx.strokeStyle = conAlfa(C.tinta, 0.75);
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(xa, Math.round(y(o.pe)) + 0.5); ctx.lineTo(xb, Math.round(y(o.pe)) + 0.5); ctx.stroke();
      }
      const ys = [o.pe, o.sl, o.tp].filter((p) => p != null).map(y);
      zonas.push({ op: o, x0: xa, x1: xb, y0: Math.min(...ys), y1: Math.max(...ys), abierta });
      if (o === elegida) {
        ctx.strokeStyle = C.tinta;
        ctx.lineWidth = 1.5;
        ctx.strokeRect(xa + 0.75, Math.min(...ys) + 0.75, xb - xa - 1.5, Math.max(...ys) - Math.min(...ys) - 1.5);
        ctx.lineWidth = 1;
      }
    }

    // velas
    const cuerpo = Math.max(1, Math.min(anchoVela * 0.64, 14));
    for (let i = i0; i <= i1; i++) {
      const sube = D.c[i] >= D.o[i];
      ctx.strokeStyle = ctx.fillStyle = sube ? C.sube : C.baja;
      const cx = Math.round(x(i)) + 0.5;
      ctx.beginPath(); ctx.moveTo(cx, y(D.h[i])); ctx.lineTo(cx, y(D.l[i])); ctx.stroke();
      const ya = y(Math.max(D.o[i], D.c[i])), yb = y(Math.min(D.o[i], D.c[i]));
      ctx.fillRect(cx - cuerpo / 2, ya, cuerpo, Math.max(1, yb - ya));
    }

    // tendencia de fondo
    ctx.strokeStyle = C.ema;
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    for (let i = Math.max(i0, 199); i <= i1; i++) {
      const px = x(i), py = y(D.ema[i]);
      i === Math.max(i0, 199) ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
    }
    ctx.stroke();
    ctx.lineWidth = 1;

    // marcas de entrada y salida
    for (const o of ops) {
      if (o.pe == null) continue;
      const col = colorEstrategia(C, o.e);
      const ex = x(o.ie), ey = y(o.pe);
      const tam = 7;
      ctx.fillStyle = col;
      ctx.strokeStyle = C.fondo;
      ctx.lineWidth = 2;
      ctx.beginPath();
      if (o.lado >= 0) { ctx.moveTo(ex, ey - tam); ctx.lineTo(ex + tam, ey + tam * 0.8); ctx.lineTo(ex - tam, ey + tam * 0.8); }
      else { ctx.moveTo(ex, ey + tam); ctx.lineTo(ex + tam, ey - tam * 0.8); ctx.lineTo(ex - tam, ey - tam * 0.8); }
      ctx.closePath(); ctx.stroke(); ctx.fill();
      if (o.ix != null && o.ix <= c0 && o.ps != null) {
        ctx.beginPath();
        ctx.arc(x(o.ix), y(o.ps), 4.5, 0, Math.PI * 2);
        ctx.fillStyle = o.r >= 0 ? C.sube : C.baja;
        ctx.stroke(); ctx.fill();
        if (o === elegida || anchoVela > 5) {
          ctx.font = "600 12px " + getComputedStyle(document.body).fontFamily;
          ctx.fillStyle = C.tinta;
          ctx.textAlign = "center";
          const arriba = o.r >= 0 ? o.lado >= 0 : o.lado < 0;
          ctx.fillText(signo(o.r, f1) + " R", x(o.ix), y(o.ps) + (arriba ? -14 : 14));
          ctx.font = "12px " + getComputedStyle(document.body).fontFamily;
        }
      }
      ctx.lineWidth = 1;
    }

    // línea del presente
    const xc = Math.round(x(c0) + anchoVela / 2) + 0.5;
    if (xc < W) {
      ctx.fillStyle = conAlfa(C.tinta2, 0.05);
      ctx.fillRect(xc, 0, W - xc, h - EJE_INF);
      ctx.strokeStyle = conAlfa(C.tinta2, 0.6);
      ctx.setLineDash([2, 3]);
      ctx.beginPath(); ctx.moveTo(xc, 0); ctx.lineTo(xc, h - EJE_INF); ctx.stroke();
      ctx.setLineDash([]);
    }
    // último precio en el eje
    etiquetaEje(ctx, y(D.c[c0]), precio(D.c[c0]), D.c[c0] >= D.o[c0] ? C.sube : C.baja, C.fondo, W);

    // cursor del puntero
    if (E.hover != null && E.hover >= i0 && E.hover <= i1 && !arrastre?.movio) {
      const hx = Math.round(x(E.hover)) + 0.5;
      ctx.strokeStyle = conAlfa(C.tinta, 0.35);
      ctx.beginPath(); ctx.moveTo(hx, 0); ctx.lineTo(hx, h - EJE_INF); ctx.stroke();
      if (E.hoverY != null && E.hoverY < h - EJE_INF) {
        ctx.beginPath(); ctx.moveTo(0, E.hoverY + 0.5); ctx.lineTo(W, E.hoverY + 0.5); ctx.stroke();
        etiquetaEje(ctx, E.hoverY, precio(precioEn(E.hoverY)), C.tinta, C.fondo, W);
      }
      const i = E.hover;
      const txt = `${fechaHora(D.t[i])}   A ${precio(D.o[i])}   Máx ${precio(D.h[i])}   Mín ${precio(D.l[i])}   C ${precio(D.c[i])}`;
      ctx.font = "12px " + getComputedStyle(document.body).fontFamily;
      const tw = ctx.measureText(txt).width;
      ctx.fillStyle = conAlfa(C.fondo, 0.88);
      ctx.fillRect(8, 8, Math.min(tw + 16, W - 16), 24);
      ctx.fillStyle = C.tinta;
      ctx.textAlign = "left";
      ctx.fillText(txt, 16, 20);
    }

    geo = { zonas };
  }

  function etiquetaEje(ctx, py, texto, fondo, tinta, W) {
    ctx.font = "600 12px " + getComputedStyle(document.body).fontFamily;
    ctx.fillStyle = fondo;
    ctx.fillRect(W + 2, py - 10, EJE_DER - 4, 20);
    ctx.fillStyle = tinta;
    ctx.textAlign = "left";
    ctx.fillText(texto, W + 8, py);
    ctx.font = "12px " + getComputedStyle(document.body).fontFamily;
  }

  function dibujarFechas(ctx, D, i0, i1, x, anchoVela, W, h) {
    const velasPorEtiqueta = 96 / anchoVela; // una etiqueta cada ~96 px
    ctx.fillStyle = C.tinta2;
    ctx.textAlign = "center";
    ctx.strokeStyle = C.grilla;
    const yt = h - EJE_INF / 2;
    let ultimoX = -Infinity;
    const poner = (i, texto) => {
      const px = x(i);
      if (px - ultimoX < 70 || px > W - 20) return;
      ctx.beginPath(); ctx.moveTo(Math.round(px) + 0.5, 0); ctx.lineTo(Math.round(px) + 0.5, h - EJE_INF); ctx.stroke();
      ctx.fillText(texto, px, yt);
      ultimoX = px;
    };
    if (velasPorEtiqueta >= 150) {
      const pasoMes = [1, 2, 3, 6, 12].find((m) => m * 180 >= velasPorEtiqueta) || 12;
      let mesAnt = null;
      for (let i = Math.max(1, i0); i <= i1; i++) {
        const d = new Date(D.t[i] * 3600e3);
        const mes = d.getUTCFullYear() * 12 + d.getUTCMonth();
        if (mesAnt != null && mes !== mesAnt && mes % pasoMes === 0) {
          poner(i, d.getUTCMonth() === 0 || pasoMes >= 12 ? String(d.getUTCFullYear()) : `${MESES[d.getUTCMonth()]} ${String(d.getUTCFullYear()).slice(2)}`);
        }
        mesAnt = mes;
      }
    } else {
      const pasoDia = [1, 2, 3, 7, 14].find((d) => d * 6 >= velasPorEtiqueta) || 14;
      for (let i = i0; i <= i1; i++) {
        const hora = D.t[i];
        if (hora % 24 !== 0) continue;
        const dia = hora / 24;
        if (dia % pasoDia !== 0) continue;
        const d = new Date(hora * 3600e3);
        poner(i, `${d.getUTCDate()} ${MESES[d.getUTCMonth()]}`);
      }
    }
  }

  // --- ficha de la operación
  function operacionActual() {
    if (E.seleccion) return E.seleccion;
    const ops = opsVisibles();
    let ultima = null;
    for (const o of ops) { if (o.ie <= cur()) ultima = o; else break; }
    return ultima;
  }

  function actualizarFicha() {
    const D = E.moneda;
    const caja = $("ficha-contenido");
    const o = operacionActual();
    const c0 = cur();
    if (!o) {
      caja.innerHTML = '<p class="ficha__vacia">Dale play: cuando Rogelio entre a una operación, acá vas a ver por qué y cómo le fue.</p>';
    } else {
      const abierta = o.ix == null || o.ix > c0;
      const lado = o.lado >= 0 ? "Compra" : "Venta";
      const est = ESTRATEGIAS[o.e];
      let rAhora = o.r;
      if (abierta && o.riesgoPrecio) rAhora = (o.lado >= 0 ? 1 : -1) * (D.c[c0] - o.pe) / o.riesgoPrecio;
      const colorRes = rAhora >= 0 ? "var(--p-sube)" : "var(--p-baja)";
      const cuenta = o.rg != null && rAhora != null ? rAhora * o.rg : null;
      const duracion = (abierta ? D.t[c0] : D.t[o.ix]) - D.t[o.ie];
      const dur = duracion >= 48 ? `${f1.format(duracion / 24)} días` : `${duracion} horas`;
      caja.innerHTML = `
        <div class="ficha__estrategia" style="--c:${colorEstrategia(C, o.e)}"><i></i>Estrategia ${nombreEstrategia(o.e).toLowerCase()}</div>
        <h3>${lado} en ${D.m}</h3>
        <p class="ficha__cuando">${fechaHora(D.t[o.ie])}</p>
        <div class="ficha__resultado" style="--c:${colorRes}">
          <b>${rAhora == null ? "—" : signo(rAhora, f2) + " R"}</b>
          <span>${abierta ? "Operación abierta, resultado hasta ahora" : textoMotivo(o.motivo)}${cuenta != null ? `, ${pct(cuenta, f2)} de la cuenta` : ""}</span>
        </div>
        <dl>
          <dt>Entrada</dt><dd>${precio(o.pe)}</dd>
          <dt>Stop</dt><dd>${precio(o.sl)}</dd>
          <dt>Objetivo</dt><dd>${o.tp != null ? precio(o.tp) : "Sin techo"}</dd>
          ${!abierta && o.ps != null ? `<dt>Salida</dt><dd>${precio(o.ps)}</dd>` : ""}
          ${o.rg != null ? `<dt>Riesgo de la cuenta</dt><dd>${f2.format(o.rg)}%</dd>` : ""}
          ${o.p != null ? `<dt>Confianza del modelo</dt><dd>${f0.format(o.p * 100)}%</dd>` : ""}
          <dt>Duración</dt><dd>${abierta ? "lleva " : ""}${dur}</dd>
        </dl>
        ${est ? `<p class="ficha__porque">${est.porque}</p>` : ""}
        ${E.seleccion ? '<p class="ficha__fijada"><button type="button" id="soltar">Seguir la última operación</button></p>' : ""}
      `;
      const soltar = $("soltar");
      if (soltar) soltar.addEventListener("click", () => { E.seleccion = null; actualizarFicha(); dibujar(); });
    }

    // acumulado de la moneda hasta la fecha
    const cerradas = opsVisibles().filter((x) => x.ix != null && x.ix <= c0);
    const gan = cerradas.filter((x) => x.r > 0).length;
    const total = cerradas.reduce((s, x) => s + x.r, 0);
    $("ficha-acumulado").innerHTML = cerradas.length
      ? `Hasta esta fecha en ${D.m}: <b>${cerradas.length}</b> operaciones cerradas, <b>${gan}</b> ganadoras, resultado <b>${signo(total, f1)} R</b>.`
      : `Todavía no cerró ninguna operación en ${D.m}.`;
  }

  async function abrirMoneda(m, conservarFecha) {
    setReproduciendo(false);
    $("cargando").hidden = false;
    $("cargando").textContent = "Cargando velas…";
    const horaPrevia = E.moneda && conservarFecha ? E.moneda.t[cur()] : null;
    try {
      E.moneda = await cargarMoneda(m);
    } catch (e) {
      $("cargando").textContent = `No pude cargar ${m}. Revisá que exista replay/monedas/${m}.js.`;
      return;
    }
    const D = E.moneda;
    E.seleccion = null;
    linea.max = D.n - 1;
    if (horaPrevia != null) {
      let i = D.t.findIndex((t) => t >= horaPrevia);
      E.cursor = i < 0 ? D.n - 1 : Math.max(i, 220);
    } else {
      const primera = opsVisibles()[0];
      E.cursor = primera ? Math.min(D.n - 1, Math.max(primera.ie - 40, 220)) : Math.min(D.n - 1, 400);
    }
    E.velasVisibles = 160;
    E.seguir = true;
    $("btn-seguir").hidden = true;
    ajustarVista();
    linea.value = cur();
    $("cargando").hidden = true;
    actualizarFicha();
    dibujar();
  }

  // ==================================================================
  // 2. RESULTADOS
  // ==================================================================
  const O = R.oficiales || {};
  const cifras = [
    { t: "Rendimiento anual", v: pct(O.rendimiento_anual), d: "Lo que creció la cuenta por año, en promedio." },
    { t: "Peor caída", v: pctLibre(O.caida_maxima), d: "La mayor baja desde un máximo hasta el punto más bajo." },
    { t: "Años con ganancia", v: O.anios_positivos, d: "Ningún año calendario terminó en pérdida." },
    { t: "Sharpe", v: f2.format(O.sharpe), d: "Ganancia por unidad de riesgo. Por encima de 1 se considera bueno." },
  ];
  $("cifras").innerHTML = cifras.map((c) => `<div><dt>${c.t}</dt><dd><b>${c.v}</b><span>${c.d}</span></dd></div>`).join("");

  const calc = R.calculadas;
  $("pie-curva").textContent = (R.curva_oficial ? "Curva de capital del backtest" : "Curva reconstruida a partir de las operaciones")
    + `: ${pct(calc.cagr)} anual, peor caída ${pctLibre(calc.caida)}. Escala logarítmica, para que un mismo porcentaje se vea igual en cualquier momento.`;

  // --- gráfico de líneas genérico
  function graficoLineas(canvas, obtener) {
    const tip = document.createElement("div");
    tip.className = "tip";
    tip.hidden = true;
    document.body.appendChild(tip);
    let hoverX = null;
    function dibujarL() {
      const { series, log, franjaDesde, formato } = obtener();
      const K = colores(document.documentElement);
      const { ctx, w, h } = prepararLienzo(canvas);
      ctx.clearRect(0, 0, w, h);
      const ML = 10, MR = 62, MT = 12, MB = 26;
      const W = w - ML - MR, H = h - MT - MB;
      let t0 = Infinity, t1 = -Infinity, v0 = Infinity, v1 = -Infinity;
      for (const s of series) {
        if (!s.t.length) continue;
        t0 = Math.min(t0, s.t[0]); t1 = Math.max(t1, s.t[s.t.length - 1]);
        for (const v of s.v) if (v > 0 || !log) { v0 = Math.min(v0, v); v1 = Math.max(v1, v); }
      }
      if (!isFinite(t0)) return;
      const tr = (v) => (log ? Math.log(Math.max(v, 1e-9)) : v);
      let a = tr(v0), b = tr(v1);
      const pad = (b - a) * 0.06 || 1;
      a -= pad; b += pad;
      const X = (t) => ML + ((t - t0) / (t1 - t0 || 1)) * W;
      const Y = (v) => MT + (1 - (tr(v) - a) / (b - a)) * H;
      ctx.font = "12px " + getComputedStyle(document.body).fontFamily;

      // franja fuera de muestra
      if (franjaDesde != null) {
        const tf = Date.UTC(franjaDesde, 0, 1) / 86400e3;
        if (tf > t0 && tf < t1) {
          ctx.fillStyle = conAlfa(K.pRegla, 0.35);
          ctx.fillRect(X(tf), MT, X(t1) - X(tf), H);
          ctx.fillStyle = K.pTinta3;
          ctx.textAlign = "left";
          ctx.textBaseline = "top";
          ctx.fillText("Datos nuevos", X(tf) + 8, MT + 6);
          ctx.textAlign = "right";
          ctx.fillText("Datos de diseño", X(tf) - 8, MT + 6);
        }
      }

      // grilla horizontal
      ctx.textBaseline = "middle";
      ctx.textAlign = "left";
      ctx.strokeStyle = conAlfa(K.pRegla, 0.8);
      ctx.lineWidth = 1;
      const marcas = [];
      if (log) {
        const cand = [10, 20, 25, 50, 75, 100, 150, 200, 300, 500, 750, 1000, 1500, 2000, 3000, 5000, 10000, 20000, 50000, 100000];
        const vis = cand.filter((v) => tr(v) >= a && tr(v) <= b);
        const salto = Math.ceil(vis.length / Math.max(3, Math.floor(H / 48)));
        vis.forEach((v, i) => { if (i % salto === 0) marcas.push(v); });
      } else {
        const p = pasoLindo(b - a, Math.max(3, Math.floor(H / 48)));
        for (let v = Math.ceil(a / p) * p; v <= b; v += p) marcas.push(v);
      }
      for (const v of marcas) {
        const py = Math.round(Y(v)) + 0.5;
        ctx.beginPath(); ctx.moveTo(ML, py); ctx.lineTo(ML + W, py); ctx.stroke();
        ctx.fillStyle = K.pTinta3;
        ctx.fillText(formato(v), ML + W + 8, py);
      }
      // años
      ctx.textAlign = "center";
      ctx.textBaseline = "alphabetic";
      const a0 = new Date(t0 * 86400e3).getUTCFullYear(), a1 = new Date(t1 * 86400e3).getUTCFullYear();
      for (let an = a0 + 1; an <= a1; an++) {
        const ta = Date.UTC(an, 0, 1) / 86400e3;
        ctx.strokeStyle = conAlfa(K.pRegla, 0.5);
        ctx.beginPath(); ctx.moveTo(Math.round(X(ta)) + 0.5, MT + H); ctx.lineTo(Math.round(X(ta)) + 0.5, MT + H + 5); ctx.stroke();
        ctx.fillStyle = K.pTinta3;
        ctx.fillText(String(an), X(ta), h - 7);
      }
      // líneas
      for (const s of series) {
        ctx.strokeStyle = s.color(K);
        ctx.lineWidth = s.ancho || 2;
        ctx.lineJoin = "round";
        if (s.punteada) ctx.setLineDash([4, 4]);
        ctx.beginPath();
        const salto = Math.max(1, Math.floor(s.t.length / (W * 1.5)));
        for (let i = 0; i < s.t.length; i += salto) {
          const px = X(s.t[i]), py = Y(Math.max(s.v[i], log ? 1e-9 : s.v[i]));
          i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
        }
        const u = s.t.length - 1;
        ctx.lineTo(X(s.t[u]), Y(s.v[u]));
        ctx.stroke();
        ctx.setLineDash([]);
      }
      // hover
      if (hoverX != null && hoverX >= ML && hoverX <= ML + W) {
        const th = t0 + ((hoverX - ML) / W) * (t1 - t0);
        ctx.strokeStyle = conAlfa(K.pTinta, 0.35);
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(Math.round(hoverX) + 0.5, MT); ctx.lineTo(Math.round(hoverX) + 0.5, MT + H); ctx.stroke();
        const filas = [];
        for (const s of series) {
          if (s.sinTip) continue;
          let i = s.t.findIndex((t) => t >= th);
          if (i < 0) i = s.t.length - 1;
          const px = X(s.t[i]), py = Y(s.v[i]);
          ctx.fillStyle = s.color(K);
          ctx.strokeStyle = K.pFondo;
          ctx.lineWidth = 2;
          ctx.beginPath(); ctx.arc(px, py, 4.5, 0, Math.PI * 2); ctx.stroke(); ctx.fill();
          filas.push(`<div><i style="--c:${s.color(K)}"></i>${s.nombre}: <b>${formato(s.v[i], true)}</b></div>`);
        }
        const d = new Date(th * 86400e3);
        tip.innerHTML = `<div>${d.getUTCDate()} ${MESES[d.getUTCMonth()]} ${d.getUTCFullYear()}</div>${filas.join("")}`;
        tip.hidden = false;
      } else tip.hidden = true;
    }
    canvas.addEventListener("pointermove", (ev) => {
      const r = canvas.getBoundingClientRect();
      hoverX = ev.clientX - r.left;
      dibujarL();
      const ancho = tip.offsetWidth;
      const izquierda = ev.clientX + 16 + ancho > window.innerWidth ? ev.clientX - ancho - 16 : ev.clientX + 16;
      tip.style.left = izquierda + "px";
      tip.style.top = ev.clientY + 14 + "px";
    });
    canvas.addEventListener("pointerleave", () => { hoverX = null; tip.hidden = true; dibujarL(); });
    return dibujarL;
  }

  const formatoIndice = (v, largo) => (largo ? f0.format(v) + " USD" : f0.format(v));
  const series = [{ nombre: "Rogelio", t: R.curva.t, v: R.curva.v, color: (K) => K.pTinta, ancho: 2.2 }];
  if (R.btc) series.push({ nombre: "Comprar y mantener Bitcoin", t: R.btc.t, v: R.btc.v, color: (K) => K.pBtc, ancho: 1.6 });
  const dibujarCurva = graficoLineas($("lienzo-curva"), () => ({
    series, log: true, franjaDesde: R.fuera_de_muestra, formato: formatoIndice,
  }));
  $("leyenda-curva").innerHTML =
    `<li><span class="linea" style="--c:var(--tinta)"></span>Rogelio</li>` +
    (R.btc ? `<li><span class="linea" style="--c:var(--btc)"></span>Comprar y mantener Bitcoin, como referencia</li>` : "") +
    `<li><span class="franja"></span>Desde ${R.fuera_de_muestra}: datos que Rogelio no conocía cuando se diseñó</li>`;

  // --- barras por año
  (function () {
    const datos = calc.por_anio;
    const max = Math.max(...datos.map((d) => Math.abs(d.rend)), 1);
    const hayNeg = datos.some((d) => d.rend < 0);
    const cero = hayNeg ? 50 : 0;
    const anioActual = new Date().getUTCFullYear();
    $("barras-anio").innerHTML = datos.map((d) => {
      const largo = (Math.abs(d.rend) / max) * (hayNeg ? 50 : 100);
      const izq = d.rend >= 0 ? cero : cero - largo;
      const color = d.rend >= 0 ? "var(--sube)" : "var(--baja)";
      const parcial = d.anio === anioActual || d.anio === datos[datos.length - 1].anio && d.anio >= anioActual - 1;
      return `<div class="barra${d.anio >= R.fuera_de_muestra ? " barra--nuevo" : ""}" title="${d.anio}: ${pct(d.rend)}${parcial ? " (año incompleto)" : ""}">
        <span class="barra__anio">${d.anio}</span>
        <span class="barra__pista" style="--cero:${cero}%"><span class="barra__valor" style="left:${izq}%;width:${largo}%;--c:${color}"></span></span>
        <span class="barra__num">${pct(d.rend)}</span></div>`;
    }).join("") + `<p class="barras__nota">• Años con datos nuevos. El último año puede estar incompleto.</p>`;
  })();

  // --- estrategias
  (function () {
    const K = colores(document.documentElement);
    $("tabla-estrategias").innerHTML = R.operaciones.por_estrategia.map((s) => `
      <div class="estrategia">
        <h4><i style="--c:${colorEstrategia(K, s.e, false)}"></i>${nombreEstrategia(s.e)}</h4>
        <p>${ESTRATEGIAS[s.e] ? ESTRATEGIAS[s.e].corto : ""}</p>
        <dl>
          <div><dt>Operaciones</dt><dd>${f0.format(s.n)}</dd></div>
          <div><dt>Ganadoras</dt><dd>${f0.format(s.ganadoras)}%</dd></div>
          <div><dt>Resultado medio</dt><dd>${signo(s.r_medio, f2)} R</dd></div>
        </dl>
      </div>`).join("");
  })();

  // ==================================================================
  // 3. SIMULADOR DE RIESGO
  // ==================================================================
  const opsOrden = R.ops.map((o) => ({ ...o, fin: o.ts != null ? o.ts : o.te })).sort((a, b) => a.fin - b.fin);
  const riesgoBase = (() => {
    const v = R.ops.filter((o) => o.e === "vendedor" || o.e === "comprador").map((o) => o.rg);
    const lista = v.length ? v : R.ops.map((o) => o.rg);
    return lista.reduce((s, x) => s + x, 0) / lista.length;
  })();

  function curvaConFactor(f) {
    let cap = 100, pico = 100, peor = 0;
    const t = [Math.floor(opsOrden[0].te / 24) - 1], v = [100];
    for (const o of opsOrden) {
      cap = Math.max(0, cap * (1 + (o.r * o.rg * f) / 100));
      pico = Math.max(pico, cap);
      peor = Math.min(peor, cap / pico - 1);
      const dia = Math.floor(o.fin / 24);
      if (t[t.length - 1] === dia) v[v.length - 1] = cap;
      else { t.push(dia); v.push(cap); }
    }
    const anios = (t[t.length - 1] - t[0]) / 365.25;
    const anual = cap > 0 ? (Math.pow(cap / 100, 1 / anios) - 1) * 100 : -100;
    return { t, v, anual, caida: peor * 100, final: cap };
  }
  const base = curvaConFactor(1);
  let actual = base;
  const dibujarRiesgo = graficoLineas($("lienzo-riesgo"), () => ({
    series: [
      { nombre: "Riesgo real", t: base.t, v: base.v, color: (K) => K.pBtc, ancho: 1.6, punteada: true },
      { nombre: "Con el riesgo elegido", t: actual.t, v: actual.v, color: (K) => K.pTinta, ancho: 2.2 },
    ],
    log: true, franjaDesde: null, formato: formatoIndice,
  }));
  const ctrl = $("ctrl-riesgo");
  function actualizarRiesgo() {
    const f = Number(ctrl.value);
    actual = curvaConFactor(f);
    $("salida-riesgo").textContent = `${f2.format(riesgoBase * f)}% de la cuenta`;
    $("sim-anual").textContent = pct(actual.anual);
    $("sim-caida").textContent = pctLibre(actual.caida);
    $("sim-final").textContent = f0.format(actual.final * 10) + " USD";
    $("sim-alerta").hidden = actual.caida > -20;
    dibujarRiesgo();
  }
  ctrl.addEventListener("input", actualizarRiesgo);

  // ==================================================================
  // Arranque
  // ==================================================================
  function redibujarTodo() {
    C = colores(pantalla);
    dibujar();
    dibujarCurva();
    dibujarRiesgo();
  }
  let pendiente = null;
  window.addEventListener("resize", () => {
    cancelAnimationFrame(pendiente);
    pendiente = requestAnimationFrame(redibujarTodo);
  });
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", redibujarTodo);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(redibujarTodo);

  actualizarRiesgo();
  dibujarCurva();
  const inicial = R.monedas.find((x) => x.m === "BTC") ? "BTC" : R.monedas[0] && R.monedas[0].m;
  if (inicial) {
    sel.value = inicial;
    abrirMoneda(inicial, false).then(() => {
      // Un único momento de movimiento: la repetición arranca sola, salvo
      // que la persona prefiera menos animación.
      if (!reducirMovimiento) { E.velocidad = 1; [...vel.children].forEach((x, j) => x.setAttribute("aria-pressed", String(j === 1))); setReproduciendo(true); }
    });
  } else {
    $("cargando").textContent = "No hay velas para mostrar. Revisá la carpeta datos/ y corré exportar_web.py.";
  }

  // Pausar la repetición cuando no se ve, para no gastar batería.
  if ("IntersectionObserver" in window) {
    let pausadaPorScroll = false;
    new IntersectionObserver(([e]) => {
      if (!e.isIntersecting && E.reproduciendo) { pausadaPorScroll = true; setReproduciendo(false); }
      else if (e.isIntersecting && pausadaPorScroll) { pausadaPorScroll = false; setReproduciendo(true); }
    }, { threshold: 0.15 }).observe(pantalla);
  }
})();
