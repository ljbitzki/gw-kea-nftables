FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN  apt update && \
     apt install --no-install-recommends ca-certificates curl dnsutils iproute2 iputils-ping isc-dhcp-client -y && \
     rm -rf /var/lib/apt/lists/*

COPY start-client.sh /usr/local/bin/start-client.sh
RUN chmod +x /usr/local/bin/start-client.sh

ENTRYPOINT ["/usr/local/bin/start-client.sh"]
