/* LockMaker — pestañas + panel de Ajustes rápidos */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const api = async (url, body) => {
    const r = await fetch(url, body === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    return r.json();
  };
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // ------------------------------------------------ pestañas
  function showTab(name) {
    $$(".tab").forEach(t => t.classList.toggle("on", t.dataset.tab === name));
    $("#quick").hidden = name !== "quick";
    $("#designer").hidden = name !== "designer";
    try { localStorage.setItem("lm.tab", name); } catch (e) {}
    if (name === "designer") window.dispatchEvent(new Event("resize"));   // refresca la vista previa
  }
  $$(".tab").forEach(t => t.addEventListener("click", () => showTab(t.dataset.tab)));
  try { const t = localStorage.getItem("lm.tab"); if (t) showTab(t); } catch (e) {}

  // ------------------------------------------------ toast
  let toastT;
  function toast(msg, err = false) {
    let el = $(".toast"); if (!el) { el = document.createElement("div"); el.className = "toast"; document.body.appendChild(el); }
    el.textContent = msg; el.classList.toggle("err", err); el.hidden = false;
    clearTimeout(toastT); toastT = setTimeout(() => { el.hidden = true; }, err ? 6000 : 2200);
  }

  // ------------------------------------------------ render
  let data = null;
  function control(it) {
    const v = it.value;
    if (it.type === "toggle")
      return `<label class="sw"><input type="checkbox" ${v ? "checked" : ""} aria-label="${esc(it.label)}"><span></span></label>`;
    if (it.type === "select")
      return `<select aria-label="${esc(it.label)}">${it.options.map(o => `<option ${String(o) === String(v) ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
    if (it.type === "color")
      return `<input type="color" value="${esc(v || "#5b7cff")}" aria-label="${esc(it.label)}">`;
    if (it.type === "slider")
      return `<div class="sl"><input type="range" min="${it.min}" max="${it.max}" step="${it.step}" value="${v}" aria-label="${esc(it.label)}"><output>${v}</output></div>`;
    return "";
  }
  function render() {
    const q = $("#qsearch").value.trim().toLowerCase();
    const groups = {};
    for (const it of data.items) {
      if (q && !(it.label + " " + it.group).toLowerCase().includes(q)) continue;
      (groups[it.group] = groups[it.group] || []).push(it);
    }
    const names = Object.keys(groups);
    $("#qgrid").innerHTML = names.length ? names.map(g => `
      <div class="qcard"><h3>${esc(g)}</h3>${groups[g].map(it => `
        <div class="qitem" data-id="${esc(it.id)}" data-type="${it.type}">
          <div class="ql">${esc(it.label)}${it.changed ? '<span class="dot" title="cambiado desde LockMaker">●</span>' : ""}${it.admin ? '<span class="adm">admin</span>' : ""}
            ${it.note ? `<small>${esc(it.note)}</small>` : ""}</div>
          ${control(it)}
        </div>`).join("")}</div>`).join("")
      : `<div class="qempty">${data.items.length ? "Ningún ajuste coincide con la búsqueda." :
          "No se reconoció un escritorio compatible (Windows, GNOME, KDE, Cinnamon, XFCE)."}</div>`;
    $("#qinfo").textContent = `${data.env} · ${data.items.length} ajustes`;
    $("#qrestore").disabled = !data.changed;
    $("#qrestore").textContent = data.changed ? `Restaurar originales (${data.changed})` : "Restaurar originales";
  }
  function renderLinks() {
    $("#qlinks").innerHTML = data.links.map(l => `<button class="btn" data-target="${esc(l.target)}">${esc(l.label)} ↗</button>`).join("")
      || '<span class="qinfo">Tu escritorio no tiene un panel de configuración enlazable.</span>';
    $("#qactions").innerHTML = data.actions.map(a => `<button class="btn" data-action="${esc(a.id)}" title="${esc(a.note)}">${esc(a.label)}</button>`).join("");
  }
  async function load() {
    try { data = await api("/api/quick"); } catch (e) { $("#qgrid").innerHTML = `<div class="qempty">Error: ${esc(e.message)}</div>`; return; }
    render(); renderLinks();
  }

  // ------------------------------------------------ aplicar cambios
  async function apply(row, value) {
    const id = row.dataset.id;
    row.classList.add("busy");
    const j = await api("/api/quick/set", { id, value }).catch(e => ({ error: e.message }));
    row.classList.remove("busy");
    const it = data.items.find(x => x.id === id);
    if (j.error) { toast(j.error, true); load(); return; }
    const was = it.changed;
    it.value = j.value; it.changed = j.changed;
    data.changed += (j.changed ? 1 : 0) - (was ? 1 : 0);
    render();
    const nr = $(`.qitem[data-id="${CSS.escape(id)}"]`); if (nr) nr.classList.add("flash");
    toast(j.restart_explorer ? "Aplicado. Pulsa «Reiniciar Explorador» para verlo." : "Aplicado: " + it.label);
  }
  const grid = $("#qgrid");
  grid.addEventListener("change", e => {
    const row = e.target.closest(".qitem"); if (!row) return;
    const t = row.dataset.type, el = e.target;
    if (t === "toggle") apply(row, el.checked);
    else if (t === "slider") apply(row, parseFloat(el.value));
    else apply(row, el.value);
  });
  grid.addEventListener("input", e => {   // número en vivo del deslizador
    if (e.target.type === "range") e.target.parentElement.querySelector("output").value = e.target.value;
  });
  $("#qsearch").addEventListener("input", () => data && render());
  $("#qreload").addEventListener("click", () => { load(); toast("Valores releídos del sistema"); });
  $("#qrestore").addEventListener("click", async () => {
    if (!confirm("¿Devolver a su valor original los ajustes cambiados desde LockMaker?")) return;
    const j = await api("/api/quick/restore", {});
    const errs = Object.keys(j.errors || {});
    toast(`Restaurados: ${j.restored.length}` + (errs.length ? ` · con error: ${errs.join(", ")}` : ""), !!errs.length);
    load();
  });
  $("#qlinks").addEventListener("click", async e => {
    const b = e.target.closest("button[data-target]"); if (!b) return;
    const j = await api("/api/quick/open", { target: b.dataset.target });
    if (j.error) toast(j.error, true);
  });
  $("#qactions").addEventListener("click", async e => {
    const b = e.target.closest("button[data-action]"); if (!b) return;
    b.disabled = true;
    const j = await api("/api/quick/action", { id: b.dataset.action });
    b.disabled = false;
    toast(j.error || j.msg, !!j.error);
  });

  load();
})();
