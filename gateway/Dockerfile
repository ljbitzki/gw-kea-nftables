FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN  apt update && \
     apt install --no-install-recommends ca-certificates curl iproute2 iputils-ping jq kea net-tools nftables procps python3 python3-flask -y && \
     rm -rf /var/lib/apt/lists/*

COPY start-gateway.sh /usr/local/bin/start-gateway.sh
COPY gwapi.py /opt/gwapi/app.py

RUN chmod +x /usr/local/bin/start-gateway.sh

EXPOSE 67/udp 8000/tcp 8080/tcp

ENTRYPOINT ["/usr/local/bin/start-gateway.sh"]
