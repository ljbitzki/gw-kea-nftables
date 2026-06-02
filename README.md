# Protótipo LEAS: gateway de rede em container com Kea DHCP e firewall nftables

Este repositório contém o artefato associado ao artigo "Protótipo LEAS: gateway de rede em container com Kea DHCP e firewall nftables". O artefato implementa um laboratório reprodutível em Docker Compose no qual um container `gw` atua como gateway entre uma rede WAN e uma rede LAN isolada, oferecendo DHCPv4 com Kea, NAT, filtragem com `nftables` e uma API/interface web para administrar regras de firewall e reservas DHCP.

O objetivo do artefato é demonstrar que uma infraestrutura de laboratório pode provisionar clientes em uma LAN isolada por DHCP, encaminhar o tráfego desses clientes por um gateway controlado e aplicar políticas de firewall e reservas DHCP dinamicamente por uma API administrativa. O ambiente é autocontido: não requer nuvem, chaves privadas, equipamentos físicos externos ou bases de dados de terceiros.

A demonstração base é totalmente local, onde a rede, o container gateway e os contêineres clientes são elementos na mesma máquina. A aplicação do artefato em cenários de uso realístico pode ser acessada em [TOPOLOGIAS-DE-IMPLANTACAO.md](TOPOLOGIAS-DE-IMPLANTACAO.md).

## Estrutura do README.md

Este README está organizado para atender aos requisitos mínimos de avaliação de artefatos do SBRC 2026:

- **Selos Considerados**: lista os selos pretendidos para avaliação.
- **Informações básicas**: descreve a arquitetura, o ambiente de execução e a organização do repositório.
- **Dependências**: apresenta os pacotes, versões e componentes necessários.
- **Preocupações com segurança**: indica riscos e cuidados para executar o artefato.
- **Instalação**: mostra como obter, configurar e iniciar o ambiente.
- **Teste mínimo**: fornece uma execução curta para validar a instalação.
- **Experimentos**: descreve como reproduzir as principais reivindicações do artigo.
- **[LICENSE](LICENSE)**: informa a licença do artefato.

### Estrutura do repositório

```text
gw-kea-nftables/
├── docker-compose.yml          # Orquestra gateway, clientes e observabilidade opcional
├── reconfigure.py              # Assistente para alterar rede, pool DHCP e portas publicadas
├── .env.example                # Exemplo de configuração do ambiente
├── TOPOLOGIAS-DE-IMPLANTACAO.md # Cenários físicos com duas NICs ou VLANs
├── LICENSE                     # Licença BSD 3-Clause
├── gateway/
│   ├── Dockerfile              # Imagem do gateway
│   ├── start-gateway.sh        # Inicializa Kea, Kea Control Agent, nftables e gwapi
│   ├── gwapi.py                # Ponto de entrada da API Flask
│   └── gwapi_app/
│       ├── auth.py             # Autenticação por sessão web e HTTP Basic Auth
│       ├── config.py           # Configuração por variáveis de ambiente
│       ├── firewall.py         # Estado, validação e aplicação de regras nftables
│       ├── dhcp.py             # Endpoints HTTP para DHCP/Kea
│       ├── dhcp_service.py     # Leitura de leases e aplicação de reservations no Kea
│       ├── web.py              # Rotas das interfaces web
│       ├── templates/          # Telas HTML
│       └── static/             # JavaScript e CSS das telas administrativas
└── client/
    ├── Dockerfile              # Imagem dos clientes de teste
    └── start-client.sh         # Remove IP temporário do Docker e solicita DHCP via Kea
```

## Selos Considerados

Os selos considerados são:

- **Artefatos Disponíveis (SeloD)**: o código-fonte, scripts e configuração do experimento estão disponíveis neste repositório.
- **Artefatos Funcionais (SeloF)**: o artefato pode ser executado localmente com Docker Compose e permite observar DHCP, NAT, firewall e API administrativa.
- **Artefatos Sustentáveis (SeloS)**: o código está modularizado em componentes de gateway, API, firewall, DHCP e clientes de teste.
- **Experimentos Reprodutíveis (SeloR)**: as principais reivindicações podem ser reproduzidas por comandos documentados neste [README.md](README.md).

