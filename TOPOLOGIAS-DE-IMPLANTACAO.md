# Topologias de implantação: gateway físico com Kea DHCP e nftables

Este documento descreve duas formas de levar a arquitetura do protótipo para um
ambiente físico com Ubuntu 24.04 LTS:

- um gateway com duas interfaces físicas, uma para WAN e outra para LAN;
- um gateway com uma única interface física, separando WAN e LAN por VLANs em
  um switch controlado.

Nos dois casos, o objetivo é o mesmo: o host Ubuntu atua como roteador da rede
interna, entrega endereços DHCPv4 com Kea, aplica política de firewall com
`nftables` e faz NAT/masquerade para permitir que os clientes da LAN acessem a
Internet pela WAN.

## Relação com o protótipo deste repositório

O laboratório em Docker Compose representa a mesma ideia lógica:

- `wan`: lado externo, com rota padrão para a Internet;
- `lan`: rede interna isolada, onde os clientes recebem DHCP pelo Kea;
- `gw`: gateway que possui uma interface em cada lado, aplica NAT e filtra o
  tráfego LAN -> WAN com `nftables`.

Em uma implantação física, os nomes mudam, mas os papéis permanecem:

| Papel lógico | Laboratório Docker | Cenário 1 físico | Cenário 2 com VLAN |
|---|---|---|---|
| WAN | rede Docker `wan` | NIC dedicada, ex. `enp1s0` | subinterface VLAN, ex. `wan10` |
| LAN | rede Docker `lan` | NIC dedicada, ex. `enp2s0` | subinterface VLAN, ex. `lan20` |
| Gateway LAN | `10.88.0.1` | IP fixo na NIC LAN | IP fixo na VLAN LAN |
| DHCP | Kea no `gw` | Kea escutando na NIC LAN | Kea escutando na VLAN LAN |
| NAT/firewall | `nftables` no `gw` | `nftables` no host | `nftables` no host |

O ponto mais importante é que WAN e LAN precisam ser domínios de camada 2
distintos. No cenário de uma única interface física, isso não deve ser feito
com dois endereços IP na mesma interface sem VLAN: nesse caso, broadcasts,
DHCP, ARP e tráfego de clientes e upstream ficariam misturados no mesmo domínio
L2, reduzindo isolamento e criando risco operacional. A separação correta é por
VLANs, ou por outra tecnologia equivalente de segmentação.

## Premissas de desenho

- O gateway é um roteador L3, não uma bridge transparente.
- A WAN fornece uma rota padrão. Ela pode usar DHCP, IP estático, PPPoE ou outro
  mecanismo do provedor/upstream, desde que o host tenha uma rota default por
  essa interface.
- A LAN usa endereçamento privado escolhido por você, por exemplo
  `10.88.0.0/24`.
- O IP do gateway na LAN deve ficar fora do pool DHCP. Exemplo:
  gateway `10.88.0.1`, pool `10.88.0.100` a `10.88.0.200`.
- O Kea DHCPv4 deve escutar somente na LAN.
- O Kea Control Agent e a interface administrativa do firewall devem ficar
  restritos a uma rede de gerência, ao próprio gateway, a uma VPN, ou a um
  conjunto pequeno de IPs confiáveis.
- Se IPv6 estiver habilitado, ele também precisa ser projetado e filtrado.
  Caso contrário, clientes podem obter conectividade IPv6 por outro caminho e
  contornar uma política pensada apenas para IPv4.

## Cenário 1: duas interfaces físicas

Neste modelo, o hardware possui duas placas/portas de rede. Uma porta conversa
com o lado externo; a outra conversa apenas com o switch dos clientes.

```text
Internet / roteador upstream
        |
        | WAN: ex. enp1s0
        |
+----------------------------+
| Ubuntu 24 LTS gateway      |
|----------------------------|
| enp1s0: WAN                |
| enp2s0: LAN 10.88.0.1/24   |
|                            |
| Kea DHCPv4                 |
| nftables firewall + NAT    |
| API/interface administrativa|
+----------------------------+
        |
        | LAN: ex. enp2s0
        |
+----------------------------+
| Switch de acesso            |
+----------------------------+
   |          |          |
cliente 1  cliente 2  cliente N
DHCP      DHCP      DHCP
```

