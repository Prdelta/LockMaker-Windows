/* LockMaker editor — sin frameworks, todo con fetch al servidor local. */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const log = (m, cls = "") => { const l = $("#log"); const d = document.createElement("div"); d.className = cls; d.textContent = m; l.prepend(d); };

  const style = {};            // estado del overlay (espejo de core.render.Style)
  let hasImage = false, imgSize = null, info = null;

  // ------------------------------------------------------------- controles
  const controls = $$("[data-k]");
  function readControl(el) {
    const k = el.dataset.k;
    if (el.type === "checkbox") style[k] = el.checked;
    else if (el.type === "range") style[k] = parseFloat(el.value);
    else style[k] = el.value;
    const out = el.parentElement.querySelector("output");
    if (out) out.value = el.value;
  }
  function setControl(k, v) {
    const el = controls.find(e => e.dataset.k === k);
    if (!el) { style[k] = v; return; }
    if (el.type === "checkbox") el.checked = !!v; else el.value = v;
    readControl(el);
  }
  controls.forEach(el => {
    readControl(el);
    el.addEventListener("input", () => { readControl(el); schedulePreview(); });
  });

  // resolución
  function applyRes() {
    const v = $("#res").value;
    let w = 1920, h = 1080;
    if (v === "screen") { w = Math.round(screen.width * devicePixelRatio); h = Math.round(screen.height * devicePixelRatio); }
    else if (v === "image") { if (imgSize) [w, h] = imgSize; }
    else [w, h] = v.split("x").map(Number);
    style.width = w; style.height = h;
  }
  $("#res").addEventListener("change", () => { applyRes(); schedulePreview(); });
  applyRes();

  // ------------------------------------------------------------- preview
  let timer = null, inflight = false, dirty = false, lastUrl = null;
  function schedulePreview() { dirty = true; clearTimeout(timer); timer = setTimeout(doPreview, 90); }
  async function doPreview() {
    if (!hasImage) return;
    if (inflight) { dirty = true; return; }
    inflight = true; dirty = false; $("#spin").hidden = false;
    try {
      const maxW = Math.min(1400, Math.round($("#stage").clientWidth * devicePixelRatio));
      const r = await fetch("/api/preview", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ style, max_w: maxW }) });
      if (!r.ok) throw new Error(await r.text());
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      $("#preview").src = url;
      if (lastUrl) URL.revokeObjectURL(lastUrl);
      lastUrl = url;
    } catch (e) { log("Vista previa: " + e.message, "err"); }
    inflight = false; $("#spin").hidden = true;
    if (dirty) schedulePreview();
  }

  // ------------------------------------------------------------- imagen
  async function upload(file) {
    if (!file) return;
    const r = await fetch("/api/image", { method: "POST", headers: { "X-Filename": encodeURIComponent(file.name) }, body: file });
    const j = await r.json();
    if (j.error) return log("Imagen: " + j.error, "err");
    hasImage = true; imgSize = j.size;
    $("#drop").hidden = true; $("#pwrap").hidden = false;
    log(`Imagen cargada: ${file.name} (${j.size[0]}×${j.size[1]})`, "ok");
    if ($("#res").value === "image") applyRes();
    schedulePreview();
  }
  $("#file").addEventListener("change", e => upload(e.target.files[0]));
  $("#file").accept = "image/*,.gif,.webp";
  $("#pick").addEventListener("click", () => $("#file").click());
  $("#pick2").addEventListener("click", () => $("#file").click());
  const stage = $("#stage");
  ["dragenter", "dragover"].forEach(ev => stage.addEventListener(ev, e => { e.preventDefault(); $("#drop").classList.add("over"); }));
  ["dragleave", "drop"].forEach(ev => stage.addEventListener(ev, e => { e.preventDefault(); $("#drop").classList.remove("over"); }));
  stage.addEventListener("drop", e => upload(e.dataTransfer.files[0]));
  document.addEventListener("paste", e => { const f = [...(e.clipboardData.files || [])][0]; if (f) upload(f); });

  // arrastrar el bloque de texto sobre la vista previa
  const pv = $("#preview");
  let drag = null;
  pv.addEventListener("pointerdown", e => {
    drag = { x: e.clientX, y: e.clientY, sx: style.x, sy: style.y };
    pv.setPointerCapture(e.pointerId); pv.classList.add("dragging");
  });
  pv.addEventListener("pointermove", e => {
    if (!drag) return;
    const rect = pv.getBoundingClientRect();
    setControl("x", Math.max(0, Math.min(100, drag.sx + (e.clientX - drag.x) / rect.width * 100)).toFixed(1));
    setControl("y", Math.max(0, Math.min(100, drag.sy + (e.clientY - drag.y) / rect.height * 100)).toFixed(1));
    schedulePreview();
  });
  pv.addEventListener("pointerup", () => { drag = null; pv.classList.remove("dragging"); });
  pv.addEventListener("wheel", e => {
    e.preventDefault();
    setControl("scale", Math.max(0.3, Math.min(3, style.scale * (e.deltaY < 0 ? 1.05 : 0.95))).toFixed(2));
    schedulePreview();
  }, { passive: false });

  // ------------------------------------------------------------- galería
  function renderGallery(list) {
    $("#gallery").innerHTML = list.map(w =>
      `<div class="cell"><img src="${w.thumb}?v=${Date.now()}" title="${w.name}${w.builtin ? "" : " (clic derecho: borrar)"}" data-file="${w.file}" data-builtin="${w.builtin}" loading="lazy" alt="${w.name}">${w.animated ? '<span class="badge">GIF</span>' : ""}</div>`).join("");
  }
  function useImage(j, label) {
    hideAnimPreview();
    hasImage = true; imgSize = j.size; $("#drop").hidden = true; $("#pwrap").hidden = false;
    if ($("#res").value === "image") applyRes();
    log(label + ": " + j.name, "ok"); schedulePreview();
  }
  async function loadGallery() {
    renderGallery(await (await fetch("/api/wallpapers")).json());
    const g = $("#gallery");
    g.addEventListener("click", async e => {
      const img = e.target.closest("img"); if (!img) return;
      const j = await (await fetch("/api/wallpaper/use", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file: img.dataset.file }) })).json();
      if (j.error) return log(j.error, "err");
      $$(".gallery img").forEach(i => i.classList.toggle("sel", i === img));
      useImage(j, "Wallpaper");
    });
    g.addEventListener("contextmenu", async e => {
      const img = e.target.closest("img"); if (!img) return;
      e.preventDefault();
      if (img.dataset.builtin === "true") return log("Los fondos incluidos no se borran.");
      if (!confirm("¿Borrar " + img.dataset.file + " de la galería?")) return;
      const j = await (await fetch("/api/wallpaper/delete", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file: img.dataset.file }) })).json();
      renderGallery(j.wallpapers || []);
    });
    $("#wadd").addEventListener("click", async () => {
      const url = $("#wurl").value.trim(); if (!url) return;
      const b = $("#wadd"); b.disabled = true; b.textContent = "…";
      try {
        const j = await (await fetch("/api/wallpaper/url", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url }) })).json();
        if (j.error) throw new Error(j.error);
        renderGallery(j.wallpapers || []); $("#wurl").value = "";
        useImage(j, "Descargado");
      } catch (e) { log("URL: " + e.message, "err"); }
      b.disabled = false; b.textContent = "Añadir";
    });
    $("#wurl").addEventListener("keydown", e => { if (e.key === "Enter") $("#wadd").click(); });
    // buscadores de wallpapers con la consulta ya puesta
    const SITES = [
      ["Wallhaven", q => "https://wallhaven.cc/search?q=" + q + "&categories=010&purity=100&atleast=1920x1080&sorting=relevance"],
      ["Pixabay (libre)", q => "https://pixabay.com/images/search/" + q + "/"],
      ["Unsplash", q => "https://unsplash.com/s/illustrations/" + q],
      ["Pexels", q => "https://www.pexels.com/search/" + q + "/"],
      ["Pixiv", q => "https://www.pixiv.net/en/tags/" + q + "/illustrations"],
      ["Google Imágenes", q => "https://www.google.com/search?tbm=isch&tbs=isz:l&q=" + q + "+wallpaper"],
    ];
    function renderLinks() {
      const q = encodeURIComponent($("#wq").value.trim() || "anime wallpaper");
      $("#wlinks").innerHTML = SITES.map(([n, f]) => `<a href="${f(q)}" target="_blank" rel="noopener">${n} ↗</a>`).join("");
    }
    $("#wsearch").addEventListener("click", renderLinks);
    $("#wq").addEventListener("keydown", e => { if (e.key === "Enter") renderLinks(); });
    $("#wchips").addEventListener("click", e => {
      const c = e.target.closest("span[data-q]"); if (!c) return;
      $$("#wchips span").forEach(x => x.classList.toggle("on", x === c));
      $("#wq").value = c.dataset.q; renderLinks();
    });
    renderLinks();
  }

  // ------------------------------------------------------------- animación
  const anim = {};
  const actrls = $$("[data-a]");
  function readA(el) {
    const k = el.dataset.a;
    anim[k] = el.type === "checkbox" ? el.checked : (el.type === "range" ? parseFloat(el.value) : el.value);
    const out = el.parentElement.querySelector("output"); if (out) out.value = el.value;
  }
  actrls.forEach(el => { readA(el); el.addEventListener("input", () => readA(el)); });
  function animRes() { const [w, h] = $("#ares").value.split("x").map(Number); anim.out_w = w; anim.out_h = h; }
  $("#ares").addEventListener("change", animRes); animRes();
  let animUrl = null;
  function showAnimPreview(fmt) {
    const wrap = $("#pwrap"); wrap.hidden = false; $("#drop").hidden = true;
    const old = $("#animprev"); if (old) old.remove();
    let el;
    if (fmt === "gif") { el = document.createElement("img"); el.src = "/api/animate/file?t=" + Date.now(); }
    else { el = document.createElement("video"); el.src = "/api/animate/file?t=" + Date.now(); el.autoplay = true; el.loop = true; el.muted = true; el.playsInline = true; }
    el.id = "animprev"; el.style.cssText = "max-width:100%;max-height:calc(100vh - 110px);display:block;border-radius:8px;box-shadow:0 20px 60px rgba(0,0,0,.5)";
    $("#preview").hidden = true; wrap.prepend(el);
  }
  function hideAnimPreview() { const old = $("#animprev"); if (old) old.remove(); $("#preview").hidden = false; }
  const _sched = schedulePreview;
  $("#agen").addEventListener("click", async () => {
    const fmt = $("#afmt").value;
    const j = await (await fetch("/api/animate", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ style, anim, fmt, source: $("#asrc").value }) })).json();
    if (j.error) return log(j.error, "err");
    $("#agen").disabled = true; $("#aprog").hidden = false; $("#adl").disabled = true; $("#alive").disabled = true;
    const poll = setInterval(async () => {
      const st = await (await fetch("/api/animate/status")).json();
      $("#aprog div").style.width = (st.total ? Math.round(100 * st.done / st.total) : 0) + "%";
      if (!st.running) {
        clearInterval(poll); $("#agen").disabled = false; $("#aprog").hidden = true;
        if (st.error) return log("Animación: " + st.error, "err");
        log(`Animación lista (${st.fmt.toUpperCase()}, ${(st.size / 1048576).toFixed(1)} MB)`, "ok");
        $("#adl").disabled = false; $("#alive").disabled = false; showAnimPreview(st.fmt);
      }
    }, 500);
  });
  $("#adl").addEventListener("click", () => { location.href = "/api/animate/file?download=1"; });
  $("#alive").addEventListener("click", async () => {
    const j = await (await fetch("/api/live/apply", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ persist: $("#apersist").checked }) })).json();
    log(j.error || j.msg, j.error ? "err" : "ok");
  });
  $("#astop").addEventListener("click", async () => {
    const j = await (await fetch("/api/live/stop", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })).json();
    log(j.error || j.msg, j.error ? "err" : "ok");
  });
  // cualquier cambio en el editor vuelve a la vista previa estática
  controls.forEach(el => el.addEventListener("input", hideAnimPreview));

  // ------------------------------------------------------------- presets
  function fillPresets(list) {
    const sel = $("#presets");
    sel.innerHTML = '<option value="">— elegir —</option>' +
      list.map(p => `<option value="${p.path}">${p.kind === "builtin" ? "★ " : ""}${p.name}</option>`).join("");
  }
  function loadStyle(s) { for (const [k, v] of Object.entries(s || {})) setControl(k, v); if (s.width && s.height) { style.width = s.width; style.height = s.height; } }
  $("#presets").addEventListener("change", async e => {
    if (!e.target.value) return;
    const r = await fetch("/api/preset?name=" + encodeURIComponent(e.target.value));
    const j = await r.json();
    if (j.error) return log("Preset: " + j.error, "err");
    loadStyle(j.style);
    if (j.image) { const i = await (await fetch("/api/info")).json(); if (i.has_image) { hasImage = true; imgSize = i.image_size; $("#drop").hidden = true; $("#pwrap").hidden = false; } }
    log("Preset cargado", "ok"); schedulePreview();
  });
  $("#psave").addEventListener("click", async () => {
    const name = $("#pname").value.trim() || "mi preset";
    const j = await (await fetch("/api/preset/save", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, style }) })).json();
    if (j.error) return log(j.error, "err");
    fillPresets(j.presets); log("Preset guardado: " + name, "ok");
  });

  // ------------------------------------------------------------- aplicar
  const targets = () => $$(".targets input:checked").map(i => i.value);
  $("#apply").addEventListener("click", async () => {
    const b = $("#apply"); b.disabled = true; b.textContent = "Aplicando…";
    try {
      const j = await (await fetch("/api/apply", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ style, targets: targets() }) })).json();
      if (j.error) throw new Error(j.error);
      for (const [k, v] of Object.entries(j.results || {})) log(`${k}: ${v}`, String(v).startsWith("ERROR") ? "err" : "ok");
      if (j.need_admin && j.need_admin.length) {
        log(`${j.need_admin.join(" y ")} necesitan administrador → pidiendo permiso (UAC)…`);
        const e = await (await fetch("/api/elevate", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ targets: j.need_admin }) })).json();
        log(e.ok ? "Acepta el diálogo de Windows para terminar." : "No se pudo elevar permisos.", e.ok ? "ok" : "err");
      }
    } catch (e) { log("Error: " + e.message, "err"); }
    b.disabled = false; b.textContent = "Aplicar ahora";
  });
  $("#export").addEventListener("click", () => {
    if (!hasImage) return log("Carga una imagen primero.", "err");
    location.href = "/api/export?fmt=png&style=" + encodeURIComponent(JSON.stringify(style));
  });
  $("#auto").addEventListener("click", async () => {
    const j = await (await fetch("/api/autorefresh", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ style, targets: targets(), every: parseInt($("#every").value, 10) }) })).json();
    log(j.error || j.msg, j.error ? "err" : "ok");
  });
  $("#autooff").addEventListener("click", async () => {
    const j = await (await fetch("/api/autorefresh", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ remove: true }) })).json();
    log(j.error || j.msg, j.error ? "err" : "ok");
  });

  // ------------------------------------------------------------- init
  (async () => {
    info = await (await fetch("/api/info")).json();
    const extra = info.os === "windows" ? (info.admin ? " · administrador" : " · sin admin (se pedirá UAC para bloqueo)")
      : ` · ${info.desktop} / ${info.display_manager}`;
    $("#sysinfo").textContent = (info.os === "windows" ? "Windows" : "Linux") + extra;
    fillPresets(info.presets || []);
    loadGallery();
    (info.procedural || []).forEach(n => { const o = document.createElement("option"); o.value = "proc:" + n; o.textContent = n + " (generado)"; $("#asrc").appendChild(o); });
    if (!info.ffmpeg) { $("#atip").innerHTML += " <b>ffmpeg no detectado</b>: solo GIF; instálalo para MP4/WebM (mucho más ligeros)."; }
    if (info.live_player) log("Reproductor de fondo animado: " + info.live_player);
    if (info.current && info.current.style) { loadStyle(info.current.style); }
    if (info.has_image) { hasImage = true; imgSize = info.image_size; $("#drop").hidden = true; $("#pwrap").hidden = false; schedulePreview(); }
    (info.notes || []).forEach(n => log(n));
    const cap = info.capabilities || {};
    $$(".targets input").forEach(i => { if (cap[i.value] === false) { i.checked = false; i.disabled = true; i.parentElement.title = "no disponible en este sistema"; } });
  })();
  window.addEventListener("resize", schedulePreview);
})();
