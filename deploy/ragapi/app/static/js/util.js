/* util.js — utilidades compartidas del panel de administración Real[IA]. */
(function (global) {
  'use strict';

  const RealIA = global.RealIA || (global.RealIA = {});

  // Escapa HTML para insertar texto de forma segura.
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // Convierte timestamp UTC ('YYYY-MM-DD HH:MM:SS' o ISO) a 'DD/MM/YYYY hh:mm:ss AM/PM' AST (GMT-4).
  function fmtTs(ts) {
    if (!ts) return '';
    const d = new Date(String(ts).replace(' ', 'T') + 'Z');
    if (isNaN(d)) return ts;
    const a = new Date(d.getTime() - 4 * 3600 * 1000);
    const pad = function (n) { return String(n).padStart(2, '0'); };
    let h = a.getUTCHours();
    const ampm = h >= 12 ? 'PM' : 'AM';
    h = h % 12 || 12;
    return pad(a.getUTCDate()) + '/' + pad(a.getUTCMonth() + 1) + '/' + a.getUTCFullYear() +
      ' ' + pad(h) + ':' + pad(a.getUTCMinutes()) + ':' + pad(a.getUTCSeconds()) + ' ' + ampm;
  }

  // Etiqueta del cliente: 'Cliente N/D' o 'Cliente <cod>'.
  function lblCliente(v) {
    return (v == null || v === '' || v === '0' || v === 0) ? 'Cliente N/D' : 'Cliente ' + v;
  }

  // Tamaño legible de archivo.
  function fmtSize(bytes) {
    const n = Number(bytes);
    if (!n || isNaN(n)) return '';
    if (n < 1024) return n + ' B';
    if (n < 1048576) return (n / 1024).toFixed(1) + ' KB';
    return (n / 1048576).toFixed(1) + ' MB';
  }

  // GET JSON con manejo uniforme de errores.
  function getJSON(url) {
    return fetch(url, { headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, status: r.status, data: j }; }); });
  }

  // POST JSON con manejo uniforme de errores.
  function postJSON(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, status: r.status, data: j }; }); });
  }

  RealIA.util = { esc: esc, fmtTs: fmtTs, lblCliente: lblCliente, fmtSize: fmtSize, getJSON: getJSON, postJSON: postJSON };
})(window);
