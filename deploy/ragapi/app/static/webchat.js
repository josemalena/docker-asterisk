const chat = document.getElementById('chat');
const messageInput = document.getElementById('message');
const sendButton = document.getElementById('send');

let modo = "normal";  
let cliente_id = null;
let ult_preg = null;
let intentosOtp = 0;
const MAX_INTENTOS_OTP = 3;
const server = "";
function getCurrentTime() {
  const now = new Date();
  return now.toLocaleTimeString('es-DO', { hour: '2-digit', minute: '2-digit' });
}

function esc(s){
  return String(s ?? '').replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
}

function addMessage(text, sender, id = null, replyToId = null) {
  const div = document.createElement('div');
  div.className = 'message ' + sender;
  if (id) div.dataset.id = id;

  let senderName = sender === 'user' ? 'Tú' : 'Real[IA]';
  let replyHtml = '';

  if (replyToId) {
    // Buscar el mensaje original
    const repliedMessage = document.querySelector(`.message[data-id='${replyToId}']`);
    if (repliedMessage) {
      const preview = repliedMessage.textContent.slice(0, 60) + (repliedMessage.textContent.length > 60 ? '...' : '');
      replyHtml = `<div style="border-left: 3px solid #ccc; padding-left: 5px; margin-bottom: 5px; font-size: 12px; color: #555;">Respuesta a: "${preview}"</div>`;
    } else {
      replyHtml = `<div style="border-left: 3px solid #ccc; padding-left: 5px; margin-bottom: 5px; font-size: 12px; color: #555;">Respuesta a mensaje desconocido (ID: ${replyToId})</div>`;
    }
    replyHtml = '';// eliminamos el "Respuesta a:""
  }

  div.innerHTML = `
    <div class="sender">${senderName}</div>
    ${replyHtml}
    ${text.replace(/\n/g, '<br>')}
    <span class="timestamp">${getCurrentTime()}</span>
  `;
  chat.appendChild(div);
  setTimeout(() => {
    chat.scrollTop = chat.scrollHeight;
  }, 50);
}

function addMenu(menu) {
  // Deshabilita botones de menús anteriores para que el usuario no vuelva atrás haciendo click viejo.
  document.querySelectorAll('.menu-card .menu-row').forEach(b => b.disabled = true);

  const card = document.createElement('div');
  card.className = 'menu-card';

  let html = '';
  if (menu.header) html += `<div class="menu-header">${esc(menu.header)}</div>`;
  if (menu.body)   html += `<div class="menu-body">${esc(menu.body).replace(/\n/g, '<br>')}</div>`;
  (menu.sections || []).forEach(sec => {
    if (sec.title) html += `<div class="menu-section-title">${esc(sec.title)}</div>`;
    (sec.rows || []).forEach(row => {
      const id = esc(row.id || '');
      const title = esc(row.title || '');
      html += `<button type="button" class="menu-row" data-id="${id}" data-title="${title}">${title}</button>`;
    });
  });
  if (menu.footer) html += `<div class="menu-footer">${esc(menu.footer)}</div>`;
  card.innerHTML = html;

  card.querySelectorAll('.menu-row').forEach(btn => {
    btn.addEventListener('click', () => seleccionarOpcionMenu(btn.dataset.id, btn.dataset.title));
  });

  chat.appendChild(card);
  setTimeout(() => { chat.scrollTop = chat.scrollHeight; }, 50);
}

async function seleccionarOpcionMenu(payloadId, titulo) {
  if (!payloadId) return;
  addMessage(titulo, 'user');
  showTypingIndicator();
  try {
    await fetch(server + '/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: titulo, payload: payloadId })
    });
  } catch (err) {
    removeTypingIndicator();
    addMessage("Error de conexión al servidor.", 'bot');
  }
}

function mostrarPensandoBienvenida() {
  const div = document.createElement('div');
  div.className = 'message bot typing';
  div.id = 'pensando';
  div.innerHTML = `
    <div class="sender">Real[IA]</div>
    Real[IA] está pensando<span id="dots">.</span>
  `;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;

  let dots = '.';
  const intervalId = setInterval(() => {
    dots = dots.length < 3 ? dots + '.' : '.';
    const dotsSpan = document.getElementById('dots');
    if (dotsSpan) dotsSpan.textContent = dots;
  }, 500);

  div.dataset.intervalId = intervalId;
}

function ocultarPensandoBienvenida() {
  const pensandoDiv = document.getElementById('pensando');
  if (pensandoDiv) {
    clearInterval(pensandoDiv.dataset.intervalId);
    pensandoDiv.remove();
  }
}

// Mensaje de bienvenida con espera simulada
window.addEventListener('load', () => {
  // Registrar el Service Worker  
  mostrarPensandoBienvenida();
  setTimeout(() => {
    ocultarPensandoBienvenida();
    addMessage("¡Hola! 👋 Bienvenido a Cooperativa Vega Real.\nSoy Real[IA], tu asistente virtual. ¿En qué puedo ayudarte hoy?", 'bot');
  }, 2000);
});

window.addEventListener('offline', () => {
  addMessage("Estás sin conexión. Algunas funciones pueden no estar disponibles.", 'bot');
});

window.addEventListener('online', () => {
  addMessage("¡Conexión restablecida!", 'bot');
});

function showTypingIndicator() {
  typingIndicator = document.createElement('div');
  typingIndicator.className = 'message bot typing';
  typingIndicator.innerHTML = `
    <div class="sender">Real[IA]</div>
    está escribiendo<span id="dots"></span>
  `;
  chat.appendChild(typingIndicator);
  chat.scrollTop = chat.scrollHeight;

  let dots = '';
  setInterval(() => {
    dots = dots.length < 3 ? dots + '.' : '';
    const dotsSpan = document.getElementById('dots');
    if (dotsSpan) dotsSpan.textContent = dots;
  }, 500);
}

function removeTypingIndicator() {
  if (typingIndicator) {
    typingIndicator.remove();
    typingIndicator = null;
  }
}

/////
sendButton.addEventListener('click', async () => {
  let text = messageInput.value.trim();
  if (!text) return;

  showTypingIndicator();  

  // Modo normal (pregunta normal)
  try {
    
    const response = await fetch(server + '/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        message: text
      })
    });

    const data = await response.json();
    removeTypingIndicator();
    if (data.error) {
      addMessage("Error: " + data.error, 'bot');
    }
    addMessage(text, 'user', data.message_id);
    messageInput.value = '';
  } catch (err) {
    removeTypingIndicator();
    addMessage("Error de conexión al servidor.", 'bot');
  }
});

/////

messageInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') {
    sendButton.click();
  }
});

// Polling cada 3 segundos para recibir nuevas respuestas
setInterval(async () => {
  try {
    const res = await fetch(server + '/webchat/mensajes');
    const data = await res.json();
    if (data.mensajes && data.mensajes.length > 0) {
      removeTypingIndicator();
      data.mensajes.forEach(jsonStr => {
        let msg;
        try { msg = JSON.parse(jsonStr); } catch { return; }
        if (msg && msg.type === 'menu' && msg.menu) {
          addMenu(msg.menu);
        } else {
          addMessage(msg.message, 'bot', null, msg.message_id);
        }
      });
    }
  } catch (err) {
    console.error("Error consultando nuevos mensajes:", err);
  }
}, 3000);