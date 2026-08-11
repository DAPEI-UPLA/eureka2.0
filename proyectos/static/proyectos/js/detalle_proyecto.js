// ============================================================
// ESTADO DE PLEGADO
// Los bloques se recargan solos vía HTMX (para evitar el F5), así que
// recordamos qué estaba abierto y lo volvemos a abrir tras cada swap.
// ============================================================
const objetivosCerrados = new Set();
const resultadosAbiertos = new Set();

function pintarObjetivo(id) {
    const grupo = document.getElementById("grupo-" + id);
    const icono = document.getElementById("icono-" + id);
    if (!grupo) return;
    const cerrado = objetivosCerrados.has(String(id));
    grupo.classList.toggle("d-none", cerrado);
    if (icono) icono.innerText = cerrado ? "▶" : "▼";
}

function pintarResultado(id) {
    const row = document.getElementById("actividades-row-" + id);
    const icono = document.getElementById("icono-res-" + id);
    if (!row) return;
    const abierto = resultadosAbiertos.has(String(id));
    row.classList.toggle("d-none", !abierto);
    if (icono) icono.innerText = abierto ? "▼" : "▶";
    if (abierto) cargarActividades(id);
}

// `revealed` sólo se evalúa al hacer scroll, así que pedimos la carga
// explícitamente la primera vez que se abre el desplegable.
function cargarActividades(id) {
    const tbody = document.getElementById("actividades-" + id);
    if (!tbody || tbody.dataset.cargado === "1" || !window.htmx) return;
    tbody.dataset.cargado = "1";
    window.htmx.trigger(tbody, "cargarActividades");
}

function toggleObjetivo(id) {
    const clave = String(id);
    if (objetivosCerrados.has(clave)) objetivosCerrados.delete(clave);
    else objetivosCerrados.add(clave);
    pintarObjetivo(id);
}

function toggleActividades(id) {
    const clave = String(id);
    if (resultadosAbiertos.has(clave)) resultadosAbiertos.delete(clave);
    else resultadosAbiertos.add(clave);
    pintarResultado(id);
}

function restaurarPlegados() {
    objetivosCerrados.forEach(pintarObjetivo);
    resultadosAbiertos.forEach(pintarResultado);
}

function togglePlanes(id) {
    const row = document.getElementById("planes-row-" + id);
    const icono = document.getElementById("planes-icon-" + id);
    if (!row) return;
    row.classList.toggle("d-none");
    const visible = !row.classList.contains("d-none");
    if (icono) icono.innerText = visible ? "▼" : "▶";

    if (visible) {
        const cell = document.getElementById("planes-cell-" + id);
        if (cell && cell.dataset.loaded !== "1" && window.htmx) {
            cell.dataset.loaded = "1";
            window.htmx.ajax("GET", cell.dataset.url, {
                target: "#planes-cell-" + id,
                swap: "innerHTML"
            });
        }
    }
}

window.toggleObjetivo = toggleObjetivo;
window.toggleActividades = toggleActividades;
window.togglePlanes = togglePlanes;

// Al crear/borrar una actividad dejamos visible su tabla para que el cambio
// se vea sin tener que desplegar nada a mano.
document.body.addEventListener("actividadActualizada", (e) => {
    const rid = e.detail && e.detail.resultado_id;
    if (!rid) return;
    resultadosAbiertos.add(String(rid));
    pintarResultado(rid);
});

// Tras cualquier recarga parcial devolvemos los bloques al estado en que
// estaban y damos el foco a la caja de texto recién insertada.
document.body.addEventListener("htmx:afterSettle", () => {
    restaurarPlegados();
    const campo = document.querySelector("[data-autofoco]");
    if (campo) {
        campo.removeAttribute("data-autofoco");
        campo.focus();
        if (typeof campo.setSelectionRange === "function") {
            const fin = campo.value.length;
            try { campo.setSelectionRange(fin, fin); } catch (e) {}
        }
        autoCrecer(campo);
    }
});