## Informações básicas

### Arquitetura lógica

O ambiente base sobe três containers:

- `gw`: gateway privilegiado com duas interfaces, uma na rede `wan` e outra na rede `lan`.
- `client1` e `client2`: clientes de laboratório conectados apenas à rede `lan`.

Opcionalmente, o perfil Compose `observability` adiciona o container `dockmon`,
baseado na imagem `darthnorse/dockmon`, para visualizar logs, eventos e métricas
dos containers pelo navegador.

```text
Host / Internet
    |
    | Docker bridge wan
    |
+-------------------------------+
| gw                            |
|-------------------------------|
| WAN: IP atribuído pelo Docker |
| LAN: 10.88.0.1                |
|                               |
| Kea DHCPv4                    |
| Kea Control Agent             |
| NAT nftables                  |
| Firewall nftables             |
| gwapi Flask                   |
+-------------------------------+
    |
    | Docker bridge lan internal
    |
+-------------------+       +-------------------+
| client1           |       | client2           |
| DHCP via Kea      |       | DHCP via Kea      |
+-------------------+       +-------------------+
```

A rede `lan` é uma bridge Docker `internal`, portanto os clientes não têm saída direta para a Internet. O tráfego deve passar pelo container `gw`, que faz NAT e aplica a política de firewall.

Observação importante: bridges Docker não usam DHCP para endereçar containers. Por isso, os clientes iniciam com um IP temporário do IPAM Docker, removem esse endereço e executam `dhclient` para obter um lease real do Kea. Para evitar colisão, a faixa temporária do Docker (`LAN_DOCKER_IP_RANGE`) fica separada do pool entregue pelo Kea.

### Configuração padrão

