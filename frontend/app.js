// Envía el PDF a POST /api/extract, consulta GET /api/jobs/{id} hasta que termina y muestra el JSON.
const $ = (id) => document.getElementById(id);
const form = $("form"), fileInput = $("file"), drop = $("drop");
const POLL_MS = 1000;
const DROP_TEXT = "Arrastra un PDF aquí o <u>elige un archivo</u>";

const FIELD_LABELS = {
  numero_factura: "Número de factura", fecha_emision: "Fecha de emisión", fecha_vencimiento: "Fecha de vencimiento",
  moneda: "Moneda", numero_pedido: "Número de pedido", emisor_nombre: "Emisor", emisor_id_fiscal: "ID fiscal emisor",
  cliente_nombre: "Cliente", cliente_id_fiscal: "ID fiscal cliente", cliente_email: "Email cliente",
  forma_pago: "Forma de pago", iban: "IBAN", base_imponible: "Base imponible", iva_importe: "IVA", total: "Total",
};
const LINE_COLS = [
  ["referencia", "Referencia"], ["descripcion", "Descripción"], ["cantidad", "Cant."], ["precio_unitario", "Precio"],
  ["descuento_pct", "Dto. %"], ["iva_pct", "IVA %"], ["importe", "Importe"],
];

let pdfUrl = null;       // object URL del PDF elegido, para la vista previa
let analysisSeq = 0;     // descarta respuestas de /api/analizar de un archivo anterior
let currentJob = null;   // trabajo en curso (para cancelarlo)
let lastResult = null;   // resultado mostrado (para copiarlo)

// ---------------------------------------------------------------- tema claro / oscuro

function effectiveTheme() {
  return document.documentElement.dataset.theme
    || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

function paintThemeButton() {
  const dark = effectiveTheme() === "dark";
  $("theme").textContent = dark ? "☀" : "☾";
  $("theme").title = dark ? "Cambiar a tema claro" : "Cambiar a tema oscuro";
}

$("theme").addEventListener("click", () => {
  const next = effectiveTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("tema", next); } catch { /* almacenamiento no disponible */ }
  paintThemeButton();
});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", paintThemeButton);
paintThemeButton();

// ---------------------------------------------------------------- selección de archivo

function setFile(file) {
  const dt = new DataTransfer();
  dt.items.add(file);
  fileInput.files = dt.files;
  onFileChange();
}

function onFileChange() {
  const f = fileInput.files[0];
  if (f) $("drop-text").textContent = `${f.name} · ${(f.size / 1024).toFixed(0)} KB`;
  else $("drop-text").innerHTML = DROP_TEXT;
  drop.classList.toggle("has-file", Boolean(f));
  if (pdfUrl) URL.revokeObjectURL(pdfUrl);
  pdfUrl = f ? URL.createObjectURL(f) : null;
  markSuggested(null);
  $("analysis").hidden = true;
  if (f) analyze(f);
}

// Lee el PDF en el servidor (sin OCR) y marca el método recomendado.
async function analyze(file) {
  const seq = ++analysisSeq;
  const a = $("analysis");
  a.className = "analysis";
  a.textContent = "Analizando el PDF…";
  a.hidden = false;
  const data = new FormData();
  data.append("file", file);
  try {
    const resp = await fetch("/api/analizar", { method: "POST", body: data });
    if (seq !== analysisSeq) return;
    if (!resp.ok) {
      a.className = "analysis error";
      a.textContent = await errorMessage(resp);
      return;
    }
    const info = await resp.json();
    if (seq !== analysisSeq) return;
    const pages = `${info.paginas} página${info.paginas === 1 ? "" : "s"}`;
    a.textContent = info.tiene_texto
      ? `${pages} · tiene texto seleccionable: se recomienda «Texto directo + regex»`
      : `${pages} · es un escaneo sin texto: se recomienda OCR`;
    form.method.value = info.metodo_sugerido;
    markSuggested(info.metodo_sugerido);
  } catch {
    if (seq === analysisSeq) a.hidden = true;  // el análisis es solo una ayuda: si falla, no molesta
  }
}

function markSuggested(method) {
  for (const label of form.querySelectorAll(".method")) {
    label.querySelector(".badge").hidden = label.querySelector("input").value !== method;
  }
}

fileInput.addEventListener("change", onFileChange);
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.classList.remove("over");
  if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]);
});

// ---------------------------------------------------------------- estado

function setStatus(kind, title, detail = "", progress = null) {
  const s = $("status");
  s.hidden = false;
  s.className = `card status ${kind}`;
  $("status-title").textContent = title;
  $("status-detail").textContent = detail;
  $("bar").hidden = progress === null;
  if (progress !== null) $("bar-fill").style.width = `${Math.round(progress * 100)}%`;
}

async function errorMessage(resp) {
  try {
    const body = await resp.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((d) => `${d.loc.at(-1)}: ${d.msg}`).join("; ");
  } catch { /* respuesta sin JSON */ }
  return `El servidor respondió ${resp.status} ${resp.statusText}.`;
}

function setRunning(running) {
  $("submit").disabled = running;
  $("cancel").hidden = !running;
  $("cancel").disabled = false;
  $("restart").hidden = running || $("status").hidden;
}