### Quando usar

Este é o desenho mais simples de operar e depurar. Ele é recomendado quando o
gateway possui duas interfaces disponíveis ou quando é possível adicionar uma
segunda NIC USB/PCIe.

Vantagens:

- separação física clara entre WAN e LAN;
- menor dependência de configuração do switch;
- troubleshooting mais direto, pois cada cabo tem uma função;
- menor chance de vazamento acidental de DHCP entre os lados.

Pontos de atenção:

- nunca conecte a NIC LAN em uma rede que já tenha outro servidor DHCP, exceto
  se houver uma decisão explícita de coexistência;
- evite que a LAN e a WAN usem o mesmo prefixo IP;
- garanta que a rota default do Ubuntu esteja pela WAN, não pela LAN;
- se o host também for administrado pela LAN, restrinja a interface
  administrativa por IP, VPN ou firewall local.

### Plano de endereçamento sugerido

| Item | Exemplo |
|---|---|
| Interface WAN | `enp1s0` |
| Interface LAN | `enp2s0` |
| Endereço LAN do gateway | `10.88.0.1/24` |
| Pool DHCP | `10.88.0.100 - 10.88.0.200` |
| Reservas/infraestrutura | `10.88.0.2 - 10.88.0.99` |
| Endereços livres especiais | `10.88.0.201 - 10.88.0.254` |
| DNS entregue por DHCP | DNS externo, DNS local ou ambos |

### Exemplo de Netplan

O exemplo abaixo assume que a WAN recebe endereço por DHCP e que a LAN tem IP
fixo. Ajuste os nomes das interfaces conforme a saída de `ip link`.

```yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    enp1s0:
      dhcp4: true
    enp2s0:
      dhcp4: false
      addresses:
        - 10.88.0.1/24
```

Aplicação sugerida:

```bash
sudo netplan try
sudo netplan apply
ip addr
ip route
```

Depois de aplicar, a rota default deve aparecer pela WAN, por exemplo
`default via ... dev enp1s0`. A LAN deve aparecer com `10.88.0.1/24`, mas sem
rota default própria.

## Cenário 2: uma interface física com VLANs

Neste modelo, o gateway usa uma única porta de rede conectada a um switch
gerenciável. A separação entre WAN e LAN é feita por VLANs 802.1Q.

```text
                   +------------------------------+
                   | Switch gerenciável           |
                   |------------------------------|
Internet/upstream--| porta access VLAN 10 (WAN)   |
                   |                              |
clientes-----------| portas access VLAN 20 (LAN)  |
                   |                              |
gateway------------| porta trunk VLANs 10 e 20    |
                   +------------------------------+
                                      |
                                      | uma interface física: ex. enp1s0
                                      | frames tagged VLAN 10 e VLAN 20
                                      |
                         +----------------------------+
                         | Ubuntu 24 LTS gateway      |
                         |----------------------------|
                         | enp1s0: sem IP ou só trunk |
                         | wan10: VLAN 10, WAN        |
                         | lan20: VLAN 20, 10.88.0.1  |
                         |                            |
                         | Kea DHCPv4 em lan20        |
                         | nftables firewall + NAT    |
                         +----------------------------+
```

### Quando usar

Este desenho é adequado quando o equipamento tem apenas uma NIC, mas o switch é
gerenciável e você controla VLANs, trunks e portas de acesso.

Vantagens:

- usa apenas um cabo e uma interface física no gateway;
- permite manter isolamento lógico entre WAN e LAN;
- facilita expansão para novas redes, como DMZ, convidados ou gerência.

Pontos de atenção:

- a porta do gateway no switch deve ser trunk/tagged para as VLANs necessárias;
- as portas dos clientes devem ser access/untagged somente na VLAN da LAN;
- a porta do roteador upstream/provedor deve estar somente na VLAN da WAN;
- a interface física base, como `enp1s0`, normalmente não deve receber IP;
- não use a mesma VLAN para WAN e LAN;
- documente qual VLAN é WAN e qual VLAN é LAN antes de conectar clientes.

### Exemplo de mapa de VLANs