| Item | Valor padrão |
|---|---|
| LAN do laboratório | `10.88.0.0/24` |
| IP do gateway na LAN | `10.88.0.1` |
| Gateway interno da bridge Docker | `10.88.0.254` |
| Faixa temporária do IPAM Docker | `10.88.0.240/28` |
| MAC fixo do `client1` | `02:42:0a:58:01:01` |
| MAC fixo do `client2` | `02:42:0a:58:01:02` |
| Pool DHCP do Kea | `10.88.0.100 - 10.88.0.200` |
| DNS entregue por DHCP | `1.1.1.1, 9.9.9.9` |
| Domínio entregue por DHCP | `lab.local` |
| API/interface do firewall no host | [http://localhost:18080](http://localhost:18080) |
| Kea Control Agent no host | [http://localhost:18000](http://localhost:18000) |
| DockMon opcional | [https://localhost:8001](https://localhost:8001) |
| Usuário administrativo de laboratório | `admin` |
| Senha administrativa de laboratório | `troque-esta-senha` |

### Portas publicadas no host

| Serviço | URL padrão | Uso |
|---|---|---|
| `gwapi` / interface web | [http://localhost:18080](http://localhost:18080) | Gerência de firewall, grupos, DHCP e proxy para Kea |
| Kea Control Agent | [http://localhost:18000](http://localhost:18000) | API nativa do Kea para comandos `status-get`, `config-get` e `config-set` |
| DockMon | [https://localhost:8001](https://localhost:8001) | Painel opcional de logs, eventos e métricas dos containers |

### Ambiente usado no desenvolvimento

O artefato foi desenvolvido e testado no seguinte ambiente:

- Kubuntu 24.04 LTS
- Docker 29.4
- Processador AMD Ryzen 5 5600X, 6 cores
- 32 GB de RAM
- Armazenamento NVMe

Para a avaliação, recomenda-se uma máquina virtual Linux recente com pelo menos 2 vCPUs, 4 GB de RAM livres e 5 GB de espaço em disco. O experimento mínimo costuma executar em poucos minutos após o download das imagens e pacotes.

## Dependências

### Dependências no host

- Linux com suporte a Docker Engine.
- Docker Engine com o plugin `docker compose`.
- `git`, para clonar o repositório.
- `curl` e `jq`, para executar e inspecionar chamadas HTTP.
- `python3`, apenas se o avaliador quiser executar `reconfigure.py`.

Em Ubuntu/Kubuntu:

```bash
sudo apt update
sudo apt install -y git curl jq python3
```

Instale o Docker conforme a documentação oficial da distribuição usada. Depois confirme:

```bash
docker --version
docker compose version
```

### Dependências dentro dos containers

As imagens são construídas a partir de `ubuntu:24.04`.

O container `gw` instala:

- `kea`
- `nftables`
- `python3`
- `python3-flask`
- `iproute2`
- `iputils-ping`
- `curl`
- `jq`
- `net-tools`
- `procps`
- `ca-certificates`

Os containers `client1` e `client2` instalam:

- `isc-dhcp-client`
- `iproute2`
- `iputils-ping`
- `dnsutils`
- `curl`
- `ca-certificates`

O perfil opcional `observability` usa a imagem pública
`darthnorse/dockmon:latest` por padrão. A tag pode ser alterada por
`DOCKMON_TAG` no `.env`.

Não há benchmark externo, dataset, credencial privada ou serviço de nuvem necessário para reproduzir os testes documentados.

## Preocupações com segurança

Este artefato cria containers privilegiados para permitir manipulação de interfaces de rede, rotas, DHCP e `nftables`. Execute-o em uma máquina de laboratório ou máquina virtual descartável, especialmente durante a avaliação.

Cuidados recomendados:

- Não exponha as portas `18080` e `18000` para redes não confiáveis.
- Altere `ADMIN_PASSWORD` e `FLASK_SECRET_KEY` no arquivo `.env` antes de qualquer uso fora de uma máquina local isolada.
- Considere o Kea Control Agent em `18000` uma interface administrativa sensível.
- Se habilitar o DockMon, trate [https://localhost:8001](https://localhost:8001) como interface administrativa sensível. O container monta `/var/run/docker.sock`, portanto consegue inspecionar e gerenciar containers Docker do host.
- Ao primeiro acesso no DockMon, altere a senha padrão indicada pelo próprio projeto.
- Não execute este Compose em um host de produção.
- Ao terminar os testes, remova containers, redes e volumes com `docker compose down -v`.

O `nftables` é aplicado dentro do namespace de rede do container `gw`. Ainda assim, como o container é privilegiado, a recomendação para os revisores é executar o artefato em ambiente isolado.

## Instalação

### 1. Clonar o repositório

```bash
git clone git@github.com:ljbitzki/gw-kea-nftables.git
cd gw-kea-nftables
```

Se preferir HTTPS:

```bash
git clone https://github.com/ljbitzki/gw-kea-nftables.git
cd gw-kea-nftables
```

### 2. Criar o arquivo de configuração

```bash
cp .env.example .env
```

Revise pelo menos estas variáveis:

```text
ADMIN_USER=admin
ADMIN_PASSWORD=troque-esta-senha
FLASK_SECRET_KEY=troque-esta-chave-por-uma-string-longa
FW_API_HOST_PORT=18080
KEA_CA_HOST_PORT=18000
DOCKMON_HOST_PORT=8001
CLIENT1_MAC=02:42:0a:58:01:01
CLIENT2_MAC=02:42:0a:58:01:02
```

Opcionalmente, altere a topologia de rede com o assistente:

```bash
python3 reconfigure.py
```

Após usar o assistente, confira novamente o arquivo `.env`, em especial as credenciais administrativas e a chave Flask.

Os MAC addresses dos clientes também podem ser definidos no `.env`. Isso torna
a demonstração de reservas DHCP mais previsível. Se alterar `CLIENT1_MAC` ou
`CLIENT2_MAC` depois de os containers já existirem, recrie os clientes com
`docker compose up -d --force-recreate client1 client2`.

### 3. Construir e iniciar o laboratório

```bash
docker compose up -d --build
```

Para iniciar também o painel auxiliar de observabilidade:

```bash
docker compose --profile observability up -d --build
```

O DockMon ficará disponível em [https://localhost:8001](https://localhost:8001) por padrão. O navegador
deve alertar sobre certificado autoassinado, comportamento esperado para esse
container. No primeiro acesso, use `admin` / `dockmon123` e troque a senha.

### 4. Conferir se os containers estão em execução

```bash
docker compose ps
```

O resultado esperado é que `gw`, `client1` e `client2` estejam em execução. Se
o perfil `observability` tiver sido usado, `dockmon` também deve aparecer.

### 5. Preparar variáveis para os comandos de teste

Os comandos abaixo evitam usar `source .env`, pois alguns valores do arquivo podem conter espaços.

```bash
ADMIN_USER="$(sed -n 's/^ADMIN_USER=//p' .env)"
ADMIN_PASSWORD="$(sed -n 's/^ADMIN_PASSWORD=//p' .env)"
FW_API_HOST_PORT="$(sed -n 's/^FW_API_HOST_PORT=//p' .env)"
KEA_CA_HOST_PORT="$(sed -n 's/^KEA_CA_HOST_PORT=//p' .env)"
CLIENT1_MAC="$(sed -n 's/^CLIENT1_MAC=//p' .env)"
CLIENT2_MAC="$(sed -n 's/^CLIENT2_MAC=//p' .env)"
FW_API_HOST_PORT="${FW_API_HOST_PORT:-18080}"
KEA_CA_HOST_PORT="${KEA_CA_HOST_PORT:-18000}"
CLIENT1_MAC="${CLIENT1_MAC:-02:42:0a:58:01:01}"
CLIENT2_MAC="${CLIENT2_MAC:-02:42:0a:58:01:02}"
FW_AUTH="${ADMIN_USER:-admin}:${ADMIN_PASSWORD:-admin}"
```

## Teste mínimo

Este teste valida que o laboratório sobe, que a API responde, que os clientes recebem DHCP via Kea e que o tráfego LAN -> WAN passa pelo gateway.

### 1. Verificar saúde da API

```bash
curl -s -u "$FW_AUTH" "http://localhost:${FW_API_HOST_PORT}/health" | jq
```

Resultado esperado:

- JSON com `status: "ok"`.
- Campos `lan_if`, `wan_if`, `lan_cidr` e `kea_ca_url` preenchidos.

### 2. Verificar leases DHCP

```bash
curl -s -u "$FW_AUTH" "http://localhost:${FW_API_HOST_PORT}/dhcp/leases" | jq
```

Resultado esperado:

- Lista com leases para `client1` e `client2`.
- Endereços dentro do pool `10.88.0.100 - 10.88.0.200`.

Também é possível conferir diretamente no cliente:

```bash
docker exec client1 ip -4 addr show eth0
docker exec client1 ip route
```

Resultado esperado:

- `client1` possui endereço na rede `10.88.0.0/24`.
- A rota padrão aponta para `10.88.0.1`.

### 3. Verificar conectividade a partir da LAN

```bash
docker exec client1 ping -c 3 1.1.1.1
docker exec client1 curl -I --max-time 10 http://example.org
```

Resultado esperado:

- O `ping` recebe respostas.
- O `curl` retorna cabeçalhos HTTP.

### 4. Encerrar o ambiente após o teste

```bash
docker compose down -v
```

## Experimentos

Os experimentos abaixo reproduzem as principais reivindicações do artefato. Antes de executá-los, inicie o laboratório conforme a seção **Instalação** e prepare `FW_AUTH`, `FW_API_HOST_PORT` e `KEA_CA_HOST_PORT` conforme indicado.

### Reivindicação 1: o gateway entrega endereços DHCP na LAN isolada

**Objetivo.** Demonstrar que os clientes da rede `lan` recebem leases do Kea DHCPv4 executando no gateway.

**Comandos.**

```bash
curl -s -u "$FW_AUTH" "http://localhost:${FW_API_HOST_PORT}/dhcp/summary" | jq
curl -s -u "$FW_AUTH" "http://localhost:${FW_API_HOST_PORT}/dhcp/leases" | jq
docker exec client1 ip -4 addr show eth0
docker exec client2 ip -4 addr show eth0
```

**Tempo esperado.** Menos de 1 minuto após o ambiente estar iniciado.

**Recursos esperados.** Menos de 1 GB de RAM adicional para os containers em execução.

**Resultado esperado.** A API mostra a subnet `10.88.0.0/24`, pool `10.88.0.100 - 10.88.0.200` e leases ativos para os clientes. Os clientes apresentam endereços da LAN e rota padrão via `10.88.0.1`.

### Reivindicação 2: os clientes acessam a WAN por NAT no gateway

**Objetivo.** Demonstrar que a LAN Docker é isolada e que a saída ocorre pelo gateway `gw`, via regra de masquerade em `nftables`.

**Comandos.**

```bash
docker exec client1 ip route
docker exec client1 ping -c 3 1.1.1.1
docker exec gw nft list ruleset
```

**Tempo esperado.** Menos de 1 minuto.

**Recursos esperados.** Tráfego mínimo de rede e uso desprezível de disco.

**Resultado esperado.** O cliente usa `10.88.0.1` como gateway padrão, o `ping` responde e o ruleset contém uma cadeia `postrouting` com `masquerade` para a rede `10.88.0.0/24`.

### Reivindicação 3: a API altera dinamicamente a política do firewall

**Objetivo.** Demonstrar que uma regra inserida via API é persistida no estado da `gwapi` e aplicada em `nftables`.

**Comandos.**

Adicionar `client1` ao grupo de bloqueados:

```bash
CLIENT1_IP="$(docker exec client1 sh -c "ip -4 -o addr show eth0 | awk '{print \$4}' | cut -d/ -f1")"
curl -s -u "$FW_AUTH" -X POST "http://localhost:${FW_API_HOST_PORT}/firewall/groups/manual_blocked/members" \
  -H 'Content-Type: application/json' \
  -d "{\"member\":\"${CLIENT1_IP}/32\"}" | jq
```

Testar o bloqueio:

```bash
docker exec client1 ping -c 3 1.1.1.1
```

Remover o bloqueio:

```bash
curl -s -u "$FW_AUTH" -X DELETE "http://localhost:${FW_API_HOST_PORT}/firewall/groups/manual_blocked/members" \
  -H 'Content-Type: application/json' \
  -d "{\"member\":\"${CLIENT1_IP}/32\"}" | jq
docker exec client1 ping -c 3 1.1.1.1
```

**Tempo esperado.** Menos de 2 minutos.

**Recursos esperados.** Sem uso relevante de disco; apenas chamadas HTTP locais e atualização do ruleset.

**Resultado esperado.** Enquanto o IP está em `manual_blocked`, o tráfego de `client1` para a WAN falha. Após remover o membro, o `ping` volta a responder.

### Reivindicação 4: a API gerencia reservas DHCP no Kea

**Objetivo.** Demonstrar que a `gwapi` cria uma reserva DHCP, aplica a configuração no Kea e permite observar a reserva na configuração ativa.

**Comandos.**

Confirmar o MAC de `client1` definido no `.env`:

```bash
echo "${CLIENT1_MAC}"
docker exec client1 cat /sys/class/net/eth0/address
```

Criar uma reserva para `10.88.0.111`:

```bash
curl -s -u "$FW_AUTH" -X POST "http://localhost:${FW_API_HOST_PORT}/dhcp/reservations" \
  -H 'Content-Type: application/json' \
  -d "{
        \"subnet_id\": 1,
        \"hw_address\": \"${CLIENT1_MAC}\",
        \"ip_address\": \"10.88.0.111\",
        \"hostname\": \"client1\"
      }" | jq
```

Conferir a configuração ativa:

```bash
curl -s -u "$FW_AUTH" "http://localhost:${FW_API_HOST_PORT}/dhcp/config" \
  | jq '.subnet4[] | select(.id == 1) | .reservations'
```

Forçar renovação do lease no cliente:

```bash
docker exec client1 dhclient -r eth0
docker exec client1 dhclient -v eth0
docker exec client1 ip -4 addr show eth0
```

**Tempo esperado.** Menos de 3 minutos.

**Recursos esperados.** Sem uso relevante de disco; altera apenas o estado JSON da `gwapi` e a configuração em memória do Kea.

**Resultado esperado.** A reserva aparece em `/dhcp/config` com o MAC de `client1` e IP `10.88.0.111`. Após renovar o lease, `client1` passa a usar o IP reservado.

### Reivindicação 5: a configuração de rede pode ser reproduzida por `.env`

**Objetivo.** Demonstrar que a topologia do laboratório é parametrizada por variáveis de ambiente e pode ser recriada de forma controlada.

**Comandos.**

```bash
python3 reconfigure.py
docker compose down -v
docker compose up -d --build
docker compose ps
curl -s -u "$FW_AUTH" "http://localhost:${FW_API_HOST_PORT}/health" | jq
```

**Tempo esperado.** De 2 a 5 minutos, dependendo do cache local das imagens Docker.

**Recursos esperados.** Até alguns GB de tráfego/disco caso as imagens precisem ser reconstruídas sem cache.

**Resultado esperado.** O Compose recria as redes com os valores definidos em `.env`, o container `gw` sobe com o IP LAN configurado, e `/health` retorna a nova configuração.

## Uso da API e da interface web

### Interface web

A interface administrativa principal fica em [http://localhost:18080/](http://localhost:18080/).

A tela de DHCP fica em [http://localhost:18080/dhcp](http://localhost:18080/dhcp).

O login usa `ADMIN_USER` e `ADMIN_PASSWORD` do arquivo `.env`.

### Observabilidade com DockMon

Quando o laboratório for iniciado com `--profile observability`, o DockMon fica
disponível em [https://localhost:8001](https://localhost:8001).

Ele permite acompanhar logs dos containers `gw`, `client1`, `client2` e
`dockmon`, além de eventos e métricas do Docker. Os logs mais úteis do gateway
incluem:

- resumo de interfaces, pool DHCP e portas administrativas no boot;
- ruleset inicial do `nftables`;
- logs INFO do Kea DHCPv4 e do Kea Control Agent;
- chamadas HTTP da `gwapi`, com método, rota, status e duração;
- eventos administrativos de firewall, grupos e reservas DHCP.

### Endpoints principais

| Método | Caminho | Descrição |
|---|---|---|
| `GET` | `/health` | Saúde da API e informações de rede |
| `GET` | `/firewall` | Estado completo do firewall |
| `POST` | `/firewall/apply` | Reaplica o ruleset |
| `PUT` | `/firewall/default` | Altera a política padrão para `allow` ou `drop` |
| `POST` | `/firewall/rules` | Cria regra de firewall |
| `GET` | `/firewall/rules/<rule_id>` | Consulta regra |
| `PUT` | `/firewall/rules/<rule_id>` | Atualiza regra não sistêmica |
| `DELETE` | `/firewall/rules/<rule_id>` | Remove regra não sistêmica |
| `GET` | `/firewall/groups` | Lista grupos de endereços |
| `POST` | `/firewall/groups` | Cria grupo |
| `POST` | `/firewall/groups/<group_id>/members` | Adiciona membro a grupo |
| `DELETE` | `/firewall/groups/<group_id>/members` | Remove membro de grupo |
| `GET` | `/dhcp/status` | Consulta status do Kea DHCPv4 |
| `GET` | `/dhcp/config` | Consulta configuração ativa do Kea DHCPv4 |
| `GET` | `/dhcp/summary` | Resumo de DHCP, leases e reservas |
| `GET` | `/dhcp/leases` | Lista leases lidos do arquivo memfile do Kea |
| `GET` | `/dhcp/reservations` | Lista reservas gerenciadas pela `gwapi` |
| `POST` | `/dhcp/reservations` | Cria reserva DHCP |
| `PUT` | `/dhcp/reservations/<reservation_id>` | Atualiza reserva DHCP |
| `DELETE` | `/dhcp/reservations/<reservation_id>` | Remove reserva DHCP |
| `POST` | `/dhcp/apply` | Reaplica reservas no Kea |
| `POST` | `/dhcp/kea` | Proxy autenticado para comandos do Kea Control Agent |

### Exemplos rápidos

Consultar firewall:

```bash
curl -s -u "$FW_AUTH" "http://localhost:${FW_API_HOST_PORT}/firewall" | jq
```

Permitir SSH de saída:

```bash
curl -s -u "$FW_AUTH" -X POST "http://localhost:${FW_API_HOST_PORT}/firewall/rules" \
  -H 'Content-Type: application/json' \
  -d '{
        "id": "allow-ssh",
        "action": "allow",
        "proto": "tcp",
        "dport": 22,
        "description": "Permite SSH de saída"
      }' | jq
```

Remover a regra:

```bash
curl -s -u "$FW_AUTH" -X DELETE "http://localhost:${FW_API_HOST_PORT}/firewall/rules/allow-ssh" | jq
```

Consultar o Kea diretamente:

```bash
curl -s -X POST "http://localhost:${KEA_CA_HOST_PORT}/" \
  -H 'Content-Type: application/json' \
  -d '{"command":"status-get", "service":["dhcp4"]}' | jq
```

Consultar o Kea pelo proxy autenticado da `gwapi`:

```bash
curl -s -u "$FW_AUTH" -X POST "http://localhost:${FW_API_HOST_PORT}/dhcp/kea" \
  -H 'Content-Type: application/json' \
  -d '{"command":"status-get", "service":["dhcp4"]}' | jq
```

## Persistência e limpeza

O estado do firewall é armazenado em `/etc/gwapi/firewall_state.json` dentro do container `gw`. As reservas DHCP gerenciadas pela `gwapi` são armazenadas em `/etc/gwapi/dhcp_reservations.json`. Os leases do Kea são lidos de `/var/lib/kea/kea-leases4.csv`.

Na configuração atual, esses caminhos não estão montados em volumes nomeados. Portanto, `docker compose down -v` remove o estado do laboratório. Esta decisão mantém o experimento simples e descartável para avaliação.

Para parar sem remover redes e volumes:

```bash
docker compose down
```

Para remover o ambiente de forma limpa:

```bash
docker compose down -v
```

## Limitações conhecidas

- Os containers usam `privileged: true`; uma versão de produção deve reduzir isso para capacidades mínimas, como `NET_ADMIN` e `NET_RAW`, após validação.
- As portas administrativas são HTTP sem TLS; use apenas em ambiente local ou isolado.
- O Kea Control Agent fica publicado diretamente no host; em produção ele deveria ficar protegido por proxy, autenticação e controle de origem.
- O estado de firewall, leases e reservas não é persistido em volumes Docker nomeados por padrão.
- Alterações estruturais no pool ou na rede exigem recriação do ambiente.

## Solução de problemas

Ver logs do gateway:

```bash
docker logs gw
docker compose logs -f gw
```

Ver logs de um cliente:

```bash
docker logs client1
```

Iniciar ou consultar o DockMon:

```bash
docker compose --profile observability up -d dockmon
docker logs dockmon
```

Inspecionar regras aplicadas:

```bash
docker exec gw nft list ruleset
```

Recriar o ambiente do zero:

```bash
docker compose down -v
docker compose up -d --build
```

Se os clientes não receberem DHCP, confira se `LAN_DOCKER_IP_RANGE` não sobrepõe o pool DHCP do Kea e se o container `gw` está saudável.

## LICENSE

Este artefato é distribuído sob a licença **BSD 3-Clause**. Consulte o arquivo [LICENSE](LICENSE) para o texto completo.
