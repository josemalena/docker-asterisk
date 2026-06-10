#rag_db.py: Manejo de la base de datos y Redis para la aplicación RAG API.
import oracledb
import sqlite3
import redis

import os
import time
import logging
import sys
import locale
import json
import ast
import traceback
import xml.etree.ElementTree as ET
import re

from typing import List, Dict, Optional
from datetime import datetime
from functools import wraps

DBTYPE = os.getenv("DBTYPE")
DBSERVER = os.getenv(DBTYPE + "_DBSERVER")
DBNAME = os.getenv(DBTYPE + "_DBNAME")
DBPORT = os.getenv(DBTYPE + "_DBPORT")
DBUSER = os.getenv(DBTYPE + "_DBUSER")
DBPASSWORD = os.getenv(DBTYPE + "_DBPASSWORD")
DBCONNSTR = DBSERVER + ":" + DBPORT + "/" + DBNAME
REDIS_DBSERVER = os.getenv("REDIS_DBSERVER")
REDIS_DBPASSWORD = os.getenv("REDIS_DBPASSWORD")
CHATBOT_DB = os.getenv("SQLITE_DBNAME")
DBBIN = "/opt/instantclient_19_26"

locale.setlocale(locale.LC_ALL, 'es_DO.UTF-8')
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
logging.basicConfig(
    level = logging.INFO,
    format='[%(asctime)s] REALIA: (%(levelname)s) %(message)s',
    stream=sys.stdout,
    datefmt='%Y-%m-%d %H:%M:%S' 
)
def writetolog(str):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open('/proc/1/fd/1', 'w') as f:
        f.write(f"[{now}] REALIA: {str}\n")
        f.flush()

def loge(texto, nivel=1):
    str = f"({nivel}) {texto}"
    #logging.error(str)
    writetolog(str)

def logg(texto, nivel=1):
    str = f"({nivel}) {texto}"
    #logging.info(str)
    writetolog(str)

def logx(e):
    stacktrace = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
    writetolog(f"Ha ocurrido una excepción:\n{stacktrace}")

def disable_log():
    logging.disable = logging.INFO

def enable_log():
    logging.disable = None

def handle_redis_errors(func):
    """Decorador para manejar errores de Redis"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except redis.RedisError as e:
            loge(f"Error de Redis en {func.__name__}: {str(e)}")
            raise
        except json.JSONDecodeError as e:
            loge(f"Error al procesar JSON en {func.__name__}: {str(e)}")
            raise
    return wrapper

class ConversationManager:
    def __init__(
        self,
        session_id: str,
        redis_host: str = REDIS_DBSERVER,
        redis_password: str = REDIS_DBPASSWORD,
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
        if session_id == "0":
            logg(f"Inicializando DB {redis_host}:{redis_port}")
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
            if session_id == "0":
                logg(f"DB {redis_host}:{redis_port} inicializada")
        except redis.RedisError as e:
            loge(f"No se pudo conectar a Redis: {str(e)}")
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
    
    def set_subscription(self, session_id, sub):
        self.set_variable(f"push:{session_id}", "subscription", json.dumps(sub))

    def get_subscription(self, session_id):
        return self.get_variable(f"push:{session_id}", "subscription")

    def add_web_message(self, session_id, message_id, message):
        mensaje_json = json.dumps({"message_id": message_id, "message": message})
        self.redis.rpush(f"mensajes:{session_id}", mensaje_json)

    def get_web_messages(self, session_id):
        key = f"mensajes:{session_id}"
        mensajes = self.redis.lrange(key, 0, -1)
        self.redis.delete(key)
        return [m.decode() for m in mensajes]

    def getRedis(self):
        return self.redis

redisdb = ConversationManager("0")
# Crear la base de datos y la tabla si no existen
def crear_bd():
    conn = sqlite3.connect(CHATBOT_DB)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS interacciones_chatbot (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        session_id TEXT NOT NULL,
        cod_persona TEXT NULL,
        canal TEXT NOT NULL,
        pregunta TEXT NOT NULL,
        intencion TEXT,
        respuesta TEXT NOT NULL,
        intent_source TEXT,
        detalle TEXT
    )
    ''')
    # Migración: agrega la columna si la tabla ya existía sin ella.
    cursor.execute("PRAGMA table_info(interacciones_chatbot)")
    cols = {row[1] for row in cursor.fetchall()}
    if 'intent_source' not in cols:
        cursor.execute("ALTER TABLE interacciones_chatbot ADD COLUMN intent_source TEXT")
        logg("crear_db: columna 'intent_source' añadida a interacciones_chatbot")
    if 'detalle' not in cols:
        cursor.execute("ALTER TABLE interacciones_chatbot ADD COLUMN detalle TEXT")
        logg("crear_db: columna 'detalle' añadida a interacciones_chatbot")

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS conversaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        session_id TEXT NOT NULL,
        canal TEXT NOT NULL,
        canal_origen TEXT NOT NULL,

        cod_persona TEXT,
        telefono TEXT,

        estado TEXT DEFAULT 'ABIERTA',

        asignado_a TEXT,
        prioridad TEXT DEFAULT 'NORMAL',

        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        fecha_ultimo_mensaje TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        fecha_cierre TIMESTAMP
    )''')

    cursor.execute("PRAGMA table_info(conversaciones)")
    cols_conversaciones = {row[1] for row in cursor.fetchall()}
    if 'canal' not in cols_conversaciones:
        cursor.execute("ALTER TABLE conversaciones ADD COLUMN canal TEXT")
        if 'canal_origen' in cols_conversaciones:
            cursor.execute("UPDATE conversaciones SET canal = canal_origen WHERE canal IS NULL")
        logg("crear_db: columna 'canal' añadida a conversaciones")
    if 'canal_origen' not in cols_conversaciones:
        cursor.execute("ALTER TABLE conversaciones ADD COLUMN canal_origen TEXT")
        if 'canal' in cols_conversaciones:
            cursor.execute("UPDATE conversaciones SET canal_origen = canal WHERE canal_origen IS NULL")
        logg("crear_db: columna 'canal_origen' añadida a conversaciones")
    # Atención humana (handoff): quién atiende la conversación (bot|humano) y cuándo
    # se asignó. Se agregan sólo si no existen para no afectar datos actuales.
    if 'atendido_por' not in cols_conversaciones:
        cursor.execute("ALTER TABLE conversaciones ADD COLUMN atendido_por TEXT")
        logg("crear_db: columna 'atendido_por' añadida a conversaciones")
    if 'fecha_asignacion' not in cols_conversaciones:
        cursor.execute("ALTER TABLE conversaciones ADD COLUMN fecha_asignacion TIMESTAMP")
        logg("crear_db: columna 'fecha_asignacion' añadida a conversaciones")

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS mensajes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        conversacion_id INTEGER NOT NULL,

        direccion TEXT NOT NULL,

        canal TEXT NOT NULL,

        message_id TEXT,
        provider_message_id TEXT,

        contenido TEXT,

        tiene_archivo INTEGER DEFAULT 0,

        archivo_nombre TEXT,
        archivo_tipo TEXT,
        archivo_url TEXT,
        archivo_size INTEGER,

        template_id TEXT,

        metadata TEXT,

        fecha_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY (conversacion_id)
            REFERENCES conversaciones(id)
    )''')

    cursor.execute("PRAGMA table_info(mensajes)")
    cols = {row[1] for row in cursor.fetchall()}
    if 'enviado_por' not in cols:
        cursor.execute("ALTER TABLE mensajes ADD COLUMN enviado_por TEXT")
        logg("crear_db: columna 'enviado_por' añadida a mensajes")

    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_msg_conv ON mensajes(conversacion_id)''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_msg_fecha ON mensajes(fecha_hora)''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_msg_template ON mensajes(template_id)''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_msg_provider ON mensajes(provider_message_id)''')
    conn.commit()
    conn.close()
    logg(f"crear_db: Base de datos ChatBot lista '{CHATBOT_DB}'")

logg(f"========================================================")
logg(f"Inicializando...")
logg(f"Usando Cliente {DBBIN}")
oracledb.init_oracle_client(lib_dir=DBBIN)
logg(f"Cliente {DBTYPE} configurado")
logg(f"Iniciando sesión de BD {DBTYPE}")
connection = oracledb.connect(user=DBUSER, password=DBPASSWORD, dsn=DBCONNSTR)
logg(f"BD {DBTYPE} conectada")

crear_bd()
logg(f"Iniciando webservice...")
AGENCIAS = """ 
    a.cod_agencia AS id_agencia
                        ),
                    XMLFOREST(
                            'Sucursal: ' || INITCAP(DECODE(a.ES_CENTRAL, 'S', 'CENTRAL', a.DESCRIPCION)) || 
                            CHR(10) || 'Ubicación: ' || a.DETALLE_DIR || ', ' || INITCAP(pu.DESCRIPCION 
                            || ', Municipo ' || ca.DESCRIPCION
                            || ', Provincia ' || pr.DESCRIPCION) || ', País República Dominicana' || --' Código Postal: ' || a.COD_POSTAL ||
                             ', Teléfono: ' || a.TELEFONO || ', extensiones ' ||  REPLACE(a.EXTENCION, ',', ', ')  ||
                             CHR(10) || REPLACE('Horario de atención:-Lunes a Viernes de 8:00am a 5:00pm' || 
                             '-Sábados de 8:00am a 12:00pm' || 
                             '-Domingos' || decode(trabaja_dom,'S', ' de 9:00am a 12:00pm', 'N', ': Cerrado'), '-', CHR(10) || '- ') AS DESCRIPCION
                             )).getClobVal() as XMLDATA
            FROM agencia a, pueblos pu, cantones ca, provincias pr
            WHERE a.cod_empresa = '1'
            AND a.est_agencia = 'A'
            AND a.cod_encargado IS NOT NULL
            AND a.cod_pais = pu.cod_pais
            AND a.cod_provincia = pu.cod_provincia
            AND a.cod_canton = pu.cod_canton
            AND a.cod_distrito = pu.cod_distrito
            AND a.cod_pueblo = pu.cod_pueblo
            AND a.cod_pais = ca.cod_pais
            AND a.cod_provincia = ca.cod_provincia
            AND a.cod_canton = ca.cod_canton
            AND a.cod_pais = pr.cod_pais
            AND a.cod_provincia = pr.cod_provincia            
            ORDER BY TO_NUMBER(REPLACE(a.cod_agencia, '0',''))"""

ARTICULOS_FERIA = """
a.CLIENTE AS COD_CLIENTE), XMLFOREST(a.CLIENTE AS COD_CLIENTE, a.COD_ART, 
TRIM(decode(b.NOMBRE_SERVICIO,d.num_id, 'MATERIALES ' || c.NOMBRE_RECAUDADOR, b.NOMBRE_SERVICIO)) AS DESCRIPCION, 
c.NOMBRE_RECAUDADOR AS SUPLIDOR,
a.FEC_DESPA AS FECHA_DESPACHADO, a.FEC_ENTRE AS FECHA_ENTREGA, a.CANT_ART AS CANTIDAD_ARTICULO,
 DECODE(
        a.estado,
        'D', 'Despachado',
        'A', 'Aprobado',
        'E', 'Entregado',
        'F', 'Facturado', 'Otro ' || a.estado
    ) AS ESTADO_ARTICULO)).GETCLOBVAL()