// ============================================================
// CAJAS DE DESCRIPCIÓN: crecen con el texto y Enter confirma
// ============================================================
function autoCrecer(el) {
    if (!el || el.tagName !== "TEXTAREA") return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight + 2, 260) + "px";
}

document.addEventListener("input", (e) => {
    if (e.target.classList && e.target.classList.contains("campo-descripcion")) {
        autoCrecer(e.target);
    }
});

document.addEventListener("keydown", (e) => {
    if (!e.target.classList || !e.target.classList.contains("campo-descripcion")) return;
    // Enter guarda (dispara el blur); Shift+Enter deja saltar de línea.
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        e.target.blur();
    }
});

// ============================================================
// AVISO "GUARDADO" Y REFRESCO MANUAL
// ============================================================
document.body.addEventListener("guardado", (e) => {
    const mensaje = (e.detail && e.detail.mensaje) || "Guardado";
    let caja = document.getElementById("proy-aviso-guardado");
    if (!caja) {
        caja = document.createElement("div");
        caja.id = "proy-aviso-guardado";
        caja.className = "proy-aviso";
        document.body.appendChild(caja);
    }
    caja.textContent = "✓ " + mensaje;
    caja.classList.add("visible");
    clearTimeout(caja._t);
    caja._t = setTimeout(() => caja.classList.remove("visible"), 2200);
});

function refrescarProyecto() {
    if (!window.htmx) return;
    window.htmx.trigger(document.body, "objetivosActualizados", {});
    window.htmx.trigger(document.body, "estructuraActualizada", {});
}
window.refrescarProyecto = refrescarProyecto;


// ============================================================
// SECCIONES PLEGABLES (Gráficos, Objetivos, Planes, Gastos)
// El estado se recuerda por proyecto en localStorage.
// ============================================================
function claveSeccion(id) {
    return "proy-sec:" + (window.location.pathname) + ":" + id;
}

function toggleSeccion(id) {
    const title = document.querySelector('.section-title[data-collapse="' + id + '"]');
    const target = document.getElementById(id);
    if (!title || !target) return;
    const colapsada = title.classList.toggle("seccion-colapsada");
    target.classList.toggle("d-none", colapsada);
    try { localStorage.setItem(claveSeccion(id), colapsada ? "1" : "0"); } catch (e) {}
    // Al abrir, re-disparamos la carga si la sección lo pide (los gráficos
    // deben re-renderizarse visibles para tomar su tamaño real).
    if (!colapsada) {
        const ev = target.getAttribute("data-reload-event");
        if (ev && window.htmx) window.htmx.trigger(target, ev);
    }
}
window.toggleSeccion = toggleSeccion;

(function restaurarSecciones() {
    document.querySelectorAll('.section-title[data-collapse]').forEach((title) => {
        const id = title.getAttribute("data-collapse");
        const target = document.getElementById(id);
        if (!target) return;
        let st = null;
        try { st = localStorage.getItem(claveSeccion(id)); } catch (e) {}
        if (st === null) st = title.getAttribute("data-default-collapsed") === "1" ? "1" : "0";
        const colapsada = st === "1";
        title.classList.toggle("seccion-colapsada", colapsada);
        target.classList.toggle("d-none", colapsada);
    });
    // Accesibilidad: Enter/Espacio sobre el encabezado también pliega.
    document.querySelectorAll('.section-title.seccion-toggle').forEach((title) => {
        title.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                toggleSeccion(title.getAttribute("data-collapse"));
            }
        });
    });
})();


