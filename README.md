# Protótipo LEAS: container gateway de rede, com Kea DHCP e firewall nftables

Este protótipo sobe um container `gw` com duas interfaces:

- `wan`: rede Docker bridge comum, com saída para internet pelo host;
- `lan`: rede Docker bridge `internal`, isolada, onde o `gw` usa IP fixo `10.88.0.1`;
- `kea-dhcp4`: entrega IPs na LAN, por padrão de `10.88.0.100` a `10.88.0.200`;
- `kea-ctrl-agent`: expõe API REST do Kea na porta `8000` do container, publicada no host como `18000`;
- `gwapi`: API simples para manipular firewall `nftables`, na porta `8080` do container, publicada no host como `18080`.

> [!NOTE]
> Observação importante: Docker bridge não usa DHCP para endereçar containers. Por isso os clientes deste laboratório iniciam com IP temporário do IPAM Docker, removem esse IP e executam `dhclient` para obter lease real do Kea. Para evitar colisão, o `ip_range` da LAN Docker fica em `10.88.0.240/28`, enquanto o pool Kea fica em `10.88.0.100-10.88.0.200`.

>[!TIP]
> Essas informações de rede poderão ser facilmente reconfiguradas executando `python3 reconfigure.py`

## Estrutura

```text
gw-kea-nftables/
├── docker-compose.yml
├── gateway/
│   ├── Dockerfile
│   ├── gwapi.py
│   └── start-gateway.sh
└── client/               # Apenas para exemplificar o funcionamento
    ├── Dockerfile        # Apenas para exemplificar o funcionamento
    └── start-client.sh   # Apenas para exemplificar o funcionamento
```

## Arquitetura lógica

```text
Internet/Host
    |
    | rede Docker wan
    |
+-------------------+
| gw                |
|-------------------|
| wan: DHCP Docker  |
| lan: 10.88.0.1    |
|                   |
| NAT nftables      |
| firewall nftables |
| Kea DHCPv4        |
| Kea Ctrl Agent    |
| gwapi             |
+-------------------+
    |
    | rede Docker lan internal
    |
+-------------------+       +-------------------+
| client1           |       | client2           |
| DHCP via Kea      |       | DHCP via Kea      |
+-------------------+       +-------------------+
```

## Ambiente de testes e desenvolvimento:
- Kubuntu 24.04 LTS
- AMD Ryzen 5 5600X 6-Core Processor
- 32GB de memória RAM DDR4
- Armazenamento NVMe
- Docker v29.4