| Função | VLAN | Interface Linux | Switch |
|---|---:|---|---|
| WAN/upstream | 10 | `wan10` | porta upstream access VLAN 10; porta gateway tagged VLAN 10 |
| LAN/clientes | 20 | `lan20` | portas clientes access VLAN 20; porta gateway tagged VLAN 20 |
| Gerência opcional | 30 | `mgmt30` | portas/admin/VPN conforme necessidade |

Se o upstream não suporta tag VLAN e chega ao switch como tráfego sem tag, a
porta do upstream pode ser configurada como access na VLAN 10. O gateway ainda
recebe a VLAN 10 tagged pela porta trunk.

### Exemplo de Netplan

O exemplo abaixo cria duas subinterfaces VLAN em cima de `enp1s0`: uma para a
WAN e outra para a LAN.

```yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    enp1s0:
      dhcp4: false
      dhcp6: false
  vlans:
    wan10:
      id: 10
      link: enp1s0
      dhcp4: true
    lan20:
      id: 20
      link: enp1s0
      dhcp4: false
      addresses:
        - 10.88.0.1/24
```

Validação após aplicar:

```bash
sudo netplan try
sudo netplan apply
ip -d link show enp1s0
ip addr show wan10
ip addr show lan20
ip route
```

A rota default deve estar pela interface WAN VLAN, por exemplo `wan10`. O Kea
deve escutar em `lan20`, nunca em `enp1s0` ou `wan10`.

## Configuração do encaminhamento IP

Para o gateway rotear pacotes entre LAN e WAN:

```bash
sudo sysctl -w net.ipv4.ip_forward=1
```

Para persistir:

```text
net.ipv4.ip_forward=1
```

em um arquivo como `/etc/sysctl.d/99-gateway.conf`, seguido de:

```bash
sudo sysctl --system
```

Se IPv6 for usado, projete também o encaminhamento e o firewall IPv6. Se IPv6
não fizer parte do escopo, prefira bloquear ou desabilitar de forma explícita,
em vez de deixá-lo em estado indefinido.

## Firewall e NAT com nftables

A política recomendada para começar é:

- `input`: negar por padrão; permitir loopback, conexões estabelecidas,
  DHCP vindo da LAN, ICMP de diagnóstico e administração somente de origem
  confiável;
- `forward`: negar por padrão; permitir retorno de conexões estabelecidas e
  tráfego novo da LAN para a WAN conforme regras administrativas;
- `postrouting`: aplicar masquerade/NAT para a rede LAN saindo pela WAN;
- WAN -> LAN: negar por padrão, exceto se houver publicação explícita de
  serviços.

Exemplo mínimo para o cenário com duas interfaces:

```nft
define WAN_IF = "enp1s0"
define LAN_IF = "enp2s0"
define LAN_NET = 10.88.0.0/24
define ADMIN_IP = 10.88.0.10

flush ruleset

table inet gw_filter {
    chain input {
        type filter hook input priority 0; policy drop;

        iifname "lo" accept
        ct state established,related accept

        iifname $LAN_IF udp dport 67 accept comment "DHCPv4 na LAN"
        ip protocol icmp accept comment "ICMP diagnostico"

        ip saddr $ADMIN_IP tcp dport { 22, 8080 } accept comment "gerencia restrita"
    }

    chain forward {
        type filter hook forward priority 0; policy drop;

        ct state established,related accept
        iifname $LAN_IF oifname $WAN_IF jump lan_to_wan
    }

    chain lan_to_wan {
        meta nfproto ipv6 counter drop comment "IPv6 fora do escopo neste exemplo"

        udp dport 53 accept comment "DNS UDP"
        tcp dport { 53, 80, 443 } accept comment "DNS TCP, HTTP e HTTPS"
        ip protocol icmp accept comment "ICMP"

        counter drop comment "politica default LAN para WAN"
    }
}

table ip gw_nat {
    chain postrouting {
        type nat hook postrouting priority srcnat; policy accept;
        ip saddr $LAN_NET oifname $WAN_IF masquerade
    }
}
```

No cenário VLAN, a ideia é a mesma; apenas troque as interfaces:

```nft
define WAN_IF = "wan10"
define LAN_IF = "lan20"
```