FROM CJ.TAHAWAII a, CJ.BCJ_CONTRATO_SERVICIO b, CJ.BCJ_RECAUDADORES c, PA.CAPTURA_CLIENTE d
WHERE TO_CHAR(TO_DATE(a.FECTRAN,'dd/mm/yyyy'),'yyyy') = TO_CHAR(SYSDATE,'yyyy')
  AND a.COD_SUP = b.CODIGO_RECAUDADOR
  AND a.COD_ART = b.CODIGO_SERVICIO
  AND a.ESTADO NOT IN ('C')
  AND c.CODIGO_RECAUDADOR NOT IN ('454','13', '936', '90', '995')
  AND c.ESTADO = 'A'
  AND a.ASIENTO IS NOT NULL
  AND c.CODIGO_RECAUDADOR =  b.CODIGO_RECAUDADOR
  AND a.CLIENTE = d.COD_PERSONA
  AND a.CLIENTE = :cod_cliente
"""

CUENTAS = """ a.cod_cliente AS id_cliente,
                        a.cod_agencia AS id_agencia,
                        a.num_cuenta AS id_cuenta),
                        XMLFOREST(
                        a.cod_cliente, a.num_cuenta,                   
                        a.fec_apertura AS fecha_apertura,
                        a.sal_total_cta AS saldo_total,
                        NVL(
                            (
                            SELECT 'Controlada'
                            FROM cuentas_controladas mn, cuenta_efectivo ccm
                            WHERE mn.ESTADO = 'A'
                                AND mn.num_cuenta = ccm.num_cuenta
                                AND ind_estado NOT IN (0, 2)
                                AND mn.num_cuenta = a.num_cuenta
                                AND ROWNUM = 1
                            ),
                            DECODE(
                            a.ind_estado,
                            '1', 'Activa',
                            '3', 'P. x Cancelar',
                            '4', 'Bloqueada',
                            '5', 'Embargada',
                            '6', 'Inactiva'
                            )
                        ) AS estado_cuenta,
                        a.cod_producto,
                        p.descripcion AS descripcion_producto
                        )
                    ).getClobVal()                    
                FROM cuenta_efectivo a, productos p
                WHERE p.cod_cat_producto = 'CC'
                    AND p.cod_producto = a.cod_producto
                    AND a.ind_estado NOT IN ('0', '2')
                    AND a.cod_cliente = :cod_cliente"""

CERTIFICADOS = """ cliente AS id_cliente,
                    cod_agencia AS id_agencia,
                    num_certificado AS id_certificado
                    ),
                XMLFOREST(
                    fec_emision fecha_apertura, monto, tasa_certificado,
                    estado_certificado
                )).getClobVal()
                from (
                    select cliente, cod_agencia, num_certificado, fec_emision, to_char(monto, '999,999,999.00') monto, tas_neta tasa_certificado,
                    decode(estado,'A','Activo',  'R','Retenido') estado_certificado
                    from cd_certificado
                    where estado in ('A','R')
                    Union all
                    select b.cod_persona, a.cod_agencia, a.num_certificado,a.fec_emision, to_char(a.monto, '999,999,999.00') monto, a.tas_neta,
                    decode(a.estado,'A','Activo',  'R','Retenido') estado_certificado
                    from cd_certificado a, cd_beneficiario b
                    where a.estado in ('A','R')                    
                    and a.num_certificado = b.num_certificado)
                    where cliente = :cod_cliente"""

CREDITOS = """ codigo_cliente as id_cliente,
            codigo_agencia as id_agencia,
            no_credito as id_credito
        ),
        XMLFOREST(codigo_cliente,
        no_credito, tipo_de_credito, fecha_primer_desembolso, f_apertura fecha_apertura, f_vencimiento fecha_vencimiento,
        to_char(monto_desembolsado, '999,999,999.00') monto_desembolsado, tasa_interes,codigo_calificacion_sistema, descripcion_calificacion, no_credito_origen credito_origen, 
        to_char(saldo_credito, '999,999,999.00') saldo_credito, estado, decode(estado,
        'D', 'Activo',
        'C', 'Cancelado',
        'J', 'Judicial',
        'V', 'Vencido',
        'M', 'Mora',
        'A', 'Anulado') estado_credito
        )).getClobVal()
