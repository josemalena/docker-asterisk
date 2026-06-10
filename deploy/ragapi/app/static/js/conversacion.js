/* conversacion.js — controlador del modal de conversación (carga, render de chat,
   intents y adjuntos, paneles colapsables, compositor y estado de handoff). */
(function (global) {
  'use strict';
  const RealIA = global.RealIA || (global.RealIA = {});
  const U = RealIA.util;
  const V = RealIA.validacion;

  let convActual = null;
  let pollTimer = null;
  let modalInstance = null;
  let ultimaData = null;

  // ── DOM refs (existen tras incluir el modal en dashboard.html) ──
  function $(id) { return document.getElementById(id); }

  function getModal() {
    if (!modalInstance) {
      const el = $('modalConversacion');
      modalInstance = global.bootstrap.Modal.getOrCreateInstance(el);
      el.addEventListener('hidden.bs.modal', detener);
    }
    return modalInstance;
  }

  // ── Apertura / cierre ──────────────────────────────────────────────
  function abrir(conversacionId) {
    convActual = conversacionId;
    ultimaData = null;
    $('panel-chat').innerHTML = '<p class="panel-empty">Cargando…</p>';
    $('panel-intents').innerHTML = '';
    $('panel-adjuntos').innerHTML = '';
    $('conv-title-text').textContent = 'Conversación #' + conversacionId;
    $('intents-count').textContent = '(0)';
    $('adjuntos-count').textContent = '(0)';
    $('acciones-output').hidden = true;
    $('acciones-output').innerHTML = '';
    V.renderPerfil({ nombre: 'N/D', cod_persona: 'N/D', telefono: 'N/D', canal: 'N/D', estado_validacion: 'sin_validar' });
    getModal().show();
    cargar(true);
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(function () { cargar(false); }, 4000);
  }

  function detener() {
    convActual = null;
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  // ── Carga / poll ───────────────────────────────────────────────────
  function cargar(inicial) {
    if (convActual == null) return;
    U.getJSON('/interacciones/conversacion/' + encodeURIComponent(convActual))
      .then(function (res) {
        if (!res.ok) throw new Error((res.data && res.data.error) || 'error');
        render(res.data, inicial);
      })
      .catch(function (e) {
        if (inicial) $('panel-chat').innerHTML = '<p class="panel-empty text-danger">Error: ' + U.esc(e.message || e) + '</p>';
      });
  }

  function render(data, inicial) {
    ultimaData = data;
    const tel = data.telefono ? ' · ' + U.esc(data.telefono) : '';
    $('conv-title-text').innerHTML = U.esc((data.canal || '?').toUpperCase()) + ' · ' +
      U.esc(U.lblCliente(data.cod_persona)) + tel + ' · #' + U.esc(data.conversacion_id);
    
    renderChat(data, inicial);
    renderIntents(data.mensajes || []);
    renderAdjuntos(data.adjuntos || []);

    // Perfil (FASE 10) + handoff (FASE 5/7)
    V.renderPerfil({
      cod_persona: (data.cod_persona && String(data.cod_persona) !== '0') ? data.cod_persona : 'N/D',
      telefono: data.telefono || 'N/D',
      canal: data.canal,
      estado_validacion: data.estado_validacion,
      estado_validacion_label: data.estado_validacion_label
    });
    if (data.estado_validacion === 'validado') {
      const btnIdentificar = $('btn-identificar');
      btnIdentificar.disabled = true;
        U.getJSON(
            '/interacciones/conversacion/' +
            encodeURIComponent(convActual) +
            '/cliente'
        ).then(function(res){
            if (
                res.ok &&
                res.data &&
                res.data.ok
            ) {
                V.renderPerfil(res.data);
            }
        });
    }
    aplicarHandoff(data.atendido_por);
  }

  function renderChat(data, inicial) {
    const $chat = $('panel-chat');
    const msgs = data.mensajes || [];
    const pegado = inicial || ($chat.scrollHeight - $chat.scrollTop - $chat.clientHeight) < 60;

    $chat.innerHTML = msgs.map(function (m) {
      const dir = String(m.direccion || '').toUpperCase();
      if (dir === 'NOTE') {
        return '<div class="row center"><div class="message note"><i class="bi bi-journal-text me-1"></i>' +
          U.esc(m.contenido) + '</div><div class="ts">Nota interna · ' +
          U.esc(m.enviado_por || '') + ' · ' + U.fmtTs(m.fecha) + '</div></div>';
      }
      const entrante = dir === 'IN';
      const ep = (m.enviado_por && m.enviado_por !== 'sistema') ? m.enviado_por : '';
      const autor = entrante ? (ep || 'Usuario') : (ep || 'Bot/Agente');
      let cuerpo = U.esc(m.contenido);
      if (m.adjunto && m.adjunto.nombre) {
        const url = m.adjunto.url ? U.esc(m.adjunto.url) : '#';
        cuerpo += '<div class="msg-file"><i class="bi bi-paperclip"></i>' +
          '<a href="' + url + '" target="_blank" rel="noopener">' + U.esc(m.adjunto.nombre) + '</a></div>';
      }
      return '<div class="row ' + (entrante ? '' : 'right') + '">' +
        '<div class="message ' + (entrante ? 'bot' : 'user') + '">' + cuerpo + '</div>' +
        '<div class="ts">' + U.esc(autor) + ' · ' + U.fmtTs(m.fecha) + '</div></div>';
    }).join('') || '<p class="panel-empty">Sin mensajes.</p>';

    if (pegado) requestAnimationFrame(function () { $chat.scrollTop = $chat.scrollHeight; });
  }

  function renderIntents(msgs) {
    let n = 0;
    const html = msgs.map(function (m) {
      const I = m.intencion;
      if (I == null) return '';
      n++;
      const isObj = I && typeof I === 'object';
      const intent = (isObj && I.intent) || (typeof I === 'string' ? I : '—');
      const tipo = (isObj ? (I.type || '') : '').toLowerCase();
      const ents = isObj && Array.isArray(I.entity) ? I.entity : (isObj && I.entity ? [I.entity] : []);
      const entHTML = ents.length ? '<div class="ents">' + ents.map(function (e) {
        if (e && typeof e === 'object') {
          const tag = [e.tipo, e.subtipo, e.valor].filter(Boolean).join('/');
          return '<span class="ent">' + U.esc(tag || JSON.stringify(e)) + '</span>';
        }
        return '<span class="ent">' + U.esc(e) + '</span>';
      }).join('') + '</div>' : '';
      const raw = JSON.stringify(I, null, 2);
      const rawHTML = raw ? '<details class="raw"><summary>Ver data raw</summary><pre>' + U.esc(raw) + '</pre></details>' : '';
      const src = (m.intent_source || (isObj ? I.intent_source : '') || '').toLowerCase();
      const srcHTML = src ? '<span class="src ' + U.esc(src.replace(/[^a-z]/g, '')) + '">' + U.esc(src) + '</span>' : '';
      return '<div class="turn"><div class="head">' +
        '<span class="intent ' + U.esc(tipo) + '">' + U.esc(intent) + (tipo ? ' · ' + U.esc(tipo) : '') + '</span>' + srcHTML +
        '<span class="ts">' + U.fmtTs(m.fecha) + '</span></div>' +
        '<div class="pregunta">"' + U.esc(m.contenido) + '"</div>' + entHTML + rawHTML + '</div>';
    }).join('');
    $('panel-intents').innerHTML = html || '<div class="turn empty">Sin intents.</div>';
    $('intents-count').textContent = '(' + n + ')';
  }

  function renderAdjuntos(adjuntos) {
    $('adjuntos-count').textContent = '(' + adjuntos.length + ')';
    if (!adjuntos.length) { $('panel-adjuntos').innerHTML = '<div class="panel-empty">Sin adjuntos.</div>'; return; }
    $('panel-adjuntos').innerHTML = adjuntos.map(function (a) {
      const size = U.fmtSize(a.size);
      const nombre = U.esc(a.nombre || 'archivo');
      const inner = a.url
        ? '<a class="nombre" href="' + U.esc(a.url) + '" target="_blank" rel="noopener">' + nombre + '</a>'
        : '<span class="nombre">' + nombre + '</span>';
      return '<div class="adjunto"><i class="bi bi-file-earmark"></i>' + inner +
        (size ? '<span class="size">' + size + '</span>' : '') + '</div>';
    }).join('');
  }

  // ── Handoff: habilita/inhabilita el compositor (FASE 5) ────────────
  function aplicarHandoff(atendido) {
    const humano = atendido === 'humano';
    const t = $('composer-text'), s = $('composer-send'), a = $('composer-attach');
    if (t) { t.disabled = !humano; t.placeholder = humano ? 'Escribe un mensaje…' : 'Inicia la atención para escribir…'; }
    if (s) s.disabled = !humano;
    if (a) a.disabled = !humano;
    const btnIdentificar = $('btn-identificar');

    if (btnIdentificar) {
        btnIdentificar.disabled = !humano;
    }

    const badge = $('conv-handoff-badge');
    if (badge) {
      badge.hidden = false;
      badge.className = 'badge rounded-pill ' + (humano ? 'humano' : 'bot');
      badge.textContent = humano ? 'Atención humana' : 'Atendido por bot';
    }
    const btnAtender = $('btn-atender');
    if (btnAtender) {
      btnAtender.disabled = humano;
      btnAtender.innerHTML = humano
        ? '<i class="bi bi-headset me-1"></i>Atención iniciada'
        : '<i class="bi bi-headset me-1"></i>Iniciar atención';
    }
  }

  // ── Compositor ─────────────────────────────────────────────────────
  function enviarMensaje() {
    const t = $('composer-text'), s = $('composer-send'), hint = $('composer-hint');
    const texto = (t.value || '').trim();
    if (!texto || convActual == null) return;
    s.disabled = true; hint.hidden = true;
    U.postJSON('/interacciones/conversacion/' + encodeURIComponent(convActual) + '/enviar', { texto: texto })
      .then(function (res) {
        if (res.ok && res.data && res.data.ok) {
          t.value = ''; t.style.height = 'auto';
          cargar(false);
        } else {
          const err = (res.data && res.data.error) || 'error';
          hint.textContent = err === 'sin_telefono'
            ? 'No hay teléfono asociado para enviar por WhatsApp.'
            : 'No se pudo enviar (' + U.esc(err) + ').';
          hint.hidden = false;
        }
      })
      .catch(function () { hint.textContent = 'Error de red al enviar.'; hint.hidden = false; })
      .finally(function () { s.disabled = false; });
  }

  // ── Paneles colapsables (FASE 4) ───────────────────────────────────
  function toggleColapsable(btn) {
    const body = $(btn.getAttribute('data-target'));
    if (!body) return;
    const abierto = btn.getAttribute('aria-expanded') === 'true';
    btn.setAttribute('aria-expanded', String(!abierto));
    btn.classList.toggle('collapsed', abierto);
    body.hidden = abierto;
    const icon = btn.querySelector('.toggle-icon');
    if (icon) { icon.classList.toggle('bi-chevron-right', abierto); icon.classList.toggle('bi-chevron-down', !abierto); }
  }

  // ── Wiring ─────────────────────────────────────────────────────────
  function init() {
    const t = $('composer-text');
    if (t) {
      t.addEventListener('input', function () { t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight, 120) + 'px'; });
      t.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviarMensaje(); }
      });
    }
    const s = $('composer-send');
    if (s) s.addEventListener('click', enviarMensaje);

    const a = $('composer-attach');
    if (a) a.addEventListener('click', function () {
      const hint = $('composer-hint');
      hint.textContent = 'El envío de adjuntos no está habilitado en los canales actuales (sólo texto).';
      hint.hidden = false;
    });

    document.querySelectorAll('.panel-toggle').forEach(function (btn) {
      btn.addEventListener('click', function () { toggleColapsable(btn); });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else { init(); }

  // API pública para dashboard.js y acciones_agente.js
  RealIA.conversacion = {
    abrir: abrir,
    recargar: function () { cargar(false); },
    convId: function () { return convActual; },
    data: function () { return ultimaData; }
  };
})(window);
