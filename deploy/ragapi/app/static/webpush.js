  /// Nueva implementacion
  const promptDiv = document.getElementById("installPrompt");
  const promptText = document.getElementById("installText");
  const installBtn = document.getElementById("installBtn");

  const statusDiv = document.getElementById("status");
  const statusText = document.getElementById("statusText");
  const btn = document.getElementById("btnNotificaciones");
  
  let deferredPrompt = null;

  // Para Android / navegadores que soportan beforeinstallprompt
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    
    // Mostrar el botón de instalación
    promptText.innerText = "¿Deseas instalar esta app en tu pantalla de inicio?";
    installBtn.style.display = "inline-block";
    promptDiv.style.display = "block";
    
    // Opcional: Mostrar automáticamente después de un tiempo
    setTimeout(() => {
      if (deferredPrompt) {
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then((choiceResult) => {
          if (choiceResult.outcome === 'accepted') {
            console.log('Usuario aceptó la instalación');
          } else {
            console.log('Usuario rechazó la instalación');
          }
          deferredPrompt = null;
        });
      }
    }, 3000); // Mostrar después de 3 segundos
  });


function esIOS() {
  return /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
}

function esStandalone() {
  return window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone;
}

export async function verificarCompatibilidadPush() {
  if (esIOS() && !esStandalone()) {
    statusDiv.style.display = "block";
    statusText.innerText = "⚠️ Para habilitar notificaciones push agregame a la pantalla de inicio.";
    return;
  }

  if (!('serviceWorker' in navigator)) {
      statusText.innerText = "❌ Este navegador no soporta Service Workers.";
      statusDiv.style.display = "none";
    return;
  }
  if (!('PushManager' in window)) {
      statusText.innerText = "❌ Este navegador no soporta PushManager.";
      statusDiv.style.display = "none";
    return;
  }
  if (!('Notification' in window)) {
      statusText.innerText = "❌ Este navegador no soporta Notification API.";
      statusDiv.style.display = "none";
    return;
  } 
  // Intentar activar notificaciones automáticamente
  setTimeout(() => {
    btn.style.display = "inline-block"; 
    }, 3000);
}

  // Utilidad para convertir clave VAPID
function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/\-/g, "+").replace(/_/g, "/");
    const rawData = atob(base64);
    return Uint8Array.from([...rawData].map(c => c.charCodeAt(0)));
  }
  
async function activarNotificaciones(){
    try {
        const reg = await navigator.serviceWorker.register("/pwa/sw.js");
        statusText.innerText = "✅ SW Registrado.";
        //const readyReg = await navigator.serviceWorker.ready;
        statusText.innerText = "✅ Listo para solicitar notificaciones.";
        const permiso = await Notification.requestPermission();
        if (permiso === 'granted') {
            statusText.innerText = "✅ Permiso para notificaciones concedido.";
            try {
                // Obtener clave pública del backend
                const res = await fetch('/vapid_public_key');
                const { publicKey } = await res.json();
                const applicationServerKey = urlBase64ToUint8Array(publicKey);
                try {
                    const subscription = await reg.pushManager.subscribe({
                        userVisibleOnly: true,
                        applicationServerKey
                    });
                    statusText.innerText = `📦 Suscripción obtenida para ${session_id}`;    
                    // Enviar al backend
                    await fetch('/subscribe', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(subscription)
                    });    
                    statusText.innerText = "✅ Suscripción enviada al backend";
                    statusDiv.style.display = "none";
                } catch (err) {
                    console.error("❌ Error en suscripción Web Push:", err);
                    statusText.innerText ="❌ Error en suscripción Web Push: " + err.message;
                }
            } catch (err) {
                console.error("❌ Error en suscripción vapid_public_key:", err);
                statusText.innerText ="❌ Error en suscripción Web Push: " + err.message;
            }
        } else {
            statusText.innerText = "❌ Permiso denegado o cancelado.";
        }
    } catch (e) {
        statusText.innerText = "❌ Error registrando Service Worker: " + e.message;
    } 
}

window.addEventListener("focus", () => {
    fetch("/push?session_id=" + session_id + "&active=1");
  });
  
  window.addEventListener("blur", () => {
    fetch("/push?session_id=" + session_id + "&active=0");
  });
  

btn.addEventListener("click", activarNotificaciones);