from (SELECT a.codigo_cliente, a.codigo_agencia,a.no_credito,b.descripcion tipo_de_credito, a.estado,
decode(a.tipo_credito,561,nvl(
           (SELECT vv.F_MOVIMIENTO
             FROM pr_movimientos vv
            WHERE     vv.no_credito = a.no_credito
                  AND vv.codigo_tipo_transaccion = 39
                  AND vv.estado = 'A'
                  and rownum = 1
                  AND vv.no_transaccion_movim IN
                         (SELECT MAX (kk.no_transaccion_movim)
                            FROM pr_movimientos kk
                           WHERE     kk.no_credito = a.no_credito
                                 AND kk.codigo_tipo_transaccion = 39
                                 AND kk.estado = 'A')),a.f_apertura) ,a.f_primer_desembolso) fecha_primer_desembolso,decode(a.tipo_credito,561,a.monto_credito, a.monto_desembolsado) monto_desembolsado, a.estado estado_credito, a.tasa_interes,
                                 a.codigo_calificacion_sistema, c.descripcion_calificacion, A.no_credito_origen,a.tipo_credito,
                                 pr.saldo_credito_cliente(a.codigo_cliente, a.no_credito,a.tipo_credito, a.f_primer_desembolso) saldo_credito, a.f_apertura, a.f_vencimiento
                            FROM pr_calificacion_credito c,pr_tipo_credito b, pr_creditos a
                            WHERE a.estado IN ('D','C','J','V','M','A', 'R')
                            AND a.f_vencimiento > (SYSDATE - (365 * 5))
                            AND a.tipo_credito <> '9'
                            AND a.tipo_credito = b.tipo_credito
                            AND a.codigo_calificacion_sistema = c.codigo_calificacion(+)) 
                            WHERE codigo_cliente = :cod_cliente""" 

CLIENTES = """  c.cod_persona AS id_cliente, 
                c.cod_agencia AS id_agencia,
                c.cod_agencia||'-'||c.cod_distrito_coop AS id_distrito),
                        XMLFOREST(                          
                          to_char(c.fec_inclusion, 'yyyy-mm-dd') AS FECHA_INCLUSION,
                          c.NUM_DEPENDIENTES AS DEPENDIENTES,
                          (SELECT nombre FROM paises WHERE codigo_pais = c.cod_nacionalidad) AS nacionalidad,
                          c.primer_nombre,
                          c.segundo_nombre,
                          c.primer_apellido,
                          c.segundo_apellido,
                          DECODE(c.sexo, 'M', 'Masculino', 'F', 'Femenino', 'Indefinido') AS sexo,
                          c.FEC_NACIMIENTO AS fecha_nacimiento,
                          c.cod_profesion,
                          c.actividad,
                          c.nom_empresa,
                          (case when to_char(c.fec_ingreso, 'yyyy') = '0000' then c.fec_inclusion else c.fec_ingreso end) AS FECHA_INGRESO,
                          c.cargo,
                          to_char(c.ingreso_mensual, '999,999,999.00') ingreso_mensual,
                          to_char(c.otros_ingresos, '999,999,999.00') otros_ingresos,
                          c.actividad_conyugue,
                          c.nom_empresa_conyugue,
                          c.cargo_conyugue,
                          to_char(c.ingreso_mensual_conyugue, '999,999,999.00') ingreso_mensual_conyugue,
                          to_char(c.otros_ingresos_conyugue, '999,999,999.00') otros_ingresos_conyugue,
                          CC.socio_activo_pasivo(b.num_cuenta) AS estado_del_cliente
                          )).getClobVal()
                          FROM captura_cliente c, cuenta_efectivo b
                  WHERE  b.cod_producto IN(601,602,603) 
                    AND (b.ind_estado IN (1, 3, 4, 5, 6))
                    AND c.cod_persona = b.cod_cliente
                    AND c.cod_persona = :cod_cliente""" 


def obtener_conversaciones(canal=None, fecha_desde=None, fecha_hasta=None,
                           q=None, cod_persona=None,
                           pagina=1, por_pagina=50):
    """Devuelve conversaciones, con filtros sobre sus mensajes y paginación."""
    con = sqlite3.connect(CHATBOT_DB)
    cur = con.cursor()

    where = []
    params = []
    if canal:
        where.append("m.canal = ?")
        params.append(canal)
    if fecha_desde:
        where.append("m.fecha_hora >= ?")
        params.append(fecha_desde)
    if fecha_hasta:
        where.append("m.fecha_hora < datetime(?, '+1 day')")
        params.append(fecha_hasta)
    if cod_persona:
        where.append("c.cod_persona = ?")
        params.append(cod_persona)
    if q:
        where.append("m.contenido LIKE ?")
        like = f"%{q}%"
        params.append(like)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    cur.execute(
        f"""SELECT COUNT(DISTINCT c.id)
              FROM conversaciones c
              JOIN mensajes m ON m.conversacion_id = c.id{where_sql}""",
        params,
    )
    total = cur.fetchone()[0]

    pagina = max(1, int(pagina or 1))
    por_pagina = max(1, min(500, int(por_pagina or 50)))
    offset = (pagina - 1) * por_pagina

    cur.execute(
        f"""SELECT c.id AS conversacion_id,
                   c.session_id,
                   COALESCE(MAX(m.canal), c.canal_origen, c.canal) AS canal,
                   c.cod_persona,
                   MIN(m.fecha_hora) AS fecha_inicio,
                   MAX(m.fecha_hora) AS fecha_fin,
                   COUNT(m.id) AS mensajes,
                   COALESCE(
                       MAX(NULLIF(c.telefono, '')),
                       MAX(CASE WHEN m.direccion = 'IN' AND json_valid(m.metadata)
                                THEN json_extract(m.metadata, '$.message.from') END)
                   ) AS telefono
              FROM conversaciones c
              JOIN mensajes m ON m.conversacion_id = c.id{where_sql}
             GROUP BY c.id, c.session_id, c.canal_origen, c.canal, c.cod_persona
             ORDER BY MAX(m.fecha_hora) DESC, c.id DESC
            LIMIT ? OFFSET ?""",
        params + [por_pagina, offset],
    )
    filas = cur.fetchall()
    con.close()
    return filas, total


def obtener_conversacion_header(conversacion_id):
    """Devuelve los datos de cabecera de una conversación (sin mensajes).

    Incluye el teléfono: si la columna está vacía (datos antiguos) se intenta
    extraer del metadata del mensaje entrante (message.from)."""
    con = sqlite3.connect(CHATBOT_DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        """SELECT c.id, c.session_id, c.cod_persona, c.estado, c.asignado_a,
                  c.atendido_por, c.fecha_asignacion,
                  COALESCE(MAX(c.canal), c.canal_origen) AS canal,
                  COALESCE(
                      NULLIF(c.telefono, ''),
                      MAX(CASE WHEN m.direccion = 'IN' AND json_valid(m.metadata)
                               THEN json_extract(m.metadata, '$.message.from') END)
                  ) AS telefono
             FROM conversaciones c
             LEFT JOIN mensajes m ON m.conversacion_id = c.id
            WHERE c.id = ?
            GROUP BY c.id""",
        (conversacion_id,),
    )
    row = cur.fetchone()
    con.close()
    return dict(row) if row else None


def marcar_atendido_por(conversacion_id, atendido_por, asignado_a=None):
    """Marca quién atiende la conversación: 'bot' o 'humano'.

    Cuando pasa a 'humano' registra la fecha de asignación y, si se indica,
    el agente asignado. No toca ninguna otra columna ni mensaje (compatibilidad
    total con conversaciones existentes)."""
    con = sqlite3.connect(CHATBOT_DB)
    cur = con.cursor()
    if atendido_por == 'humano':
        if asignado_a:
            cur.execute(
                """UPDATE conversaciones
                      SET atendido_por = ?, fecha_asignacion = CURRENT_TIMESTAMP, asignado_a = ?
                    WHERE id = ?""",
                (atendido_por, asignado_a, conversacion_id),
            )
        else:
            cur.execute(
                """UPDATE conversaciones
                      SET atendido_por = ?, fecha_asignacion = CURRENT_TIMESTAMP
                    WHERE id = ?""",
                (atendido_por, conversacion_id),
            )
    else:
        cur.execute(
            "UPDATE conversaciones SET atendido_por = ? WHERE id = ?",
            (atendido_por, conversacion_id),
        )
    con.commit()
    afectadas = cur.rowcount
    con.close()
    logg(f"marcar_atendido_por: conv={conversacion_id} atendido_por={atendido_por} asignado_a={asignado_a}")
    return afectadas > 0


def obtener_atendido_por(conversacion_id):
    """Devuelve 'bot'|'humano'|None (None = nunca asignado => se trata como bot)."""
    con = sqlite3.connect(CHATBOT_DB)
    cur = con.cursor()
    cur.execute("SELECT atendido_por FROM conversaciones WHERE id = ?", (conversacion_id,))
    row = cur.fetchone()
    con.close()
    return row[0] if row else None


def transferir_conversacion(conversacion_id, asignado_a):
    """Reasigna la conversación a otro agente (no cambia atendido_por)."""
    con = sqlite3.connect(CHATBOT_DB)
    cur = con.cursor()
    cur.execute(
        "UPDATE conversaciones SET asignado_a = ?, atendido_por = 'humano' WHERE id = ?",
        (asignado_a, conversacion_id),
    )
    con.commit()
    afectadas = cur.rowcount
    con.close()
    logg(f"transferir_conversacion: conv={conversacion_id} asignado_a={asignado_a}")
    return afectadas > 0


def cerrar_conversacion(conversacion_id):
    """Cierra el caso: estado=CERRADA, registra fecha_cierre y devuelve el control
    al bot (atendido_por='bot')."""
    con = sqlite3.connect(CHATBOT_DB)
    cur = con.cursor()
    cur.execute(
        """UPDATE conversaciones
              SET estado = 'CERRADA',
                  atendido_por = 'bot',
                  fecha_cierre = CURRENT_TIMESTAMP
            WHERE id = ?""",
        (conversacion_id,),
    )
    con.commit()
    afectadas = cur.rowcount
    con.close()
    logg(f"cerrar_conversacion: conv={conversacion_id}")
    return afectadas > 0


def guardar_nota_interna(conversacion_id, agente, texto):
    """Guarda una nota interna del agente asociada a la conversación.

    Se persiste como un mensaje con direccion='NOTE' para que NO se entregue por
    ningún canal (la entrega sólo ocurre en endpoints que filtran IN/OUT) y se
    pueda mostrar en el panel del agente. No crea conversaciones nuevas."""
    con = sqlite3.connect(CHATBOT_DB)
    cur = con.cursor()
    cur.execute("SELECT canal, canal_origen FROM conversaciones WHERE id = ?", (conversacion_id,))
    row = cur.fetchone()
    if not row:
        con.close()
        return {"ok": False, "error": "not_found"}
    canal = row[0] or row[1] or 'wc'
    cur.execute(
        """INSERT INTO mensajes (conversacion_id, direccion, canal, contenido, enviado_por)
           VALUES (?, 'NOTE', ?, ?, ?)""",
        (conversacion_id, canal, texto, agente),
    )
    mensaje_id = cur.lastrowid
    con.commit()
    con.close()
    logg(f"guardar_nota_interna: conv={conversacion_id} agente={agente}")
    return {"ok": True, "mensaje_id": mensaje_id}


def obtener_mensajes_conversacion(conversacion_id):
    """Devuelve los mensajes de una conversación ordenados cronológicamente."""
    con = sqlite3.connect(CHATBOT_DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        """SELECT m.id, m.fecha_hora, m.direccion, m.canal, m.contenido,
                  m.message_id, m.provider_message_id, m.template_id,
                  m.metadata, m.enviado_por,
                  m.tiene_archivo, m.archivo_nombre, m.archivo_tipo,
                  m.archivo_url, m.archivo_size,
                  c.session_id, c.cod_persona, c.telefono, c.asignado_a,
                  c.atendido_por
             FROM mensajes m
             JOIN conversaciones c ON c.id = m.conversacion_id
            WHERE m.conversacion_id = ?
            ORDER BY m.fecha_hora ASC, m.id ASC""",
        (conversacion_id,),
    )
    out = [dict(row) for row in cur.fetchall()]
    con.close()
    return out


def obtener_interacciones(canal=None, fecha_desde=None, fecha_hasta=None,
                          q=None, cod_persona=None, conversacion_id=None,
                          pagina=1, por_pagina=50):
    """Devuelve mensajes con datos de su conversación para exportación."""
    con = sqlite3.connect(CHATBOT_DB)
    cur = con.cursor()

    where = []
    params = []
    if canal:
        where.append("m.canal = ?")
        params.append(canal)
    if fecha_desde:
        where.append("m.fecha_hora >= ?")
        params.append(fecha_desde)
    if fecha_hasta:
        where.append("m.fecha_hora < datetime(?, '+1 day')")
        params.append(fecha_hasta)
    if cod_persona:
        where.append("c.cod_persona = ?")
        params.append(cod_persona)
    if conversacion_id:
        where.append("c.id = ?")
        params.append(conversacion_id)
    if q:
        where.append("m.contenido LIKE ?")
        like = f"%{q}%"
        params.append(like)

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    base = " FROM mensajes m JOIN conversaciones c ON c.id = m.conversacion_id"
    cur.execute(f"SELECT COUNT(*){base}{where_sql}", params)
    total = cur.fetchone()[0]

    pagina = max(1, int(pagina or 1))
    por_pagina = max(1, min(500, int(por_pagina or 50)))
    offset = (pagina - 1) * por_pagina

    cur.execute(
        f"""SELECT m.id, m.fecha_hora, c.id AS conversacion_id, c.session_id,
                   c.cod_persona, m.canal, m.direccion, m.contenido,
                   m.enviado_por, m.message_id, m.provider_message_id,
                   m.template_id, m.metadata
              {base}{where_sql}
             ORDER BY m.fecha_hora DESC, m.id DESC LIMIT ? OFFSET ?""",
        params + [por_pagina, offset]
    )
    filas = cur.fetchall()
    columnas = [d[0] for d in cur.description]
    con.close()
    return columnas, filas, total

def obtener_respuestas_plantilla(desde=None, hasta=None, q=None, pagina=1, por_pagina=50):
    """Devuelve interacciones WA que son respuesta a una plantilla de otro sistema.
    Filtra por intencion JSON que contenga intent='respuesta_plantilla'.
    Retorna (filas, total). Cada fila:
        (id, fecha_hora, session_id, cod_persona, canal, pregunta, intencion, respuesta)
    """
    con = sqlite3.connect(CHATBOT_DB)
    cur = con.cursor()

    where = ["canal = 'wa'"]
    params = []
    if desde:
        where.append("fecha_hora >= ?"); params.append(desde)
    if hasta:
        where.append("fecha_hora < datetime(?, '+1 day')"); params.append(hasta)
    if q:
        like = f"%{q}%"
        where.append("""
            (
                pregunta LIKE ?
                OR session_id LIKE ?
                OR intencion LIKE ?
                OR respuesta LIKE ?
            )
        """)
        params.extend([like, like, like, like])
    w = " WHERE " + " AND ".join(where)

    cur.execute(f"SELECT COUNT(*) FROM interacciones_chatbot{w}", params)
    total = cur.fetchone()[0]

    pagina = max(1, int(pagina or 1))
    por_pagina = max(1, min(500, int(por_pagina or 50)))
    offset = (pagina - 1) * por_pagina

    cur.execute(
        f"SELECT id, fecha_hora, session_id, cod_persona, canal, pregunta, intencion, respuesta "
        f"FROM interacciones_chatbot{w} "
        f"ORDER BY fecha_hora DESC, id DESC LIMIT ? OFFSET ?",
        params + [por_pagina, offset]
    )
    filas_raw = cur.fetchall()
    con.close()
    #logg(f" {w}. Filas obtenidas: {total}")
    return filas_raw, total

def guardar_cliente(numero):

    conn = sqlite3.connect(CHATBOT_DB)
    cur = conn.cursor()
    conversacion_id = redisdb.get_variable(numero, "conversacion_id")
    cod_persona_b = redisdb.get_variable(numero, "cod_persona")
    cod_persona = cod_persona_b.decode() if cod_persona_b else None
    templateId_b = redisdb.get_variable(numero, "templateId")
    templateId = templateId_b.decode() if templateId_b else None
    cur.execute("""
            UPDATE conversaciones
               SET cod_persona = ?, template_id = ?
             WHERE id = ?
    """, (cod_persona, templateId, conversacion_id))

    conn.commit()

def guardar_mensaje(
    session_id,
    canal,
    direccion,
    contenido,
    cod_persona=None,
    telefono=None,
    template_id=None,
    message_id=None,
    provider_message_id=None,
    metadata=None,
    archivo=None,
    enviado_por='sistema'
):
    """
    Guarda un mensaje dentro de una conversación.

    direccion:
        IN  = mensaje recibido
        OUT = mensaje enviado

    archivo:
    {
        "nombre": "foto.jpg",
        "tipo": "image/jpeg",
        "url": "https://...",
        "size": 123456
    }
    """

    conn = None

    try:
        conn = sqlite3.connect(CHATBOT_DB)
        conn.row_factory = sqlite3.Row

        cur = conn.cursor()
        enviado_por = enviado_por if direccion == 'OUT' else 'usuario'
        #
        # Buscar conversación abierta
        #
        cur.execute("""
            SELECT id
            FROM conversaciones
            WHERE (session_id = ? OR telefono = ?)
              AND estado = 'ABIERTA'
            ORDER BY id DESC
            LIMIT 1
        """, (session_id, telefono))

        row = cur.fetchone()

        #
        # Crear conversación si no existe
        #
        if row:
            conversacion_id = row["id"]
        else:

            cur.execute("""
                INSERT INTO conversaciones (
                    session_id,
                    canal,
                    canal_origen,
                    cod_persona,
                    telefono,
                    estado
                )
                VALUES (?, ?, ?, ?, ?, 'ABIERTA')
            """, (
                session_id,
                canal,
                canal,
                cod_persona,
                telefono
            ))

            conversacion_id = cur.lastrowid           
        
        #
        # Metadata JSON
        #
        metadata_json = None

        if metadata:
            metadata_json = json.dumps(
                metadata,
                ensure_ascii=False,
                default=str
            )

        #
        # Archivo
        #
        tiene_archivo = 0
        archivo_nombre = None
        archivo_tipo = None
        archivo_url = None
        archivo_size = None

        if archivo:
            tiene_archivo = 1
            archivo_nombre = archivo.get("nombre")
            archivo_tipo = archivo.get("tipo")
            archivo_url = archivo.get("url")
            archivo_size = archivo.get("size")

        #
        # Insertar mensaje
        #
        cur.execute("""
            INSERT INTO mensajes (
                conversacion_id,
                direccion,
                canal,
                message_id,
                provider_message_id,
                contenido,
                tiene_archivo,
                archivo_nombre,
                archivo_tipo,
                archivo_url,
                archivo_size,
                template_id,
                metadata,
                enviado_por
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            conversacion_id,
            direccion,
            canal,
            message_id,
            provider_message_id,
            contenido,
            tiene_archivo,
            archivo_nombre,
            archivo_tipo,
            archivo_url,
            archivo_size,
            template_id,
            metadata_json,
            enviado_por
        ))

        mensaje_id = cur.lastrowid

        #
        # Actualizar fecha último mensaje
        #
        cur.execute("""
            UPDATE conversaciones
               SET fecha_ultimo_mensaje = CURRENT_TIMESTAMP
             WHERE id = ?
        """, (conversacion_id,))

        conn.commit()

        logg(
            f"guardar_mensaje: "
            f"conv={conversacion_id} "
            f"msg={mensaje_id} "
            f"dir={direccion} "
            f"canal={canal} "
            f"enviado_por={enviado_por} "
            f"contenido={contenido}"
        )
        redisdb.set_variable(telefono, "session_id", session_id)
        redisdb.set_variable(telefono, "conversacion_id", conversacion_id)
        return {
            "ok": True,
            "conversacion_id": conversacion_id,
            "mensaje_id": mensaje_id
        }

    except Exception as e:

        if conn:
            conn.rollback()

        loge(f"guardar_mensaje: {e}")

        return {
            "ok": False,
            "error": str(e)
        }

    finally:

        if conn:
            conn.close()
    

