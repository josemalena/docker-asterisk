#   curl --ntlm -u 'VEGAREAL\jamalena' "http://cvrsvr0052.vegareal.local/certsrv/certnew.cer?ReqID=CACert&Renewal=0&Enc=b64" -o CAcert.crt
#   docker build --no-cache -t ragapi:1.01 .
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
EXPOSE 8000
# Zona horaria
ENV TZ=America/Santo_Domingo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Descargar el certificado CA desde el servidor CA 0052
COPY CAcert.crt /tmp/
# Cliente oracle
COPY instantclient_19_26 /opt/instantclient_19_26
# Proyecto Python
COPY app opt/rag/
RUN ldconfig && \
    cd /opt && \
    apt-get update -y && \
    apt install -y ca-certificates locales curl libaio1&& \    
    sed -i '/es_DO.UTF-8/s/^# //g' /etc/locale.gen && \
    locale-gen  && \
    python -m venv rag && \
    rag/bin/python -m pip install --upgrade pip && \
    rag/bin/pip install oracledb redis flask flask_session pywebpush && \ 
    rm -rf /var/lib/apt/lists/*

    # rag/bin/pip install sentence-transformers faiss-cpu langchain-ollama 
# Instalar el certificado
RUN cp /tmp/CAcert.crt /usr/local/share/ca-certificates/CAcert.crt && \
    chmod 644 /usr/local/share/ca-certificates/CAcert.crt && \
    update-ca-certificates
COPY startup.sh /usr/local/bin/startup.sh
RUN chmod +x /usr/local/bin/startup.sh
ENV LD_LIBRARY_PATH=/opt/instantclient_19_26:$LD_LIBRARY_PATH
CMD ["/usr/local/bin/startup.sh"]