O protótipo deste repositório segue esta mesma lógica ao construir o ruleset em
[gateway/gwapi_app/firewall.py](gateway/gwapi_app/firewall.py): identifica `LAN_IF`, identifica `WAN_IF`,
permite tráfego LAN -> WAN conforme regras e aplica masquerade para `LAN_CIDR`.

Neste exemplo, IPv6 é bloqueado explicitamente no encaminhamento. Se a intenção
for oferecer IPv6 aos clientes, substitua esse bloqueio por um desenho completo
de roteamento, anúncios de roteador, DHCPv6 quando necessário e regras `nftables`
equivalentes para IPv6.

## DHCPv4 com Kea

O Kea deve ser configurado para responder apenas na interface LAN. Em duas NICs,
essa interface pode ser `enp2s0`; em VLANs, pode ser `lan20`.

Exemplo mínimo:

```json
{
  "Dhcp4": {
    "interfaces-config": {
      "interfaces": [ "enp2s0" ]
    },
    "lease-database": {
      "type": "memfile",
      "persist": true,
      "name": "/var/lib/kea/kea-leases4.csv"
    },
    "valid-lifetime": 600,
    "renew-timer": 300,
    "rebind-timer": 500,
    "subnet4": [
      {
        "id": 1,
        "subnet": "10.88.0.0/24",
        "pools": [
          { "pool": "10.88.0.100 - 10.88.0.200" }
        ],
        "option-data": [
          { "name": "routers", "data": "10.88.0.1" },
          { "name": "domain-name-servers", "data": "1.1.1.1, 9.9.9.9" },
          { "name": "domain-name", "data": "lab.local" }
        ]
      }
    ]
  }
}
```

Para o cenário VLAN, altere `"interfaces": [ "enp2s0" ]` para
`"interfaces": [ "lan20" ]`.

Cuidados importantes:

- o pool não deve conter o IP do gateway;
- reservas DHCP devem ficar dentro da sub-rede, mas preferencialmente fora do
  intervalo dinâmico;
- se houver impressoras, câmeras, APs ou servidores na LAN, planeje reservas ou
  uma faixa estática;
- se a política de firewall bloquear DNS, os servidores DNS entregues por DHCP
  precisam ser exceções permitidas;
- o Control Agent do Kea é administrativo: em uso real, prefira bind em
  `127.0.0.1` ou em uma rede de gerência, não em todas as interfaces.

## Da concepção à aplicação prática

### 1. Levantamento inicial

Antes de configurar, registre:

- nomes das interfaces (`ip link`);
- qual cabo/porta chega ao upstream;
- qual cabo/porta chega ao switch dos clientes;
- prefixo que será usado na LAN;
- pool DHCP;
- DNS que será entregue aos clientes;
- como o gateway será administrado;
- se IPv6 será suportado ou bloqueado;
- se há outros servidores DHCP no ambiente.

### 2. Desenho da topologia

Para duas NICs:

- conecte a NIC WAN ao roteador upstream, modem, firewall de borda ou rede que
  forneça Internet;
- conecte a NIC LAN ao switch dos clientes;
- mantenha o switch LAN sem ligação direta ao upstream.

Para uma NIC com VLAN:

- escolha VLANs separadas para WAN e LAN;
- configure a porta do gateway como trunk/tagged;
- configure as portas dos clientes como access/untagged na VLAN LAN;
- configure a porta do upstream como access/untagged na VLAN WAN, salvo quando
  o upstream também trabalhar tagged;
- permita no trunk somente as VLANs necessárias.

### 3. Configuração do host

No Ubuntu:

- configure Netplan para criar as interfaces físicas ou VLANs;
- habilite `net.ipv4.ip_forward`;
- instale e habilite `nftables`;
- instale e configure Kea DHCPv4;
- aplique o ruleset de firewall/NAT;
- restrinja serviços administrativos.

Pacotes típicos:

```bash
sudo apt update
sudo apt install -y nftables kea tcpdump
```

Dependendo do empacotamento usado, os serviços podem aparecer como
`kea-dhcp4-server` e `kea-ctrl-agent`. Confirme com:

```bash
systemctl list-unit-files 'kea*'
```