def guardar_interaccion(session_id, cod_cliente, canal, pregunta, intencion, respuesta, detalle=None):
    intent_source = intencion.get('intent_source') if isinstance(intencion, dict) else None
    intencion_str = json.dumps(intencion, ensure_ascii=False) if isinstance(intencion, dict) else intencion
    conn = sqlite3.connect(CHATBOT_DB)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO interacciones_chatbot
        (session_id, cod_persona, canal, pregunta, intencion, respuesta, intent_source, detalle)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (session_id, cod_cliente, canal, pregunta, intencion_str, respuesta, intent_source, detalle))
    conn.commit()
    conn.close()
    chat = ConversationManager(session_id)
    chat.add_user_message(pregunta)
    chat.add_assistant_message(respuesta)


def moneda(num):
    num = num if num is not None else 0
    # Formatear el número como moneda
    moneda_ = locale.currency(num, grouping=True).split("$")[1]
    # Eliminar los decimales
    #moneda_sin_decimales = moneda.split('.')[0]
    return f"RD${moneda_}" #moneda_sin_decimales

def fin(inicio):
    segundos = time.time() - inicio
    dias = int(segundos // (24 * 3600))
    segundos = segundos % (24 * 3600)
    horas = int(segundos // 3600)
    segundos %= 3600
    minutos = int(segundos // 60)
    segundos = int(segundos % 60) 
    return f"{dias:02d}d {horas:02d}:{minutos:02d}:{segundos:02d}"

def tago(str):
    return ("<" + str + "s>").upper()

def tagc(str):
    return ("</" + str + "s>").upper()

def ejecuta(tabla, query, cod_cliente = None, mostrar_query = False):
    global connection
    inicio = time.time()
    registros = 0
    logg("Procesando " + tabla + "s...")
    SELECT = """SELECT 
                    XMLELEMENT(
                        NAME """ + tabla + """,
                        XMLATTRIBUTES(""" + query
    if mostrar_query:
        print("Query: " + SELECT)

    cursor = connection.cursor()
    if cod_cliente:
        cursor.execute(SELECT, {'cod_cliente': cod_cliente})
    else: 
        cursor.execute(SELECT)
    fila = None
    datos = []
    datos.append(tago(tabla))
    while True:
        row = cursor.fetchone()
        if row is None:
            break
        else:
            if fila != row[0].read():
                registros += 1
                fila = row[0].read()
                datos.append(fila)

    datos.append(tagc(tabla))
    logg(f"Tabla procesada '{tabla}'. Registros procesados: {registros} tiempo de procesamiento: {fin(inicio)}")
    return "\n".join(datos)

def enmascarar_pci(pan):
    pan = str(pan).strip()
    if len(pan) < 10:
        return '*' * len(pan)  # En caso de ser muy corto, se enmascara completo
    return f"{pan[:6]}{'*' * (len(pan) - 10)}{pan[-4:]}"

def buscar_cliente_por_cedula(cedula):
    try:
        cursor = connection.cursor()
        query = """
        SELECT COD_PERSONA, SEXO, REPLACE(REPLACE(REPLACE(CELULAR ||',' || TELEFONO, '-', ''), '.', ''), '+', '') AS TELEFONO,
         INITCAP(PRIMER_NOMBRE || ' ' || SEGUNDO_NOMBRE) nombres, 
         INITCAP(PRIMER_APELLIDO || ' ' || SEGUNDO_APELLIDO) apellidos         
        FROM captura_cliente
        WHERE num_id = :cedula
        """
        valida, mensaje, cedula = validar_cedula(cedula)
        logg(f"buscar_cliente_por_cedula({cedula}) {mensaje}")
        if valida:
            cursor.execute(query, {'cedula': cedula})
            row = cursor.fetchone()
            if row:
                return {"cod_persona": row[0], "sexo": row[1], "celular": row[2], "nombres" : row[3], "apellidos": row[4]}
            else:
                return None
        else:
            return None
    except Exception as e:
        logg(f"Error buscando cliente por cédula: {e}")
        return None

def buscar_cliente(cod_persona):
    try:
        cursor = connection.cursor()
        query = """
        SELECT COD_PERSONA, SEXO, CELULAR ||',' || TELEFONO,
         INITCAP(PRIMER_NOMBRE || ' ' || SEGUNDO_NOMBRE) nombres, 
         INITCAP(PRIMER_APELLIDO || ' ' || SEGUNDO_APELLIDO) apellidos         
        FROM captura_cliente
        WHERE cod_persona = :cod_persona
        """        
        cursor.execute(query, {'cod_persona': cod_persona})
        row = cursor.fetchone()
        if row:
            return {"cod_persona": row[0], "sexo": row[1], "celular": row[2], "nombres" : row[3], "apellidos": row[4]}
        else:
            return None
        
    except Exception as e:
        logg(f"Error buscando cliente por cédula: {e}")
        return None


def consulta_prestamo(cod_persona, no_credito):
    try:
        datos_cliente = buscar_cliente(cod_persona)
        cursor = connection.cursor()    
        ###INICIO
        # =============================================
        # Variables NUMÉRICAS (NUMBER en Oracle)
        # =============================================
        Gn_Empresa = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Agencia = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_SubAplicacion = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Cuenta = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Cliente = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Codigo_Moneda = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Monto = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Tasa = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Capital_Vigente = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Balance_Capital = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Saldo_Total = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Cuota = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Cuota_Vencida = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Capital_Vencido = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Interes_Vencido = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Mora = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Total_Cargo = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Total_Vencido = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Capital_Pagar = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Interes_Pagar = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Cargos_Pagar = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Total_a_Pagar = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Interes_Cobrar_Vigente = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_interes_cobrado_anticipado = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_mensualidad_anticipada = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Plazo = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Tipo_Amortizacion = cursor.var(str, 20)
        Gn_Numero_Prestamo = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Numero_Garantia = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Atraso = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Capital_Actual = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gn_Interes_Actual = cursor.var(oracledb.DB_TYPE_NUMBER)
        Gi_CodigoError = cursor.var(oracledb.DB_TYPE_NUMBER)  # Código de error (OUT)

        # =============================================
        # Variables de TEXTO (VARCHAR2 en Oracle)
        # =============================================
        Gv_Aplicacion = cursor.var(str, 100)  # Asumiendo tamaño máximo 100 caracteres
        Gv_Descripcion_Moneda = cursor.var(str, 100)
        Gv_Abreviatura_Moneda = cursor.var(str, 10)
        Gv_Nombre_Cliente = cursor.var(str, 200)
        Gv_Cuenta_Debito = cursor.var(str, 50)
        Gv_Descripcion = cursor.var(str, 255)
        Gv_Estado = cursor.var(str, 50)
        Gv_Desc_Garantia = cursor.var(str, 255)
        Gv_Debito_credito_todo = cursor.var(str, 10)
        Gv_Ordenamiento = cursor.var(str, 50)
        Gv_Descripcion_Error = cursor.var(str, 500)  # Mensaje de error (OUT)

        # =============================================
        # Variables de FECHA (DATE en Oracle)
        # =============================================
        Gd_Fecha_Desembolso = cursor.var(oracledb.DB_TYPE_DATE)
        Gd_Fecha_Vencimiento = cursor.var(oracledb.DB_TYPE_DATE)
        Gd_Fecha_Proximo_Pago = cursor.var(oracledb.DB_TYPE_DATE)
        Gd_FechaHoy = cursor.var(oracledb.DB_TYPE_DATE)  
        Gd_Fecha_Desde = cursor.var(oracledb.DB_TYPE_DATE)
        Gd_Fecha_Hasta = cursor.var(oracledb.DB_TYPE_DATE)
        Gd_Fecha_Ultimo_Pago = cursor.var(oracledb.DB_TYPE_DATE)

        # =============================================
        # Variable CURSOR (para resultados tabulares)
        # =============================================
        Gc_Mov = cursor.var(oracledb.DB_TYPE_CURSOR)

        # =============================================
        # Llamada al procedimiento
        # =============================================
        Gn_Empresa.setvalue(0,1)
        Gn_Cuenta.setvalue(0,int(no_credito))
        Gn_Cliente.setvalue(0, int(cod_persona))
        Gv_Debito_credito_todo.setvalue(0, 'T')
        Gv_Ordenamiento.setvalue(0, 'A')
        Gn_Agencia.setvalue(0,None)
        Gn_SubAplicacion.setvalue(0, None)
        Gv_Aplicacion.setvalue(0, None)
        Gd_Fecha_Desde.setvalue(0, None)
        Gd_Fecha_Hasta.setvalue(0, None)
        
        params = {
            # Parámetros IN
            'Gn_Empresa': Gn_Empresa,
            'Gn_Agencia': Gn_Agencia,
            'Gn_SubAplicacion': Gn_SubAplicacion, 
            'Gn_Cuenta': Gn_Cuenta,
            'Gn_Cliente': Gn_Cliente,
            'Gv_Aplicacion': Gv_Aplicacion,
            'Gd_Fecha_Desde': Gd_Fecha_Desde,
            'Gd_Fecha_Hasta' : Gd_Fecha_Hasta,
            'Gv_Debito_credito_todo': Gv_Debito_credito_todo,
            'Gv_Ordenamiento': Gv_Ordenamiento,
            # Parámetros OUT,
            'Gn_Codigo_Moneda' : Gn_Codigo_Moneda,
            'Gv_Descripcion_Moneda' : Gv_Descripcion_Moneda,
            'Gv_Abreviatura_Moneda' : Gv_Abreviatura_Moneda,
            'Gv_Nombre_Cliente' : Gv_Nombre_Cliente,
            'Gd_Fecha_Desembolso' : Gd_Fecha_Desembolso,
            'Gd_Fecha_Vencimiento' : Gd_Fecha_Vencimiento,
            'Gn_Monto' : Gn_Monto,
            'Gn_Tasa' : Gn_Tasa,
            'Gn_Capital_Vigente' : Gn_Capital_Vigente,
            'Gn_Balance_Capital' : Gn_Balance_Capital,
            'Gn_Saldo_Total' : Gn_Saldo_Total,
            'Gn_Cuota' : Gn_Cuota,
            'Gn_Cuota_Vencida' : Gn_Cuota_Vencida,
            'Gn_Capital_Vencido' : Gn_Capital_Vencido,
            'Gn_Interes_Vencido' : Gn_Interes_Vencido,
            'Gn_Mora' : Gn_Mora,
            'Gn_Total_Cargo' : Gn_Total_Cargo,
            'Gn_Total_Vencido' : Gn_Total_Vencido,
            'Gd_Fecha_Proximo_Pago' : Gd_Fecha_Proximo_Pago,
            'Gn_Capital_Pagar' : Gn_Capital_Pagar,
            'Gn_Interes_Pagar' : Gn_Interes_Pagar,
            'Gn_Cargos_Pagar' : Gn_Cargos_Pagar,
            'Gn_Total_a_Pagar' : Gn_Total_a_Pagar,
            'Gn_Interes_Cobrar_Vigente' : Gn_Interes_Cobrar_Vigente,
            'Gn_interes_cobrado_anticipado' : Gn_interes_cobrado_anticipado,
            'Gn_mensualidad_anticipada' : Gn_mensualidad_anticipada,
            'Gn_Plazo' : Gn_Plazo,
            'Gn_Tipo_Amortizacion' : Gn_Tipo_Amortizacion,
            'Gd_FechaHoy' : Gd_FechaHoy,
            'Gv_Cuenta_Debito' : Gv_Cuenta_Debito,
            'Gn_Numero_Prestamo' : Gn_Numero_Prestamo,
            'Gv_Descripcion' : Gv_Descripcion,
            'Gv_Estado' : Gv_Estado,
            'Gc_Mov' : Gc_Mov,
            'Gn_Numero_Garantia' : Gn_Numero_Garantia,
            'Gv_Desc_Garantia' : Gv_Desc_Garantia,
            'Gn_Atraso' : Gn_Atraso,
            'Gd_Fecha_Ultimo_Pago' : Gd_Fecha_Ultimo_Pago,
            'Gn_Capital_Actual' : Gn_Capital_Actual,
            'Gn_Interes_Actual' : Gn_Interes_Actual,
            'Gi_CodigoError': Gi_CodigoError,  
            'Gv_Descripcion_Error': Gv_Descripcion_Error
        }
        cursor.callproc("PR.PR_INTERFAZ_IB.consulta_prestamo", keywordParameters=params)
        
        # Obtener resultados
        if Gi_CodigoError.getvalue() == 0:
            logg("consulta_prestamo: Éxito:", Gv_Descripcion_Error.getvalue())
            # Procesar otros resultados...
        else:
            logg(f"consulta_prestamo: Error {Gi_CodigoError.getvalue()}: {Gv_Descripcion_Error.getvalue()}")
        
        ####FIN
        result = {
            "tipo": "producto", "subtipo": "prestamo",
            "nombre_asociado": datos_cliente["nombres"],
            "numero_producto": Gn_Numero_Prestamo.getvalue(),
            "estado": Gv_Estado.getvalue(),
            "fecha_desembolso": str(Gd_Fecha_Desembolso.getvalue()).replace(" 00:00:00",""),
            "fecha_vencimiento": str(Gd_Fecha_Vencimiento.getvalue()).replace(" 00:00:00",""),
            "monto_prestamo": Gn_Monto.getvalue(),
            "monto_prestamo_formateado": moneda(Gn_Monto.getvalue()),
            "cuota": Gn_Cuota.getvalue(),
            "cuota_formateado": moneda(Gn_Cuota.getvalue()),
            "tasa": Gn_Tasa.getvalue(),
            "saldo_total": Gn_Saldo_Total.getvalue(),
            "saldo_formateado" : moneda(Gn_Saldo_Total.getvalue()),
            "proximo_pago": str(Gd_Fecha_Proximo_Pago.getvalue()).replace(" 00:00:00",""),
            "total_a_pagar": Gn_Total_a_Pagar.getvalue(),
            "total_a_pagar_formateado": moneda(Gn_Total_a_Pagar.getvalue()),
            "moneda": Gv_Abreviatura_Moneda.getvalue(),
            "descripcion_moneda": Gv_Descripcion_Moneda.getvalue(),
            "codigo_moneda": "DOP",
            "descripcion": Gv_Descripcion.getvalue(),
            #"descripcion_garantia": Gv_Desc_Garantia.getvalue(),
            "fecha_ultimo_pago": str(Gd_Fecha_Ultimo_Pago.getvalue()).replace(" 00:00:00",""),
            "capital_actual": Gn_Capital_Actual.getvalue(),
            "capital_actual_formateado": moneda(Gn_Capital_Actual.getvalue()),            
            "interes_actual": Gn_Interes_Actual.getvalue(),
            "interes_actual_formateado": moneda(Gn_Interes_Actual.getvalue()),
            "codigo_error": Gi_CodigoError.getvalue(),
            "mensaje_error": Gv_Descripcion_Error.getvalue()
        }
        return result
    except Exception as e:
            print(f"Error consulta_prestamo: {e}")
            return e

def envia_sms(destino, mensaje):
    try:
        # Normalizar destino: eliminar separadores y convertir a formato E.164 cuando sea posible.
        def _normalize_phone(dest):
            if not dest:
                return dest
            s = str(dest).strip()
            # si ya tiene prefijo + conservar solo dígitos
            if s.startswith('+'):
                digits = re.sub(r'\D', '', s)
                return '+' + digits
            # quitar cualquier caractere no numérico
            digits = re.sub(r'\D', '', s)
            if not digits:
                return dest
            # si viene con 11 dígitos y comienza con 1 -> asume +1
            if len(digits) == 11 and digits.startswith('1'):
                return '+' + digits
            # si son 10 dígitos, verificar si es número dominicano (809, 829, 849)
            if len(digits) == 10:
                if digits[:3] in ('809', '829', '849'):
                    return '+1' + digits
                # Si no es dominicano, asumir NANP (+1) por defecto para números de 10 dígitos
                return '+1' + digits
            # caso general: anteponer + y los dígitos
            return '+' + digits

        destino_norm = _normalize_phone(destino)
        # usar el destino normalizado si cambió
        if destino_norm:
            destino = destino_norm
        cursor = connection.cursor()
        ret = cursor.var(int)
        logg(f"Enviando mensaje a {destino}: {mensaje}")
        cursor.execute("""
            BEGIN 
                :ret := PA.PKG_NOTIFICACION_CLIENTE.ENVIASMS(
                    pDestino => :d, 
                    pMensaje => :m
                );
            END;
        """, ret=ret, d=destino, m=mensaje)

        resultado = ret.getvalue()
        return resultado

    except Exception as e:
        print(f"Error enviando SMS: {e}")
        return None

def validar_usuario(usuario, password):
    sql = ("SELECT 1 "
          " FROM USUARIOS "
          " WHERE EST_ACTIVO = 'S' "
          " AND COD_USUARIO  = UPPER(:usuario) "
          " AND PALABRA_PASO = ENCRIPTAR(UPPER(:pass)) ")
    binds = {"usuario": usuario, "pass": password}
    cursor = connection.cursor()
    cursor.execute(sql, binds)
    rows = cursor.fetchmany(1)
    if rows:
        return True
    return False

def nombre_usuario(usuario):
    sql = ("SELECT NVL(pa.Nombre_clientefj(cod_per_fisica), COD_USUARIO) "
          " FROM USUARIOS "
          " WHERE EST_ACTIVO = 'S' "
          " AND COD_USUARIO  = UPPER(:usuario) "
          )
    binds = {"usuario": usuario}
    cursor = connection.cursor()
    cursor.execute(sql, binds)
    rows = cursor.fetchmany(1)
    if rows:
        return rows[0][0]
    return False

def _candidatos_destino(destino):
    """Normaliza un destino a sus variantes de número (sólo dígitos).

    Devuelve la lista de candidatos a buscar en DESTINO, sin duplicados.
    """
    digits = re.sub(r"\D", "", str(destino or ""))
    if not digits:
        return []
    candidates = [digits]
    # si viene con prefijo 1 (ej. 1829...), incluir sin prefijo
    if digits.startswith('1') and len(digits) == 11:
        candidates.append(digits[1:])
    # si viene sin prefijo y tiene 10 dígitos, incluir con 1 delante
    if len(digits) == 10:
        candidates.append('1' + digits)
    # eliminar duplicados preservando orden
    return list(dict.fromkeys(candidates))


def _parse_detalle_lob(detalle_raw):
    """Lee/parsea el campo DETALLE_ESTADO (posible LOB) a JSON o str."""
    try:
        detalle_s = detalle_raw.read() if hasattr(detalle_raw, 'read') else detalle_raw
    except Exception:
        detalle_s = detalle_raw
    try:
        if isinstance(detalle_s, (bytes, bytearray)):
            detalle_s = detalle_s.decode('utf-8', errors='ignore')
        if isinstance(detalle_s, str) and detalle_s.strip():
            return json.loads(detalle_s)
    except Exception:
        pass
    return detalle_s


def buscar_notificaciones_por_destinos(destinos, tipo_notificacion=2):
    """Versión por lote de buscar_notificaciones_por_destino.

    Recibe un iterable de destinos y hace UNA sola consulta a Oracle (dividida
    en lotes por el límite del IN), en lugar de una consulta por destino.

    Retorna un dict { destino_original: detalle } donde `detalle` es la
    notificación enviada (ESTADO=2) más reciente para cualquier variante del
    número. Los destinos sin notificación quedan fuera del dict.
    """
    # destino_original -> lista de candidatos
    por_destino = {}
    todos = []
    for d in destinos:
        cands = _candidatos_destino(d)
        if not cands:
            continue
        por_destino[d] = cands
        todos.extend(cands)
    if not todos:
        return {}

    # candidato (sólo dígitos) -> {'fecha': ..., 'detalle': ...} (el más reciente)
    cand_info = {}
    try:
        cursor = connection.cursor()
        unicos = list(dict.fromkeys(todos))
        CHUNK = 500  # margen bajo el límite de 1000 elementos del IN de Oracle
        for ini in range(0, len(unicos), CHUNK):
            lote = unicos[ini:ini + CHUNK]
            ph, binds = [], {}
            for i, c in enumerate(lote):
                key = f"d{i}"
                ph.append(':' + key)
                binds[key] = c
            binds['tipo'] = tipo_notificacion
            sql = ("SELECT id_notificacion, fecha_adicion, destino, detalle_estado "
                   "FROM PA.NOTIFICACIONES_CLIENTES "
                   "WHERE DESTINO IN (" + ",".join(ph) + ") "
                   "AND TIPO_NOTIFICACION = :tipo "
                   "AND ESTADO_NOTIFICACION = 2 "
                   "ORDER BY FECHA_ADICION DESC")
            cursor.execute(sql, binds)
            for row in cursor.fetchall():
                destino_db = re.sub(r"\D", "", str(row[1 + 1] or ""))
                if not destino_db or destino_db in cand_info:
                    continue  # ya guardamos la más reciente para este candidato
                cand_info[destino_db] = {
                    'fecha': row[1],
                    'detalle': _parse_detalle_lob(row[3]),
                }
    except Exception as e:
        loge(f"buscar_notificaciones_por_destinos: error: {e}")
        return {}

    # resolver, por cada destino original, el candidato con la notif más reciente
    result = {}
    for d, cands in por_destino.items():
        best = None
        for c in cands:
            info = cand_info.get(c)
            if info is None:
                continue
            if best is None or (info['fecha'] is not None and
                                (best['fecha'] is None or info['fecha'] > best['fecha'])):
                best = info
        if best is not None:
            result[d] = best['detalle']
    logg(f"buscar_notificaciones_por_destinos: destinos={len(por_destino)} "
         f"con_notif={len(result)} lotes={(len(list(dict.fromkeys(todos)))+499)//500}")
    return result


def buscar_notificaciones_por_destino(destino, tipo_notificacion=2, limit=5):
    """Busca en PA.NOTIFICACIONES_CLIENTES notificaciones enviadas al destino.

    Normaliza el número (quita caracteres no numéricos) y consulta la tabla
    retornando hasta `limit` registros ordenados por fecha más reciente.

    Retorna lista de dicts: {"id": ..., "fecha_envio": ..., "detalle_raw": ..., "detalle": parsed_or_str}
    """
    try:
        candidates = _candidatos_destino(destino)
        if not candidates:
            return []

        cursor = connection.cursor()
        # construir placeholders dinámicos
        ph = []
        binds = {}
        for i, c in enumerate(candidates):
            key = f"d{i}"
            ph.append(':' + key)
            binds[key] = c
        binds['tipo'] = tipo_notificacion

        sql = ("SELECT id_notificacion, NVL(fecha_adicion, NULL) AS fecha_envio, detalle_estado "
               "FROM PA.NOTIFICACIONES_CLIENTES "
               "WHERE DESTINO IN (" + ",".join(ph) + ") "
               "AND TIPO_NOTIFICACION = :tipo "
               "AND ESTADO_NOTIFICACION = 2 " # solo notificaciones enviadas
               "ORDER BY FECHA_ADICION DESC")

        cursor.execute(sql, binds)
        rows = cursor.fetchmany(limit)
        out = []
        for row in rows:
            _id = row[0]
            fecha = row[1]
            detalle_raw = row[2]
            # Si es LOB, leer
            try:
                if hasattr(detalle_raw, 'read'):
                    detalle_s = detalle_raw.read()
                else:
                    detalle_s = detalle_raw
            except Exception:
                detalle_s = detalle_raw

            parsed = None
            try:
                if isinstance(detalle_s, (bytes, bytearray)):
                    detalle_s = detalle_s.decode('utf-8', errors='ignore')
                if isinstance(detalle_s, str) and detalle_s.strip():
                    parsed = json.loads(detalle_s)
            except Exception:
                parsed = None

            out.append({
                'id': _id,
                'fecha_envio': fecha.isoformat() if getattr(fecha, 'isoformat', None) else str(fecha),
                'detalle_raw': detalle_s,
                'detalle': parsed or detalle_s
            })
        logg(f"buscar_notificaciones_por_destino: destino={destino} candidates={candidates} found={len(out)}")
        return out
    except Exception as e:
        loge(f"buscar_notificaciones_por_destino: error buscando notificaciones: {e}")
        return []

def resumen_agencias(xml_str):
    if not xml_str:
        return ""
    tree = ET.fromstring(xml_str)
    resumen = []
    for agencia in tree.findall("AGENCIA"):
        sucursal = agencia.findtext("DESCRIPCION")
        resumen.append(sucursal)
    x = len(resumen)
    resumen.append("Oficina de representación: Sánchez Worldwide Multiservices, Ubicación: 496 West 159th Street, Bet. Amsterdam & Saint Nicholas, New York, NY 10032, Teléfonos: 347-573-9501, 212-923-1193. Extensión 1080, País: Estados Unidos de Norteamérica")    
    resumen.append(f"En total Vega Real tiene {x} sucursales y una oficina de representación")
    return "\n".join(resumen)

def _clasificar_producto_cuenta(descripcion):
    """Determina si una DESCRIPCION_PRODUCTO corresponde a 'certificado' o 'cuenta'."""
    d = (descripcion or "").lower()
    if "certificado" in d or "plazo fijo" in d or "deposito a plazo" in d or "depósito a plazo" in d:
        return "certificado"
    return "cuenta"

def resumen_cuentas(xml_str, entidad):
    if not xml_str:
        return ""
    tree = ET.fromstring(xml_str)
    resumen = []
    for cuenta in tree.findall("CUENTA"):
        producto = cuenta.findtext("DESCRIPCION_PRODUCTO")
        saldo = cuenta.findtext("SALDO_TOTAL")
        estado = cuenta.findtext("ESTADO_CUENTA")
        numero = cuenta.findtext("NUM_CUENTA")
        fecha_apertura = cuenta.findtext("FECHA_APERTURA")
        cliente  = cuenta.findtext("COD_CLIENTE")
        datos_cliente = buscar_cliente(cliente)
        if estado != "Inactiva":
            logg(f"resumen_cuentas: Verificando '{entidad}' -> '{producto}'")
            prod = producto.lower().strip().split(" ")
            if any(entidad in palabra for palabra in prod) or entidad in ("cuentas", "certificados"):
                subtipo = _clasificar_producto_cuenta(producto)
                logg(f"resumen_cuentas: OK '{entidad}' -> {producto} (subtipo={subtipo})")
                result = {
                    "tipo": "producto", "subtipo": subtipo, "moneda": "RD$", "descripcion_moneda": "Pesos", "codigo_moneda": "DOP",
                    "numero_producto": enmascarar_pci(numero),
                    "fecha_apertura": fecha_apertura,
                    "estado": estado,
                    "saldo_total": float(saldo),
                    "saldo_formateado" : moneda(float(saldo)),
                    "descripcion": producto,
                    "nombre_asociado" : datos_cliente["nombres"]
                }
                resumen.append(result)
    return resumen

def resumen_creditos(xml_str, entidad):
    if not xml_str:
        return ""
    tree = ET.fromstring(xml_str)
    resumen = []
    for credito in tree.findall("CREDITO"):
        if credito.findtext("ESTADO") != 'C':
            no_credito = credito.findtext("NO_CREDITO")
            cliente  = credito.findtext("CODIGO_CLIENTE")
            producto = credito.findtext("TIPO_DE_CREDITO")
            logg(f"resumen_creditos: Verificando '{entidad}' -> '{producto}'")
            prod = producto.lower().strip().split(" ")
            if any(entidad in palabra for palabra in prod) or entidad == "prestamos":
                logg(f"resumen_creditos: OK '{entidad}' -> {producto}")            
                resumen.append(consulta_prestamo(cliente, no_credito))
    return resumen

def resumen_feria(xml_str, entidad):
    #logg(f"resumen_feria: '{entidad}': \n {xml_str}")
    if not xml_str:
        return ""
    tree = ET.fromstring(xml_str)
    resumen = []
    for articulos in tree.findall("ARTICULO"):
        cliente  = articulos.findtext("COD_CLIENTE")
        numero_producto  = articulos.findtext("COD_ART")
        articulo = articulos.findtext("DESCRIPCION")
        cantidad = articulos.findtext("CANTIDAD_ARTICULO")
        estado = articulos.findtext("ESTADO_ARTICULO")
        suplidor = articulos.findtext("SUPLIDOR")
        fecha_entrega = articulos.findtext("FECHA_ENTREGA")
        fecha_depachado = articulos.findtext("FECHA_DESPACHADO")
        if not fecha_depachado:
            fecha_depachado = "Sin fecha programada"
        if not fecha_entrega:
            fecha_entrega = "Sin fecha programada"
        datos_cliente = buscar_cliente(cliente)
        if articulo:
            logg(f"resumen_feria: Verificando '{entidad}' -> '{articulo}'")
            art = articulo.lower().strip().split(" ")
            if any(entidad in palabra for palabra in art) or entidad == "articulos":
                logg(f"resumen_feria: OK '{entidad}' -> {articulo}")            
                result = {
                    "tipo": "articulo", "subtipo": "prestamo_feria", 
                    "numero_producto": numero_producto,
                    "codigo_articulo": numero_producto,
                    "suplidor": suplidor,
                    "fecha_entrega": fecha_entrega,
                    "fecha_depachado" : fecha_depachado,
                    "descripcion_articulo": articulo,
                    "estado_articulo": estado,
                    "cantidad_articulo": cantidad,                
                    "nombre_asociado" : datos_cliente["nombres"]
                }
                resumen.append(result)
    if not resumen:
        # Intentar obtener el cliente desde el XML si está disponible
        cliente_id = tree.findtext('.//COD_CLIENTE')
        if cliente_id:
            try:
                datos_cliente = buscar_cliente(cliente_id)
            except Exception:
                datos_cliente = {"nombres": ""}
        else:
            datos_cliente = {"nombres": ""}

        result = {
                    "tipo": "articulo", "subtipo": "prestamo_feria", 
                    "numero_producto": "0",
                    "codigo_articulo": "Ninguno",
                    "suplidor": "",
                    "fecha_entrega": "",
                    "fecha_depachado" : "",
                    "descripcion_articulo": "Ninguno",
                    "estado_articulo": "Ninguno",
                    "cantidad_articulo": 0,                
                    "nombre_asociado" : datos_cliente.get("nombres", "")
                }
        resumen.append(result)
    return resumen

def resumen_personal(xml_str):
    if not xml_str:
        return ""
    tree = ET.fromstring(xml_str)
    cliente = tree.find("CLIENTE")
    if cliente is None:
        return ""
    nombre = " ".join([
        cliente.findtext("PRIMER_NOMBRE", ""),
        cliente.findtext("SEGUNDO_NOMBRE", ""),
        cliente.findtext("PRIMER_APELLIDO", ""),
        cliente.findtext("SEGUNDO_APELLIDO", "")
    ])
    cargo = cliente.findtext("CARGO", "")
    ingreso = cliente.findtext("INGRESO_MENSUAL", "0")
    empresa = cliente.findtext("NOM_EMPRESA", "")
    return f"El asociado {nombre.strip()} trabaja como {cargo} en {empresa} y tiene un ingreso mensual de RD${ingreso}."

def contexto_agencias():
    inicio = time.time()
    logg(f"Iniciando el contexto para las sucursales...")
    datos = []
    datos.append(resumen_agencias(ejecuta("Agencia", AGENCIAS)))
    logg("Listo!. Tiempo de procesamiento de sucursales: " + fin(inicio) + " segundos")
    return "".join(datos)

def procesar_productos(datos_originales: List[List[Dict]]) -> List[Dict]:
    # Aplanar la estructura anidada
    productos_planos = [producto for sublista in datos_originales for producto in sublista]
    
    # Eliminar duplicados (basado en numero_producto)
    productos_unicos = {}
    for producto in productos_planos:
        num_producto = producto['numero_producto'] 
        if num_producto not in productos_unicos:
            productos_unicos[num_producto] = producto
    JSONprods = json.dumps(list(productos_unicos.values()), ensure_ascii=False, indent=2)
    return JSONprods

def contexto_cliente(cliente, query):
    inicio = time.time()
    logg(f"contexto_cliente: Iniciando el contexto\n{query}\nPara el cliente {cliente}...")
    datos = []
    if len(query["entity"]) > 0:
        for entity in query["entity"]:
        #entity = query["entity"][0]
            subtipo = entity["subtipo"]
            entidad = subtipo.replace("_asociado", "")
            producto = entity["valor"]
            logg(f"contexto_cliente: {entidad} {producto}")
            if entidad == "personal":
                logg("Consultando datos personales..")
                personales = resumen_personal(ejecuta("Cliente", CLIENTES, cliente))
                if personales:
                    datos.append("Información personal: " + personales)
            
            elif entidad == "cuenta":
                logg("Consultando datos cuentas..")
                cuentas = resumen_cuentas(ejecuta("Cuenta", CUENTAS,  cliente), producto)
                if cuentas:
                    datos.append(cuentas)
            elif entidad == "prestamo":
                logg("Consultando datos préstamos..")
                creditos = resumen_creditos(ejecuta("Credito", CREDITOS, cliente), producto)
                if creditos:
                    datos.append(creditos)
            elif entidad == "prestamo_feria" or  entidad == "articulo_feria":
                logg("Consultando datos feria..")
                articulos = resumen_feria(ejecuta("Articulo", ARTICULOS_FERIA, cliente), producto)
                #if cliente == "37710":
                #    articulos = resumen_feria(ejecuta("Articulo", ARTICULOS_FERIA, "111930"), producto)
                #else:
                #    articulos = resumen_feria(ejecuta("Articulo", ARTICULOS_FERIA, cliente), producto)
                if articulos:
                    datos.append(articulos)
        
            #elif entidad == "certificado":
            #   logg("Consultando datos certificados..")
            #   certificados = ejecuta("Certificado", CERTIFICADOS, cliente)
            #   if certificados:
            #        creditos = resumen_creditos(ejecuta("Certificados", CERTIFICADOS, cliente), producto)
            #            if creditos:
            #                datos.append(creditos)
    logg(f"Listo!. Tiempo de procesamiento de cliente: {fin(inicio)} segundos")
    return procesar_productos(datos)

def validar_cedula(cedula):
    """
    Valida una cédula dominicana según el algoritmo de la JCE
    Args:
        cedula (str): Número de cédula a validar (puede contener guiones o espacios)    
    Returns:
        tuple: (bool, str) (True/False, mensaje de error/exito)
    """
    try:
        
        # Limpiar la cédula (eliminar guiones, espacios)
        cedula = cedula.replace("-", "").replace(" ", "").strip()
        
        # Validaciones básicas
        if not cedula.isdigit():
            return False, "La cédula debe contener solo números", None
        
        if len(cedula) != 11:
            return False, "La cédula debe tener 11 dígitos", None
        
        # La cédula debe tener 11 dígitos
        if len(cedula)== 11:
            if (int(cedula[0:3]) < 122 and int(cedula[0:3]) > 0 or int(cedula[0:3]) == 402):
                suma = 0
                mutliplicador = 1
                verificador = 0
                for i in range(10):
                    # Se multiplica cada dígito por su paridad
                    multiplicador = 1 if i % 2 == 0 else 2
                    parte = int(cedula[i])
                    digito = parte * multiplicador
                    # Si la multiplicación da de dos dígitos, se suman entre sí
                    if(digito>9):
                        digito = digito//10 + digito%10
                    # Y se va haciendo la acumulación de esa suma
                    suma = suma + digito
                # Al final se obtiene el verificador con la siguiente fórmula
                verificador = (10 - (suma % 10) ) % 10
                # Se comprueba que coincidan
                if(verificador == int(cedula[10]) ):
                    return True, "Cédula válida", cedula
                # El dígito verificador no es válido
                else:
                    return False, f"Dígito verificador {verificador} inválido", None
            # La serie no es válida
            else:
                return False, "Serie inválida", None
    except Exception as e:
        return False, f"Error al validar: {str(e)}"
