#!/bin/bash
if [ -f /tmp/CAcert.crt ]; then
    cp /tmp/CAcert.crt /usr/local/share/ca-certificates/CAcert.crt
    chmod 644 /usr/local/share/ca-certificates/CAcert.crt
    update-ca-certificates
fi

/opt/rag/bin/python /opt/rag/app/api_llm.py