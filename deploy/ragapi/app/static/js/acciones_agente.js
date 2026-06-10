/* acciones_agente.js — panel de Acciones (FASE 8/9). Cada botón [data-accion]
   invoca su endpoint backend y refresca el modal. */
(function (global) {
  'use strict';
  const RealIA = global.RealIA || (global.RealIA = {});
  const U = RealIA.util;
  const C = RealIA.conversacion;

  function out(html, esError) {
    const el = document.getElementById('acciones-output');
    if (!el) return;
    el.hidden = false;
    el.className = 'acciones-output' + (esError ? ' text-danger' : '');
    el.innerHTML = html;
  }

  function base() {
    const id = C.convId();
    return id == null ? null : '/interacciones/conversacion/' + encodeURIComponent(id);
  }

  function setBusy(btn, busy) {
    if (!btn) return;
    btn.disabled = !!busy;
    btn.classList.toggle('disabled', !!busy);
  }

  // GET de datos del cliente (cuentas/préstamos/certificados/feria).
  function verDatos(url, titulo) {
    out('<div class="text-muted">Consultando ' + U.esc(titulo) + '…</div>');
    U.getJSON(url).then(function (res) {
      const d = res.data || {};
      if (!res.ok || !d.ok) {
        out('<strong>' + U.esc(titulo) + '</strong><br>' + U.esc(d.mensaje || d.error || 'No disponible.'), true);
        return;
      }
      const texto = d.texto || 'Sin información.';
      out('<strong>' + U.esc(titulo) + '</strong><br>' + U.esc(texto));
    }).catch(function () { out('Error de red consultando ' + U.esc(titulo) + '.', true); });
  }

  // POST que envía los datos del cliente (cuentas/préstamos/feria) directo a su canal.
  function enviarDatos(url, titulo) {
    if (!global.confirm('¿Enviar ' + titulo + ' directamente al cliente?')) return;
    out('<div class="text-muted">Enviando ' + U.esc(titulo) + ' al cliente…</div>');
    U.postJSON(url, {}).then(function (res) {
      const d = res.data || {};
      if (!res.ok || !d.ok) {
        out('<strong>' + U.esc(titulo) + '</strong><br>' + U.esc(d.mensaje || d.error || 'No se pudo enviar.'), true);
        return;
      }
      if (d.enviado) {
        out('<strong>' + U.esc(titulo) + ' enviado al cliente.</strong>');
        C.recargar();
      } else {
        out('<strong>' + U.esc(titulo) + '</strong><br>' + U.esc(d.mensaje || 'No había datos para enviar.'), true);
      }
    }).catch(function () { out('Error de red enviando ' + U.esc(titulo) + '.', true); });
  }

  function verPerfil(url) {
    U.getJSON(url).then(function (res) {
      const d = res.data || {};
      if (!res.ok || !d.ok) { out('No se pudo obtener el perfil.', true); return; }
      RealIA.validacion.renderPerfil(d);
      out('<strong>Perfil actualizado</strong><br>' +
        U.esc(d.nombre) + ' · Cod ' + U.esc(d.cod_persona) + ' · ' + U.esc(d.estado_validacion_label));
    }).catch(function () { out('Error de red obteniendo el perfil.', true); });
  }

  const handlers = {
    atender: function (b) {
      setBusy(b, true);
      U.postJSON(base() + '/atender', {}).then(function (res) {
        const d = res.data || {};
        if (res.ok && d.ok) {
          out('<strong>Atención iniciada</strong><br>Agente: ' + U.esc(d.agente || '') +
            (d.saludo_enviado ? '<br>Saludo enviado al cliente.' : '<br><span class="text-danger">Saludo no enviado (' + U.esc(d.saludo_error || '') + ').</span>'));
          C.recargar();
        } else { out('No se pudo iniciar la atención (' + U.esc(d.error || '') + ').', true); }
      }).catch(function () { out('Error de red al iniciar atención.', true); })
        .finally(function () { setBusy(b, false); });
    },
    identificar: function (b) {
      setBusy(b, true);
      U.postJSON(base() + '/identificar', {}).then(function (res) {
        const d = res.data || {};
        if (res.ok && d.ok) { out('<strong>Solicitud de cédula enviada</strong><br>Esperando la cédula del cliente…'); C.recargar(); }
        else { out('No se pudo solicitar la cédula (' + U.esc(d.error || '') + ').', true); }
      }).catch(function () { out('Error de red al solicitar la cédula.', true); })
        .finally(function () { setBusy(b, false); });
    },
    cliente: function () { verPerfil(base() + '/cliente'); },
    cuentas: function () { verDatos(base() + '/cuentas', 'Cuentas'); },
    prestamos: function () { verDatos(base() + '/prestamos', 'Préstamos'); },
    certificados: function () { verDatos(base() + '/certificados', 'Certificados'); },
    feria: function () { verDatos(base() + '/feria', 'Feria'); },
    'enviar-cuentas': function () { enviarDatos(base() + '/cuentas', 'Cuentas'); },
    'enviar-prestamos': function () { enviarDatos(base() + '/prestamos', 'Préstamos'); },
    'enviar-feria': function () { enviarDatos(base() + '/feria', 'Feria'); },
    nota: function () {
      const texto = global.prompt('Nota interna (no se envía al cliente):');
      if (!texto || !texto.trim()) return;
      U.postJSON(base() + '/nota', { texto: texto.trim() }).then(function (res) {
        if (res.ok && res.data && res.data.ok) { out('Nota interna guardada.'); C.recargar(); }
        else { out('No se pudo guardar la nota.', true); }
      }).catch(function () { out('Error de red al guardar la nota.', true); });
    },
    transferir: function () {
      const agente = global.prompt('Transferir a (usuario del agente):');
      if (!agente || !agente.trim()) return;
      U.postJSON(base() + '/transferir', { agente: agente.trim() }).then(function (res) {
        if (res.ok && res.data && res.data.ok) { out('Conversación transferida a ' + U.esc(res.data.asignado_a) + '.'); C.recargar(); }
        else { out('No se pudo transferir.', true); }
      }).catch(function () { out('Error de red al transferir.', true); });
    },
    cerrar: function (b) {
      if (!global.confirm('¿Cerrar el caso? El control volverá al bot.')) return;
      setBusy(b, true);
      U.postJSON(base() + '/cerrar', {}).then(function (res) {
        if (res.ok && res.data && res.data.ok) { out('Caso cerrado.'); C.recargar(); }
        else { out('No se pudo cerrar el caso.', true); }
      }).catch(function () { out('Error de red al cerrar el caso.', true); })
        .finally(function () { setBusy(b, false); });
    }
  };

  function init() {
    document.querySelectorAll('.acciones-body .accion').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (C.convId() == null) return;
        const accion = btn.getAttribute('data-accion');
        if (handlers[accion]) handlers[accion](btn);
      });
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})(window);
