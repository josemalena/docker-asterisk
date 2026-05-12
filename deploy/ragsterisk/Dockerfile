# Imagen base con Python y Debian
FROM python:3.12-slim

# Variables para evitar prompts en apt
ENV DEBIAN_FRONTEND=noninteractive

# Zona horaria
ENV TZ=America/Santo_Domingo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Instala el certificado SSL del CA interno para evitar errores descargando paquetes
COPY CAcert.crt /tmp/CAcert.crt
RUN  cat /tmp/CAcert.crt >> /etc/ssl/certs/ca-certificates.crt

# Instala dependencias de sistema necesarias para Asterisk + Whisper
RUN apt update && apt install -y \
    git \
    curl \
    wget \
    build-essential \
    ffmpeg \
    libffi-dev \
    libssl-dev \
    libncurses5-dev \
    libxml2-dev \
    libsqlite3-dev \
    uuid-dev \
    libjansson-dev \
    libedit-dev \
    libpq-dev \
    libvorbis-dev \
    libopus-dev \
    libcurl4-openssl-dev \
    subversion \
    automake \
    libtool \
    pkg-config \
    yasm \
    net-tools \
    iputils-ping \
    && apt clean


# Instala Asterisk desde fuente
WORKDIR /usr/src
COPY libcap-dev_2.66-4_amd64.deb /usr/src
RUN curl -s -O http://downloads.asterisk.org/pub/telephony/asterisk/asterisk-20-current.tar.gz && \
    tar -xzvf asterisk-20-current.tar.gz && \
    rm asterisk-20-current.tar.gz && \
    dpkg -i libcap-dev_2.66-4_amd64.deb && \
    cd asterisk-* && \
    contrib/scripts/install_prereq install && \
    ./configure && \
    make -j$(nproc) && \
    make install && \
    make samples && \
    make config && \
    ldconfig

# Crear usuario de ejecución
RUN useradd -m asterisk && \
    mkdir -p /opt/agi/app && \
    chown asterisk:asterisk -R /opt/agi && \
    mkdir -p /var/run/asterisk /var/log/asterisk /var/lib/asterisk /var/lib/asterisk/sounds/custom && \
    chown -R asterisk:asterisk /var/run/asterisk /var/log/asterisk /var/lib/asterisk /var/lib/asterisk/sounds/custom && \
    chmod -R 775 /var/run/asterisk /var/log/asterisk /var/lib/asterisk

USER asterisk

# Directorio de trabajo para AGI scripts
WORKDIR /var/lib/asterisk/agi-bin/

# Puerto por defecto para Asterisk
EXPOSE 5060/udp
EXPOSE 5038/tcp
EXPOSE 8088/tcp
EXPOSE 10000-20000/udp

# Configuracion inicial
#COPY sound /var/lib/asterisk/sounds/custom
COPY config /etc/asterisk
COPY app/rag_agi.py /var/lib/asterisk/agi-bin/app/
COPY app/requirements.txt /opt/agi/app

RUN python -m venv /opt/agi/app && \
    cd /opt/agi/app/bin/ && \
    ./pip install --upgrade pip && \
    # Instala PyTorch compatible con CPU (sin GPU)
    ./pip install torch torchvision torchaudio numpy tqdm --index-url https://download.pytorch.org/whl/cpu && \
    # Instala Whisper directamente desde GitHub (sin triton)
    ./pip install git+https://github.com/openai/whisper.git && \    
    # Instala requerimientos de rag_agi.py
    ./pip install --upgrade --force-reinstall pyst2
    #./pip install -r ../requirements.txt

# Ejecuta asterisk

CMD ["/usr/sbin/asterisk", "-f", "-U", "asterisk"]