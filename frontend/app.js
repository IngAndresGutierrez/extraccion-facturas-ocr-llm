// Envía el PDF a POST /api/extract, consulta GET /api/jobs/{id} hasta que termina y muestra el JSON.
const $ = (id) => document.getElementById(id);
const form = $("form"), fileInput = $("file"), drop = $("drop");
const POLL_MS = 1000;

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

// ---------------------------------------------------------------- selección de archivo

function setFile(file) {
  const dt = new DataTransfer();
  dt.items.add(file);
  fileInput.files = dt.files;
  showFileName();
}

function showFileName() {
  const f = fileInput.files[0];
  $("drop-text").textContent = f ? `${f.name} · ${(f.size / 1024).toFixed(0)} KB` : "Arrastra un PDF aquí o elige un archivo";
  drop.classList.toggle("has-file", Boolean(f));
}

fileInput.addEventListener("change", showFileName);
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.classList.remove("over");
  if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]);
});

// ---------------------------------------------------------------- estado

function setStatus(kind, title, detail = "") {
  const s = $("status");
  s.hidden = false;
  s.className = `card status ${kind}`;
  $("status-title").textContent = title;
  $("status-detail").textContent = detail;
}

async function errorMessage(resp) {
  try {
    const body = await resp.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((d) => `${d.loc.at(-1)}: ${d.msg}`).join("; ");
  } catch { /* respuesta sin JSON */ }
  return `El servidor respondió ${resp.status} ${resp.statusText}.`;
}

// ---------------------------------------------------------------- envío y seguimiento

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = fileInput.files[0];
  if (!file) return setStatus("error", "Falta el archivo", "Elige un PDF antes de extraer.");

  $("result").hidden = true;
  $("submit").disabled = true;
  setStatus("", "Subiendo el PDF…");

  const data = new FormData();
  data.append("file", file);
  data.append("method", form.method.value);

  try {
    const resp = await fetch("/api/extract", { method: "POST", body: data });
    if (!resp.ok) throw new Error(await errorMessage(resp));
    const { job_id } = await resp.json();
    await follow(job_id);
  } catch (err) {
    setStatus("error", "No se pudo procesar el PDF", err.message === "Failed to fetch"
      ? "No hay conexión con el servidor. ¿Está en marcha?" : err.message);
  } finally {
    $("submit").disabled = false;
  }
});

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
    if (job.estado === "error") {
      setStatus("error", "No se pudo extraer", job.mensaje);
      return;
    }
    setStatus("", job.estado === "en_cola" ? "En cola" : "Procesando…", `${job.etapa || ""}${elapsed}`);
    await new Promise((r) => setTimeout(r, POLL_MS));
  }
}

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
  $("result").hidden = false;
  $("result-title").textContent = r.archivo;
  const filled = Object.values(r.campos).filter((v) => v !== null).length;
  $("result-meta").textContent =
    `${r.metodo_nombre} · ${filled}/${Object.keys(r.campos).length} campos · ${r.lineas.length} líneas · ${r.tiempo_s} s`;
  $("download").href = `/api/jobs/${jobId}/descarga`;

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