// ============================================================
// BUSCADOR DENTRO DEL PROYECTO
// Indexa secciones, objetivos y resultados presentes en el DOM;
// al elegir, abre lo que esté plegado y hace scroll con resaltado.
// ============================================================
(function buscadorProyecto() {
    const input = document.getElementById("proy-buscar");
    const menu = document.getElementById("proy-buscar-menu");
    if (!input || !menu) return;

    function limpiar(txt) {
        return (txt || "").replace(/[▶▼▾]/g, "").replace(/\s+/g, " ").trim();
    }

    function indexar(q) {
        q = q.trim().toLowerCase();
        if (!q) return [];
        const out = [];
        document.querySelectorAll('.section-title[data-collapse]').forEach((t) => {
            const h = t.querySelector("h5");
            const label = h ? limpiar(h.innerText) : "";
            if (label.toLowerCase().includes(q)) out.push({ tipo: "Sección", texto: label, el: t });
        });
        document.querySelectorAll('#contenedor-objetivos .objetivo-grupo').forEach((g) => {
            const tit = g.querySelector(".objetivo-titulo");
            if (!tit) return;
            const txt = limpiar(tit.innerText);
            if (txt && txt.toLowerCase().includes(q)) out.push({ tipo: "Objetivo", texto: txt, el: g });
        });
        document.querySelectorAll('#contenedor-objetivos tr[id^="resultado-"]').forEach((r) => {
            const cell = r.querySelector("td");
            const txt = cell ? limpiar(cell.innerText) : "";
            if (txt && txt.toLowerCase().includes(q)) out.push({ tipo: "Resultado", texto: txt, el: r });
        });
        return out.slice(0, 12);
    }

    function esc(s) {
        const d = document.createElement("div");
        d.textContent = s;
        return d.innerHTML;
    }

    function pintar(items) {
        if (!items.length) {
            menu.innerHTML = '<div class="proy-buscar-vacio">Sin coincidencias</div>';
            menu.classList.remove("d-none");
            return;
        }
        menu.innerHTML = items
            .map((it) => '<div class="proy-buscar-item"><span class="tipo">' + it.tipo +
                '</span><span class="txt">' + esc(it.texto) + "</span></div>")
            .join("");
        menu.classList.remove("d-none");
        Array.from(menu.children).forEach((el, i) => {
            el.addEventListener("click", () => { irA(items[i]); cerrar(); });
        });
    }

    function cerrar() { menu.classList.add("d-none"); }

    function abrirSeccion(id) {
        const title = document.querySelector('.section-title[data-collapse="' + id + '"]');
        if (title && title.classList.contains("seccion-colapsada")) toggleSeccion(id);
    }

    function irA(item) {
        if (item.tipo === "Sección") {
            abrirSeccion(item.el.getAttribute("data-collapse"));
        } else {
            // Objetivos/resultados viven en la sección Objetivos.
            abrirSeccion("contenedor-objetivos");
            // Si el resultado está dentro de un objetivo plegado, lo abrimos.
            const grupo = item.el.closest ? item.el.closest(".objetivo-grupo") : null;
            if (grupo) {
                const cont = grupo.querySelector('[id^="grupo-"]');
                if (cont && cont.classList.contains("d-none") && window.toggleObjetivo) {
                    window.toggleObjetivo(cont.id.replace("grupo-", ""));
                }
            }
        }
        const target = item.el;
        setTimeout(() => {
            target.scrollIntoView({ behavior: "smooth", block: "center" });
            target.classList.remove("proy-resaltar");
            void target.offsetWidth;
            target.classList.add("proy-resaltar");
            setTimeout(() => target.classList.remove("proy-resaltar"), 2000);
        }, 140);
        if (item.tipo !== "Sección") input.value = item.texto;
    }

    let t;
    input.addEventListener("input", () => {
        clearTimeout(t);
        t = setTimeout(() => pintar(indexar(input.value)), 120);
    });
    input.addEventListener("focus", () => {
        if (input.value.trim()) pintar(indexar(input.value));
    });
    input.addEventListener("keydown", (e) => {
        if (e.key === "Escape") { cerrar(); input.blur(); }
        if (e.key === "Enter") {
            const items = indexar(input.value);
            if (items.length) { irA(items[0]); cerrar(); }
        }
    });
    document.addEventListener("click", (e) => {
        if (!e.target.closest(".proy-buscador")) cerrar();
    });
})();