## Requisitos básicos:
Pacotes: `git`, `jq`, `curl` e `docker` (instalado conforme [documentação oficial](https://docs.docker.com/engine/install/ubuntu/)) .
```
sudo apt update
sudo apt install git jq curl -y
```

## Clonar o repositório e entrar no diretório

```bash
git clone git@github.com:GT-IoTEdu/gw-kea-nftables.git
cd gw-kea-nftables || exit 1
```

## Reconfigurar os endereços envolvidos na WAN/LAN/DHCP (opcional, a configuração atual é):
```text
# Endereço do container gateway na LAN. Também será anunciado pelo DHCP como gateway dos clientes.
LAN_IP=10.88.0.1

# Rede LAN dos containers.
LAN_CIDR=10.88.0.0/24

# Gateway interno da bridge Docker. Deve estar na LAN, mas não deve ser igual ao LAN_IP.
LAN_DOCKER_GATEWAY=10.88.0.254

# Faixa usada pelo IPAM do Docker para IPs temporários dos containers. Deve ficar fora do pool DHCP do Kea para evitar colisão.
LAN_DOCKER_IP_RANGE=10.88.0.240/28

# Pool DHCP entregue pelo Kea aos clientes da LAN.
DHCP_POOL_START=10.88.0.100
DHCP_POOL_END=10.88.0.200

# DNS entregue por DHCP. Lista separada por vírgula.
DHCP_DNS=1.1.1.1, 9.9.9.9

# Domínio entregue pelo DHCP aos clientess.
DHCP_DOMAIN=lab.local

# Portas internas dos serviços no container Gateway.
FW_API_PORT=8080
KEA_CA_PORT=8000

# Portas publicadas no host.
FW_API_HOST_PORT=18080
KEA_CA_HOST_PORT=18000
```

### Caso queira modificar algum desses valores, use o formulário automatizado e siga as perguntas do prompt:
```bash
python3 reconfigure.py
```

## Para subir esse "protótipo"

```bash
docker compose up --build
```

--- 

# Daqui para baixo é informação para quem for abraçar o desenvolvimento

## Portas publicadas no host

| Serviço | URL no host | Uso |
|---|---:|---|
| Firewall API / `gwapi` | `http://localhost:18080` | Manipulação de política e regras de firewall |
| Kea Control Agent | `http://localhost:18000` | Controle direto do Kea DHCPv4 |

## API do firewall

Ver se a API está rodando:

```bash
curl -s http://localhost:18080/health | jq
```

Ver política de firewall atual:

```bash
curl -s http://localhost:18080/firewall | jq
```

Ver ruleset efetivo no `nftables`:

```bash
docker exec -it gw nft list ruleset
```

Por padrão, a política LAN -> WAN é `drop`, com regras liberando DNS, HTTP, HTTPS e ICMP.

### Adicionar uma regra para permitir SSH de saída

```bash
curl -s -X POST http://localhost:18080/firewall/rules \
  -H 'Content-Type: application/json' \
  -d '{
        "id": "allow-ssh",
        "action": "allow",
        "proto": "tcp",
        "dport": 22,
        "description": "Permite SSH de saída"
      }' | jq
```

### Remover a regra de SSH (por nome)

```bash
curl -s -X DELETE http://localhost:18080/firewall/rules/allow-ssh | jq
```

### Mudar política default para permitir tudo (apenas demonstração, não fazer isso obviamente)

```bash
curl -s -X PUT http://localhost:18080/firewall/default \
  -H 'Content-Type: application/json' \
  -d '{"policy":"allow"}' | jq
```

### Mudar política default para bloquear tudo que não esteja explicitamente liberado

```bash
curl -s -X PUT http://localhost:18080/firewall/default \
  -H 'Content-Type: application/json' \
  -d '{"policy":"drop"}' | jq
```

## Exemplos um pouco mais complecos do firewall

- `src`: endereço ou rede de origem, por exemplo `10.88.0.200/32`;
- `position`: posição de inserção da regra, por exemplo `first` ou `last`.


```text
ip saddr 10.88.0.200/32 drop
```

Além disso, como já existem regras liberando DNS, HTTP, HTTPS e ICMP, a regra de bloqueio precisa ser inserida no topo da cadeia, antes das permissões existentes.

### Inserir regra que bloqueia por completo o tráfego do cliente `10.88.0.200`

```bash
curl -s -X POST http://localhost:18080/firewall/rules \
  -H 'Content-Type: application/json' \
  -d '{
        "id": "drop-client-10-88-0-200",
        "position": "first",
        "action": "drop",
        "src": "10.88.0.200/32",
        "proto": "all",
        "description": "Bloqueia completamente o cliente 10.88.0.200 para a internet"
      }' | jq
```

Verificar no firewall:

```bash
docker exec -it gw nft list ruleset
```

A regra deve aparecer antes das regras permissivas, como `allow-dns`, `allow-http`, `allow-https` e `allow-icmp`.

### Remover a regra anterior, se ela existir

```bash
curl -s -X DELETE http://localhost:18080/firewall/rules/drop-client-10-88-0-200 | jq
```

Versão que trata `404` como “não havia regra para remover”:

```bash
curl -s -X DELETE http://localhost:18080/firewall/rules/drop-client-10-88-0-200 \
  | jq 'if .error == "regra não encontrada" then {removed:false, reason:.error} else {removed:true} end'
```
---

## API do DHCP/Kea

O Kea Control Agent fica publicado diretamente em `localhost:18000`.

Status do DHCPv4:

```bash
curl -s -X POST http://localhost:18000/ \
  -H 'Content-Type: application/json' \
  -d '{"command":"status-get", "service":["dhcp4"]}' | jq
```

Configuração ativa:

```bash
curl -s -X POST http://localhost:18000/ \
  -H 'Content-Type: application/json' \
  -d '{"command":"config-get", "service":["dhcp4"]}' | jq
```

A API do firewall também inclui um proxy simples para o Kea:

```bash
curl -s http://localhost:18080/dhcp/status | jq
curl -s http://localhost:18080/dhcp/config | jq

curl -s -X POST http://localhost:18080/dhcp/kea \
  -H 'Content-Type: application/json' \
  -d '{"command":"status-get", "service":["dhcp4"]}' | jq
```

## Exemplos de reservas DHCP no Kea

Os exemplos abaixo manipulam a configuração ativa do Kea usando:

1. `config-get`, para buscar a configuração atual;
2. `jq`, para alterar somente a lista de reservas da subnet desejada;
3. `config-set`, para aplicar a configuração alterada.

No protótipo, a subnet LAN possui `id: 1` e rede `10.88.0.0/24`.

### Criar reserva do MAC `aa:bb:cc:dd:ee:ff` para o IP `10.88.0.111`
> [!WARNING]
> É importante haver um tratamento mínimo para evitar ficar tentando incluir/remover coisas do KEA em redes ou reservations que não existe.


```bash
#!/usr/bin/env bash
KEA_API="http://localhost:18000/"
MAC="aa:bb:cc:dd:ee:ff"
IP="10.88.0.111"
SUBNET_ID="1"

tmp="$(mktemp)"

curl -s -X POST "$KEA_API" \
  -H 'Content-Type: application/json' \
  -d '{"command":"config-get", "service":["dhcp4"]}' \
| jq --arg mac "$MAC" --arg ip "$IP" --argjson subnet_id "$SUBNET_ID" '
    .[0].arguments.Dhcp4
    | .subnet4 |= map(
        if .id == $subnet_id then
          .reservations = (
            (.reservations // [])
            | map(select(.["ip-address"] != $ip and .["hw-address"] != $mac))
            + [
                {
                  "hw-address": $mac,
                  "ip-address": $ip
                }
              ]
          )
        else
          .
        end
      )
    | {
        command: "config-set",
        service: ["dhcp4"],
        arguments: {
          Dhcp4: .
        }
      }
  ' > "$tmp"

curl -s -X POST "$KEA_API" \
  -H 'Content-Type: application/json' \
  --data-binary @"$tmp" | jq

rm -f "$tmp"
```

Verificar se a reserva foi criada:

```bash
#!/usr/bin/env bash
curl -s -X POST http://localhost:18000/ \
  -H 'Content-Type: application/json' \
  -d '{"command":"config-get", "service":["dhcp4"]}' \
| jq '.[0].arguments.Dhcp4.subnet4[] | select(.id == 1) | .reservations'
```

### Remover reserva por IP, se ela existir

Exemplo removendo qualquer reserva associada ao IP `10.88.0.111`:

```bash
#!/usr/bin/env bash
KEA_API="http://localhost:18000/"
IP="10.88.0.111"
SUBNET_ID="1"

tmp="$(mktemp)"

curl -s -X POST "$KEA_API" \
  -H 'Content-Type: application/json' \
  -d '{"command":"config-get", "service":["dhcp4"]}' \
| jq --arg ip "$IP" --argjson subnet_id "$SUBNET_ID" '
    .[0].arguments.Dhcp4
    | .subnet4 |= map(
        if .id == $subnet_id then
          .reservations = (
            (.reservations // [])
            | map(select(.["ip-address"] != $ip))
          )
        else
          .
        end
      )
    | {
        command: "config-set",
        service: ["dhcp4"],
        arguments: {
          Dhcp4: .
        }
      }
  ' > "$tmp"

curl -s -X POST "$KEA_API" \
  -H 'Content-Type: application/json' \
  --data-binary @"$tmp" | jq

rm -f "$tmp"
```

Verificar novamente:

```bash
curl -s -X POST http://localhost:18000/ \
  -H 'Content-Type: application/json' \
  -d '{"command":"config-get", "service":["dhcp4"]}' \
| jq '.[0].arguments.Dhcp4.subnet4[] | select(.id == 1) | .reservations'
```

### Observação sobre leases já ativos

Remover uma reserva não necessariamente derruba um lease já entregue. Se o cliente já recebeu `10.88.0.111`, ele pode continuar usando o IP até renovar, reiniciar ou liberar manualmente o lease.

> [!NOTE]
> Se uma reserva foi feita e o cliente está usando o IP, e enquanto o lease estiver ativo for feita uma modificação no IP ou MAC da reserva, ela só será assimilada pelo cliente se ele forçar o DHCP Client (dele) a buscar nova atribuição.

Para forçar renovação em laboratório:

```bash
docker exec -it client1 dhclient -r eth0
docker exec -it client1 dhclient -v eth0
```

Ou recrie/reinicie o cliente:

```bash
docker compose restart client1
```

## Alterar o pool DHCP

> [!WARNING]
> Sempre que modificações de estrutura (rede, pool, etc) form feitas no KEA, **é imperativo rebuildar o container**.

Depois recrie o ambiente:

```bash
docker compose down -v
docker compose up --build
```

## Persistência das alterações:
Como dito desde o início nas reuniões, o papel de persistência é do `BACKEND`. Caso o container do dhcp, que é efêmero, caia/trave/morra, cabe ao backend, que tem as reservas registradas em banco, refazer as liberações do firewall e recriação de reservations no DHCP.

## O que ainda não foi feito:
1. Restringir o acesso às portas `18000` e `18080` por IP de origem ou colocar autenticação/reverse proxy.
2. Remover `privileged: true` e substituir por capacidades mínimas, como `NET_ADMIN` e `NET_RAW`, após validar no host alvo.
3. Persistir `/var/lib/kea`, `/etc/kea` e `/etc/gwapi` em volumes nomeados. (Mesmo que não seja obrigação da aplicação manter os estados, não custa ter um backup próprio)
4. Criar endpoints específicos para reservas DHCP, alteração de pool e listagem de leases, em vez de usar o proxy bruto para o Kea.
5. Adicionar autenticação e autorização na API de firewall antes de usar fora de ambiente de teste. No momento, dada a correria, nada de segurança foi implementado.
