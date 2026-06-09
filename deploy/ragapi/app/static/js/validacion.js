/* validacion.js — capa de PRESENTACIÓN del estado de validación (FASE 6/10).
   NO implementa lógica de validación: cédula, OTP, SMS y la máquina de estados
   viven en procesar() (backend). Aquí sólo se mapea el estado a etiquetas y se
   pinta el panel de perfil. */
(function (global) {
  'use strict';
  const RealIA = global.RealIA || (global.RealIA = {});
  const U = RealIA.util;

  // Mapa estado_validacion (Redis) -> clave de estilo.
  function estadoKey(estado) {
    const e = String(estado || '').toLowerCase();
    if (e === 'validado') return 'validado';
    if (e === 'esperando_cedula' || e === 'esperando_telefono' || e === 'esperando_otp' || e === 'validando') return 'validando';
    return 'sin_validar';
  }

  function estadoLabel(estado) {
    const k = estadoKey(estado);
    return k === 'validado' ? 'Validado' : (k === 'validando' ? 'Validando' : 'Sin validar');
  }

  // Pinta el badge de Estado Validación del panel Datos Cliente.
  function pintarEstado(estado, labelExplicito) {
    const el = document.getElementById('perfil-estado');
    if (!el) return;
    const k = estadoKey(estado);
    el.dataset.estado = k;
    el.textContent = labelExplicito || estadoLabel(estado);
  }

  // Rellena el panel Datos Cliente (FASE 10) desde el endpoint /cliente o el poll.
  function renderPerfil(data) {
    if (!data) return;
    const set = function (id, val) {
      const el = document.getElementById(id);
      if (el) el.textContent = (val == null || val === '') ? 'N/D' : val;
    };
    if ('nombre' in data) set('perfil-nombre', data.nombre);
    if ('cod_persona' in data) set('perfil-cod', data.cod_persona);
    if ('telefono' in data) set('perfil-tel', data.telefono);
    if ('canal' in data) set('perfil-canal', (data.canal || '').toUpperCase());
    if ('estado_validacion' in data) pintarEstado(data.estado_validacion, data.estado_validacion_label);
  }

  RealIA.validacion = { estadoKey: estadoKey, estadoLabel: estadoLabel, pintarEstado: pintarEstado, renderPerfil: renderPerfil };
})(window);