// ---------------------------------------------------------------- envío y seguimiento

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = fileInput.files[0];
  if (!file) {
    setStatus("error", "Falta el archivo", "Elige un PDF antes de extraer.");
    return setRunning(false);
  }

  $("result").hidden = true;
  setStatus("", "Subiendo el PDF…");
  setRunning(true);
  $("cancel").hidden = true;  // aún no hay trabajo que cancelar

  const data = new FormData();
  data.append("file", file);
  data.append("method", form.method.value);

  try {
    const resp = await fetch("/api/extract", { method: "POST", body: data });
    if (!resp.ok) throw new Error(await errorMessage(resp));
    currentJob = (await resp.json()).job_id;
    $("cancel").hidden = false;
    await follow(currentJob);
  } catch (err) {
    setStatus("error", "No se pudo procesar el PDF", err instanceof TypeError
      ? "No hay conexión con el servidor. ¿Está en marcha?" : err.message);
  } finally {
    currentJob = null;
    setRunning(false);
  }
});

function progressText(job) {
  const t = job.transcurrido_s, est = job.estimado_s;
  if (t == null) return job.etapa || "";
  const left = Math.round(est - t);
  const eta = left > 0 ? `quedan ≈ ${left} s` : "tarda algo más de lo previsto";
  return `${job.etapa || ""} · ${t} s · ${eta}`;
}

async function follow(jobId) {
  for (;;) {
    const resp = await fetch(`/api/jobs/${jobId}`);
    if (!resp.ok) throw new Error(await errorMessage(resp));
    const job = await resp.json();
    const elapsed = job.transcurrido_s != null ? ` · ${job.transcurrido_s} s` : "";

    if (job.estado === "completado") {
      setStatus("done", "Extracción completada", `${job.resultado.metodo_nombre}${elapsed}`);
      return showResult(job.resultado, jobId);
    }
    if (job.estado === "error") return setStatus("error", "No se pudo extraer", job.mensaje);
    if (job.estado === "cancelado") return setStatus("cancelled", "Extracción cancelada", "Puedes elegir otro archivo o método.");

    if (job.estado === "en_cola") setStatus("", "En cola", job.etapa || "");
    else setStatus("", "Procesando…", progressText(job), Math.min((job.transcurrido_s || 0) / job.estimado_s, 0.95));
    await new Promise((r) => setTimeout(r, POLL_MS));
  }
}

$("cancel").addEventListener("click", async () => {
  if (!currentJob) return;
  $("cancel").disabled = true;
  $("status-title").textContent = "Cancelando…";
  // El seguimiento continúa hasta que el servidor confirma el estado final (cancelado, o completado si ya acababa).
  const resp = await fetch(`/api/jobs/${currentJob}`, { method: "DELETE" }).catch(() => null);
  if (resp && !resp.ok && resp.status !== 409) $("status-detail").textContent = await errorMessage(resp);
});

// Deja la página como recién abierta: sin archivo, método por defecto y sin estado ni resultado.
$("restart").addEventListener("click", () => {
  form.reset();
  onFileChange();
  $("status").hidden = true;
  $("result").hidden = true;
  $("restart").hidden = true;
  for (const id of ["status-title", "status-detail", "result-title", "result-meta", "text", "json"]) $(id).textContent = "";
  for (const id of ["warnings", "fields", "lines"]) $(id).querySelectorAll("li, tr").forEach((el) => el.remove());
  $("preview").src = "about:blank";
  $("download").href = "#";
  lastResult = null;
  window.scrollTo({ top: 0, behavior: "smooth" });
});

// ---------------------------------------------------------------- resultado

function cell(value, numeric = false) {
  const td = document.createElement("td");
  if (value === null || value === undefined) {
    td.textContent = "null";
    td.className = "null";
  } else {
    td.textContent = value;
    if (numeric) td.className = "num";
  }
  return td;
}

function showResult(r, jobId) {
  lastResult = r;
  $("result").hidden = false;
  $("result-title").textContent = r.archivo;
  const filled = Object.values(r.campos).filter((v) => v !== null).length;
  $("result-meta").textContent =
    `${r.metodo_nombre} · ${filled}/${Object.keys(r.campos).length} campos · ${r.lineas.length} líneas · ${r.tiempo_s} s`;
  $("download").href = `/api/jobs/${jobId}/descarga`;
  $("preview").src = pdfUrl ? `${pdfUrl}#view=FitH` : "about:blank";

  $("warnings").replaceChildren(...r.avisos.map((a) => Object.assign(document.createElement("li"), { textContent: a })));

  $("fields").tBodies[0].replaceChildren(...Object.entries(r.campos).map(([k, v]) => {
    const tr = document.createElement("tr");
    const th = Object.assign(document.createElement("th"), { textContent: FIELD_LABELS[k] || k, title: k });
    tr.append(th, cell(v));
    return tr;
  }));

  const head = document.createElement("tr");
  head.append(...LINE_COLS.map(([, label]) => Object.assign(document.createElement("th"), { textContent: label })));
  $("lines").tHead.replaceChildren(head);
  $("lines").tBodies[0].replaceChildren(...(r.lineas.length ? r.lineas.map((l) => {
    const tr = document.createElement("tr");
    tr.append(...LINE_COLS.map(([k]) => cell(l[k], !["referencia", "descripcion"].includes(k))));
    return tr;
  }) : [Object.assign(document.createElement("tr"), { innerHTML: '<td colspan="7" class="null">Sin líneas detectadas</td>' })]));

  $("text").textContent = r.texto_leido;
  const { texto_leido, ...rest } = r;
  $("json").textContent = JSON.stringify(rest, null, 2);
}

// Copia el mismo JSON que se descarga (incluye texto_leido).
$("copy").addEventListener("click", async () => {
  if (!lastResult) return;
  const btn = $("copy");
  try {
    await navigator.clipboard.writeText(JSON.stringify(lastResult, null, 2));
    btn.textContent = "Copiado ✓";
  } catch {
    btn.textContent = "No se pudo copiar";
  }
  setTimeout(() => { btn.textContent = "Copiar JSON"; }, 1500);
});
