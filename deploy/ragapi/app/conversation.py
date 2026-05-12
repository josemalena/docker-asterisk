import redis
import time
import json
from typing import List, Dict, Optional
import logging
import uuid
from datetime import datetime
from functools import wraps

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def handle_redis_errors(func):
    """Decorador para manejar errores de Redis"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except redis.RedisError as e:
            logger.error(f"Error de Redis en {func.__name__}: {str(e)}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Error al procesar JSON en {func.__name__}: {str(e)}")
            raise
    return wrapper

class ConversationManager:
    def __init__(
        self,
        session_id: str,
        redis_host: str = 'redis',
        redis_password: str = 'sOmE_sEcUrE_pAsS',
        redis_port: int = 6379,
        max_history_length: int = 20,
        encoding: str = 'utf-8'
    ):
        """
        Gestor de conversaciones con Redis
        
        Args:
            session_id: Identificador único de la conversación
            redis_host: Host de Redis
            redis_password: Contraseña de Redis
            redis_port: Puerto de Redis
            max_history_length: Máximo número de mensajes a conservar
            encoding: Codificación para los mensajes
        """
        self.session_id = session_id
        self.max_history_length = max_history_length
        self.encoding = encoding
        
        # Conexión segura a Redis con manejo de errores
        try:
            self.redis = redis.Redis(
                host=redis_host,
                port=redis_port,
                password=redis_password,
                decode_responses=False,
                encoding=encoding,
                socket_timeout=5,
                socket_connect_timeout=5,
                health_check_interval=30
            )
            # Test de conexión
            self.redis.ping()
        except redis.RedisError as e:
            logger.error(f"No se pudo conectar a Redis: {str(e)}")
            raise

    @property
    def _key(self) -> str:
        """Genera la clave Redis para esta conversación"""
        return f"chat:{self.session_id}"

    @handle_redis_errors
    def add_message(self, role: str, content: str) -> None:
        """
        Añade un mensaje al historial
        
        Args:
            role: 'usuario' o 'asistente'
            content: Contenido del mensaje
        """
        if role not in ('usuario', 'asistente'):
            raise ValueError("El rol debe ser 'usuario' o 'asistente'")
            
        message = {"role": role, "content": content, "timestamp": int(time.time())}
        self._append_to_history(message)
        
        # Mantener solo los últimos N mensajes
        self.redis.ltrim(self._key, -self.max_history_length, -1)

    @handle_redis_errors
    def _append_to_history(self, msg: Dict) -> None:
        """Guarda un mensaje en Redis"""
        self.redis.rpush(self._key, json.dumps(msg, ensure_ascii=False))

    @handle_redis_errors
    def get_conversation_history(self) -> List[Dict]:
        """Obtiene todo el historial de la conversación"""
        messages = self.redis.lrange(self._key, 0, -1)
        return [json.loads(m) for m in messages]
    
    def get_prompt(self):
        history = [json.loads(m) for m in self.redis.lrange(self._key(), 0, -1)]
        return "\n".join([f"{m['role'].capitalize()}: {m['content']}" for m in history]) + "\nAsistente:"

    @handle_redis_errors
    def get_formatted_prompt(self, system_prompt: Optional[str] = None) -> str:
        """
        Genera un prompt formateado para el modelo
        
        Args:
            system_prompt: Mensaje inicial del sistema (opcional)
        
        Returns:
            str: Prompt formateado
        """
        history = self.get_conversation_history()
        prompt_parts = []
        
        if system_prompt:
            prompt_parts.append(f"Sistema: {system_prompt}")
            
        for msg in history:
            prompt_parts.append(f"{msg['role'].capitalize()}: {msg['content']}")
            
        prompt_parts.append("Asistente:")
        return "\n".join(prompt_parts)

    @handle_redis_errors
    def get_last_messages(self, n: int = 3) -> List[Dict]:
        """Obtiene los últimos N mensajes"""
        messages = self.redis.lrange(self._key, -n, -1)
        return [json.loads(m) for m in messages]

    @handle_redis_errors
    def reset(self) -> None:
        """Borra todo el historial de la conversación"""
        self.redis.delete(self._key)

    @handle_redis_errors
    def get_ttl(self) -> int:
        """Obtiene el TTL restante de la clave en Redis"""
        return self.redis.ttl(self._key)

    @handle_redis_errors
    def set_expiration(self, seconds: int) -> bool:
        """Establece un tiempo de expiración para la conversación"""
        return self.redis.expire(self._key, seconds)

    # Métodos de conveniencia
    def add_user_message(self, message: str) -> None:
        """Añade un mensaje del usuario"""
        self.add_message('usuario', message)

    def add_assistant_message(self, message: str) -> None:
        """Añade un mensaje del asistente"""
        self.add_message('asistente', message)

    def set_variable(self, clave, campo, valor, expira=600):
        """Guarda un valor en Redis como hash por clave"""
        self.redis.hset(clave, campo, valor)
        self.redis.expire(clave, expira)

    def get_variable(self, clave, campo):
        """Recupera un valor de Redis"""
        return self.redis.hget(clave, campo)

    def del_variable(self, clave, campo):
        """Elimina un campo de una clave"""
        self.redis.hdel(clave, campo)

    @property
    def message_count(self) -> int:
        """Número de mensajes en la conversación"""
        return self.redis.llen(self._key)
    
    def add_web_message(self, session_id, message_id, message):
        mensaje_json = json.dumps({"message_id": message_id, "message": message})
        print(f"add_message({session_id}, {message_id},{message})")
        self.redis.rpush(f"mensajes:{session_id}", mensaje_json)
        #self.redis.rpush(f"mensajes:{session_id}", {"message_id": message_id, "message": message})

    def get_web_messages(self, session_id):
        key = f"mensajes:{session_id}"
        print(f"get_messages({session_id})")
        mensajes = self.redis.lrange(key, 0, -1)
        self.redis.delete(key)
        return [m.decode() for m in mensajes]

    def getRedis(self):
        return self.redis