### 4. Validação funcional

No gateway:

```bash
ip addr
ip route
sudo nft list ruleset
systemctl status nftables
systemctl status kea-dhcp4-server
```

Na LAN, conecte um cliente e valide:

- recebeu IP dentro do pool esperado;
- recebeu gateway `10.88.0.1`;
- recebeu DNS esperado;
- consegue pingar o gateway;
- consegue resolver DNS;
- consegue acessar HTTP/HTTPS se essas portas estiverem liberadas;
- não consegue acessar serviços bloqueados pela política.

Comandos úteis no gateway:

```bash
sudo tcpdump -ni enp2s0 'port 67 or port 68'
sudo journalctl -u kea-dhcp4-server -f
sudo nft list ruleset
```

No cenário VLAN, substitua `enp2s0` por `lan20`.

### 5. Validação de isolamento

Teste explicitamente os limites:

- um cliente LAN não deve receber DHCP do upstream;
- o upstream/WAN não deve receber DHCP do Kea;
- tráfego iniciado da WAN para a LAN deve ser bloqueado por padrão;
- a API administrativa não deve estar acessível pela WAN;
- se IPv6 estiver ativo, a política IPv6 deve bloquear ou permitir de modo
  tão explícito quanto a política IPv4.

## Problemas comuns e diagnóstico

| Sintoma | Causa provável | Verificação |
|---|---|---|
| Cliente não recebe DHCP | Kea escutando na interface errada, porta switch errada, VLAN não permitida no trunk | `tcpdump -ni LAN_IF port 67 or port 68` |
| Cliente recebe IP do upstream | VLANs misturadas ou LAN ligada diretamente à WAN | revisar portas access/trunk do switch |
| Gateway sem Internet | rota default ausente ou pela interface errada | `ip route` |
| Cliente tem IP mas não navega | NAT ausente, forward bloqueado, DNS bloqueado | `nft list ruleset`, teste `ping 1.1.1.1` e DNS |
| API exposta onde não deveria | regra `input` ampla demais ou bind em `0.0.0.0` | `ss -lntup`, regras `nftables` |
| Regras somem após reboot | serviço `nftables` não habilitado ou outro gerenciador sobrescrevendo | `systemctl status nftables`, verificar UFW/firewalld |
| VLAN não funciona | porta do switch não está tagged/trunk ou VLAN não existe | `ip -d link`, contadores do switch |
| Política IPv4 funciona, mas cliente ainda sai | IPv6 sem controle | revisar RA, DHCPv6, regras `ip6`/`inet` |

## Boas práticas para operação

- Mantenha um diagrama simples com cabos, portas, VLANs e endereços.
- Use nomes de interface previsíveis e documente qualquer renomeação.
- Evite gerenciar `nftables` simultaneamente por várias ferramentas sem um
  plano claro. UFW, firewalld e scripts próprios podem sobrescrever políticas.
- Faça backup dos arquivos de configuração antes de alterar firewall remoto.
- Use `netplan try` quando houver risco de perder acesso ao host.
- Comece com uma política pequena e observável; adicione regras por necessidade.
- Separe gerência, LAN de clientes e WAN sempre que possível.
- Trate Kea Control Agent e API de firewall como interfaces sensíveis.
- Em produção, prefira autenticação forte, HTTPS, logs persistentes e acesso
  administrativo por VPN ou rede de gerência.

## Checklist final

- [ ] WAN e LAN estão em interfaces ou VLANs distintas.
- [ ] A rota default do gateway sai pela WAN.
- [ ] A LAN tem IP fixo no gateway.
- [ ] `net.ipv4.ip_forward=1` está ativo e persistente.
- [ ] Kea DHCPv4 escuta somente na LAN.
- [ ] O pool DHCP não conflita com gateway, reservas ou endereços estáticos.
- [ ] `nftables` nega `input` e `forward` por padrão.
- [ ] Regras LAN -> WAN permitem apenas o necessário.
- [ ] NAT/masquerade está aplicado na saída WAN.
- [ ] Serviços administrativos não estão expostos na WAN.
- [ ] IPv6 foi explicitamente suportado ou bloqueado.
- [ ] A configuração sobrevive a reboot.
