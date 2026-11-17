# Checkout, Pedido e Configuração da Loja — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O cliente finaliza o pedido (agora ou agendado), o pedido fica gravado com número do dia, o cliente confirma pelo WhatsApp e acompanha o status; a Ana configura toda a loja dentro do /gerenciar.

**Architecture:** App novo `pedidos` (Pedido, ItemPedido, HistoricoStatus, ContadorDia; serviço `criar_pedido` que reaproveita `cardapio.precos.calcular_item`). App novo `clientes` (Cliente pelo telefone, do lado da loja; Dispositivo + EnderecoSalvo para o "Lembrar de mim", do lado do celular, sem nunca expor dados de um telefone digitado). Telas de configuração da loja entram no app `gerenciar` em módulos próprios. Deploy fica para o plano seguinte (ver `notas-para-plano-2.md`, itens 1–4 e 8).

**Tech Stack:** Django 5.2, HTMX 2.0.4, JS puro, pytest-django, node (smoke de JS). Cache do Django (LocMem local) para limitar envios.

**Spec:** `../docs/PRD-sistema.md` (seções 5, 6 "Tudo interno", 9 fluxo, 11, 14) + `docs/planos/notas-para-plano-2.md` (itens 5, 6, 7) + formato da mensagem em `../docs/levantamento-olaclick-2026-11-05.md` (Rodada 4).

## Global Constraints

- Tudo em Python; textos em português do Brasil; celular primeiro, sem rolagem horizontal em 360 px.
- **Nenhum arquivo de código/template/CSS/JS/teste passa de 1000 linhas** (alvo: ≤ 400). Dividir por assunto.
- Preço **sempre** recalculado no servidor (`calcular_item`); o total do pedido nunca vem do navegador.
- Valores `Decimal`, 2 casas, `ROUND_HALF_UP`. Acréscimo do cartão = `(subtotal + taxa_entrega) × acrescimo_pct / 100`.
- Pedido mínimo R$ 10 **só no delivery** (valor vem de `Configuracao.pedido_minimo`).
- Bairro inativo ou fora da lista: não entrega.
- Troco só para dinheiro; `troco_para` precisa ser ≥ total.
- Cliente bloqueado: mensagem **exata** "Não conseguimos receber seu pedido agora. Fale com a loja no WhatsApp."
- Agendamento **só com a loja fechada**: horários da próxima abertura, de 15 em 15 min, de `abre` até `fecha` inclusive. Loja aberta = pedido para agora.
- O nº do pedido recomeça todo dia (dia local `America/Recife`).
- Sem busca por telefone ou nome do lado do cliente. "Lembrar de mim" guarda dados **do aparelho**, nunca do telefone digitado.
- Observação do item até 140 caracteres; observação geral até 500.
- A Ana nunca precisa do /admin: tudo o que ela configura fica no /gerenciar (só Dono/superusuário).
- Docstrings curtas em português explicando o porquê (o Matheus está aprendendo).

## Review Focus

1. **Duplo toque em "Enviar pedido"** (4G lento) → não pode criar dois pedidos (dois impressos na cozinha). O formulário manda uma `chave` única; repetir a mesma chave devolve o mesmo pedido. Teste na Task 4.
2. **Envio em massa / brincadeira** (alguém dispara 30 pedidos) → limite de 5 pedidos por IP e 5 por telefone a cada 10 min, com mensagem clara. Teste na Task 6.
3. **Loja fecha entre abrir a sacola e enviar** (22:29 → 22:31) → o servidor recusa "pedido para agora" e pede para escolher horário; nada se perde da sacola. Teste na Task 4.
4. **Celular de outra pessoa / telefone de outra pessoa** → digitar o telefone de alguém nunca mostra o endereço dela; o "Usar cadastro anterior" só mostra o que *este aparelho* salvou. Teste na Task 5.
5. **Dois pedidos no mesmo segundo** → números do dia diferentes e em sequência (sem repetir #12). Teste na Task 3.

---

### Task 1: Configuração da loja no /gerenciar

**Files:**
- Modify: `loja/models.py` (Configuracao: `pix_titular`, `pix_banco`; migração)
- Create: `gerenciar/views_loja.py`, `gerenciar/forms_loja.py`, `gerenciar/templates/gerenciar/{loja,horarios,bairros,pagamentos}.html`
- Modify: `gerenciar/urls.py`, `gerenciar/templates/gerenciar/_topo.html` (aba "Loja")
- Test: `gerenciar/tests/test_loja.py`; adicionar as rotas novas em `gerenciar/tests/test_permissoes.py`

**Interfaces:**
- Produces: rotas `gerenciar:loja` (`/gerenciar/loja/`: modo da loja com 3 botões grandes "Pelo horário / Forçar aberta / Forçar fechada" + nome, slogan, endereço, WhatsApp, Instagram, chave Pix, titular, banco, prazo, pedido mínimo, vias), `gerenciar:horarios` (7 linhas: ativo, abre, fecha), `gerenciar:bairros` (lista com taxa e ativo editáveis, criar, excluir com confirmação), `gerenciar:pagamentos` (por forma: acréscimo %, aceita delivery/retirada/no local).
- Valores em reais usam o `ler_preco` existente (aceita 0 para taxa e acréscimo; rejeita negativo).

Regras: `fecha > abre` (senão erro "O horário de fechar precisa ser depois do de abrir."); WhatsApp guarda só dígitos e precisa ter 12 ou 13 dígitos começando com 55 (aceita digitar "(81) 99000-1234" e completa o 55); bairro com nome repetido dá erro de formulário; excluir bairro só pede confirmação (pedidos antigos guardam nome e taxa copiados).

- [ ] **Step 1: testes que falham**

```python
def test_dono_forca_loja_fechada(client_dono, horarios): ...      # POST modo=fechada -> status_loja().texto == "Fechado no momento"
def test_horario_fecha_antes_de_abrir_da_erro(client_dono, horarios): ...
def test_whatsapp_aceita_formatado_e_guarda_digitos(client_dono):
    # "(81) 99000-1234" -> "5581990001234"
def test_bairro_novo_e_taxa_em_reais(client_dono):                 # "Paratibe", "5,00" -> Decimal("5.00")
def test_bairro_nome_repetido_da_erro(client_dono): ...
def test_desligar_dinheiro_no_delivery(client_dono): ...            # aceita_delivery False
def test_acrescimo_negativo_da_erro(client_dono): ...
```

- [ ] **Step 2:** FAIL. **Step 3:** implementar (padrão de `views_grupos.py`: `dono_obrigatorio`, POST + CSRF, mensagens). **Step 4:** PASS + suíte.
- [ ] **Step 5:** commit `feat: dono configura a loja no gerenciar`.

---

### Task 2: Clientes e "Lembrar de mim"

**Files:**
- Create: app `clientes/` (`models.py`, `admin.py`, `servicos.py`, migrations)
- Modify: `config/settings.py` (INSTALLED_APPS)
- Test: `clientes/tests/test_clientes.py`

**Interfaces:**
- Produces (`clientes.models`):
  - `Cliente`: `telefone` (único, só dígitos com DDD, 10–11), `nome`, `bloqueado: bool`, `motivo_bloqueio`, `criado_em`. Lado da loja.
  - `Dispositivo`: `token_hash` (único, sha256 do token), `nome`, `telefone`, `criado_em`, `usado_em`. Lado do aparelho.
  - `EnderecoSalvo`: `dispositivo` FK, `bairro` FK `loja.Bairro` (`on_delete=SET_NULL`, null), `rua`, `numero`, `referencia`, `usado_em`.
- Produces (`clientes.servicos`):
  - `normalizar_telefone(texto: str) -> str` — só dígitos, sem 55; levanta `ValueError("Informe o WhatsApp com DDD, ex.: (81) 9 8888-7777.")` se não tiver 10 ou 11 dígitos.
  - `formatar_telefone(digitos: str) -> str` — "(81) 98888-7777".
  - `cliente_do_telefone(telefone: str, nome: str) -> Cliente` — get_or_create; não troca o nome de quem já existe.
  - `dispositivo_do_token(token: str | None) -> Dispositivo | None`
  - `lembrar(token: str | None, nome, telefone, bairro, rua, numero, referencia) -> str` — cria o dispositivo se preciso, atualiza nome/telefone, adiciona o endereço se for novo (mesmo bairro+rua+numero não duplica), devolve o token (novo ou o mesmo).
  - Constante `COOKIE_DISPOSITIVO = "lb_aparelho"` (1 ano, HttpOnly, SameSite=Lax).

- [ ] **Step 1: testes que falham**

```python
@pytest.mark.parametrize("entrada, saida", [("(81) 9 8888-7777", "81988887777"), ("+55 81 98888-7777", "81988887777"), ("8133334444", "8133334444")])
def test_normalizar_telefone(entrada, saida): ...
def test_telefone_sem_ddd_da_erro(): ...
def test_cliente_existente_nao_troca_nome(db): ...
def test_lembrar_cria_token_e_nao_duplica_endereco(db, bairro): ...
def test_token_errado_nao_acha_dispositivo(db): ...
def test_token_guardado_so_como_hash(db):  # Dispositivo.token_hash != token
```

- [ ] **Step 2:** FAIL. **Step 3:** implementar (`secrets.token_urlsafe(32)`, `hashlib.sha256`). **Step 4:** PASS. **Step 5:** commit `feat: clientes e lembrar de mim`.

---

### Task 3: Modelos do pedido e número do dia

**Files:**
- Create: app `pedidos/` (`models.py`, `admin.py` só leitura, `numeracao.py`, migrations)
- Test: `pedidos/tests/test_modelos.py`

**Interfaces:**
- Produces (`pedidos.models`):
  - `Pedido`: `codigo` (único, `secrets.token_urlsafe(9)`, usado na URL de acompanhar), `chave` (UUID único enviado pelo formulário), `numero` (do dia), `dia` (date local), `origem` (`"site"|"pdv"`), `tipo` (`"delivery"|"retirada"|"local"`), `status` (`"agendado"|"preparo"|"pronto"|"saiu"|"concluido"|"cancelado"`), `cliente` FK (PROTECT), `nome`, `telefone` (copiados), `bairro_nome`, `rua`, `numero_end`, `referencia` (copiados), `agendado_para: datetime|None`, `observacao`, `forma_pagamento_nome`, `forma_pagamento_codigo`, `troco_para`, `subtotal`, `taxa_entrega`, `acrescimo`, `desconto` (0), `total`, `pago: bool`, `criado_em`. Property `troco` (`troco_para - total` ou None). `get_tipo_display` em português: "Delivery", "Retirada", "No local".
  - `ItemPedido`: `pedido` FK, `produto` FK (`SET_NULL`, null), `nome`, `preco_unitario`, `quantidade`, `opcoes` (JSON: `[{grupo, nome, qtd, preco}]`), `observacao`; property `total`.
  - `HistoricoStatus`: `pedido` FK, `status`, `em`.
  - `ContadorDia`: `dia` (único), `ultimo`.
- Produces (`pedidos.numeracao`): `proximo_numero(dia: date) -> int` — dentro de `transaction.atomic` com `select_for_update` no `ContadorDia` (cria se não existe).

- [ ] **Step 1: testes que falham**

```python
def test_numero_recomeca_no_dia_seguinte(db): ...       # 1,2 em 11/11; 1 em 12/11
def test_numeros_em_sequencia_sem_repetir(db):           # 20 chamadas -> 1..20
def test_codigo_unico_e_nao_sequencial(db): ...
def test_troco(db): ...                                  # troco_para 50, total 37,40 -> 12,60
```

- [ ] **Step 2:** FAIL. **Step 3:** implementar. **Step 4:** PASS. **Step 5:** commit `feat: modelos do pedido e número do dia`.

---

### Task 4: Criar pedido (regras do checkout)

**Files:**
- Create: `pedidos/servicos.py`, `pedidos/agendamento.py`
- Modify: `loja/horario.py` (turno da loja fechada)
- Test: `pedidos/tests/test_criar_pedido.py`, `pedidos/tests/test_agendamento.py`, `loja/tests/test_horario.py`

**Interfaces:**
- Consumes: `calcular_item`/`PrecoInvalido` (cardápio), `status_loja`/`proxima_abertura` (loja), `cliente_do_telefone`/`normalizar_telefone` (Task 2), modelos e `proximo_numero` (Task 3).
- Produces:
  - `class PedidoInvalido(Exception)` — mensagem pronta; atributo opcional `campo` (ex.: `"horario"`, `"bairro"`).
  - `horarios_agendamento(agora: datetime | None = None) -> list[datetime]` — vazio se a loja está aberta ou não há próxima abertura.
  - `criar_pedido(dados: dict, agora: datetime | None = None) -> Pedido`. `dados` = `{chave, tipo, nome, telefone, bairro_id, rua, numero, referencia, observacao, pagamento, troco_para, agendar_para (ISO ou ""), itens: [{produto_id, quantidade, opcoes, observacao}]}`.
  - **Mudança em `status_loja`:** com a loja fechada e havendo próxima abertura, `turno = proxima_abertura.date().isoformat()` (antes era `""`). Atualizar o teste `test_turno_vazio_quando_fechada` → `test_turno_fechada_e_data_da_proxima_abertura`; sem próxima abertura continua `""`.

Regras de `criar_pedido` (nesta ordem): mesma `chave` já usada → devolve o pedido existente; sacola vazia ou > 50 itens; nome obrigatório (até 80); telefone válido; cliente bloqueado → mensagem exata do Global Constraints; tipo válido; loja aberta → `agendar_para` precisa vir vazio; loja fechada → `agendar_para` precisa estar em `horarios_agendamento()` (senão `PedidoInvalido("A loja está fechada. Escolha um horário para agendar.", campo="horario")`); itens por `calcular_item` (erro vira `PedidoInvalido` com a mesma mensagem); delivery → bairro ativo, rua e número obrigatórios, subtotal ≥ pedido mínimo ("Pedido mínimo para entrega: R$ 10,00."); forma de pagamento existe e aceita o tipo; acréscimo; troco (`ler_valor` como no protótipo); total; tudo em `transaction.atomic`; status inicial `"agendado"` se agendado, senão `"preparo"`; grava `HistoricoStatus`.

- [ ] **Step 1: testes que falham**

```python
def test_total_com_taxa_e_acrescimo_do_credito(db, cenario):
    # burger 20 + bacon 2,50 x2, qtd 2 = 50,00; taxa 5; crédito 4% de 55 = 2,20 -> total 57,20
def test_mesma_chave_nao_cria_dois_pedidos(db, cenario): ...
def test_cliente_bloqueado_recebe_mensagem_neutra(db, cenario): ...
def test_pedido_minimo_so_no_delivery(db, cenario): ...
def test_bairro_inativo_nao_entrega(db, cenario): ...
def test_dinheiro_desligado_no_delivery(db, cenario): ...
def test_troco_menor_que_total_da_erro(db, cenario): ...
def test_loja_fechou_antes_de_enviar_pede_horario(db, cenario):   # campo == "horario"
def test_agendado_fica_com_status_agendado(db, cenario): ...
def test_horario_fora_da_lista_e_recusado(db, cenario): ...
def test_preco_vem_do_banco_mesmo_se_navegador_mandar_total(db, cenario): ...
# test_agendamento.py
def test_horarios_da_proxima_abertura_de_15_em_15(db, horarios):
    # segunda 20:00 -> quarta 18:15, 18:30 ... 22:30 (18 horários)
def test_sem_horarios_com_loja_aberta(db, horarios): ...
```

- [ ] **Step 2:** FAIL. **Step 3:** implementar. **Step 4:** PASS + suíte (inclui o teste de horário alterado). **Step 5:** commit `feat: criar pedido com as regras do checkout`.

---

### Task 5: Sacola com a loja fechada

**Files:**
- Modify: `static/js/sacola.js`, `static/js/produto.js`, `cardapio/templates/cardapio/{cardapio,_produto_modal}.html`, `cardapio/views.py`
- Modify: `static/js/tests/sacola.smoke.js`
- Test: `cardapio/tests/test_views.py`, smoke JS

**Interfaces:**
- Consumes: novo `turno` (Task 4).
- Produces: `<body data-turno="AAAA-MM-DD" data-aberta="1|0" data-agendavel="1|0">`; regra da sacola: esvazia **só** quando o turno muda ou quando `data-turno` é `""` (nunca abre). Com a loja fechada mas agendável, o botão do modal fica "Adicionar R$ X" e a barra mostra "Pedido agendado para quarta, a partir de 18:15".

- [ ] **Step 1: testes que falham:** `test_loja_fechada_agendavel_deixa_adicionar` (HTML do modal sem "Loja fechada", body com `data-agendavel="1"`); `test_sem_abertura_futura_mostra_loja_fechada`. Smoke JS: com `data-aberta="0"`, `data-turno="2026-11-18"` e sacola salva com o mesmo turno → mantém os itens; com turno diferente → esvazia.
- [ ] **Step 2:** FAIL. **Step 3:** implementar. **Step 4:** PASS (`pytest` + `node static/js/tests/sacola.smoke.js`). **Step 5:** commit `feat: sacola para pedido agendado`.

---

### Task 6: Tela de checkout

**Files:**
- Create: `pedidos/views_checkout.py`, `pedidos/urls.py`, `pedidos/templates/pedidos/checkout.html`, `static/js/checkout.js`, `static/css/checkout.css`
- Modify: `config/urls.py`, `cardapio/models.py` (`Produto.sugerir_no_checkout` + migração; checkbox no formulário de produto do /gerenciar), `static/js/sacola.js` (botão "Continuar" → `/checkout/`)
- Test: `pedidos/tests/test_checkout.py`

**Interfaces:**
- Consumes: `criar_pedido`, `horarios_agendamento`, `PedidoInvalido` (Task 4); `dispositivo_do_token`, `lembrar`, `COOKIE_DISPOSITIVO` (Task 2); `localStorage["sacola"]`.
- Produces:
  - `GET /checkout/` → uma tela: itens da sacola (desenhados pelo JS a partir do localStorage, conferidos em `/sacola/validar/`), "Complemente seu pedido" (até 6 produtos com `sugerir_no_checkout`, visíveis e não esgotados), "Usar cadastro anterior" (cartões dos endereços do aparelho: "Nome · Rua, nº — Bairro · [Usar este]" + "Outro endereço"), tipo (Entrega / Retirada / No local), bairro com taxa ao lado, rua, número, referência, pagamento (só as formas que aceitam o tipo), troco (só dinheiro), observação geral (500), horário (só quando agendável), "Lembrar de mim neste celular" (marcado), resumo (subtotal + entrega + acréscimo = total, calculado no JS só para mostrar) e "Enviar pedido".
  - `POST /checkout/enviar/` (JSON, CSRF) → `201 {"codigo", "url": "/pedido/<codigo>/"}` ou `400 {"erro", "campo"}`; `429 {"erro": "Muitos pedidos em pouco tempo. Aguarde alguns minutos ou fale com a loja no WhatsApp."}` acima de 5 por IP ou 5 por telefone em 10 min (cache do Django). Se "lembrar" vier marcado, responde com o cookie `lb_aparelho`.
  - O JS gera a `chave` (`crypto.randomUUID()`, com reserva para navegador antigo) uma vez por tentativa e reaproveita nos reenvios; botão desabilitado durante o envio; `fetch` com `AbortController` de 20 s ("A internet está lenta. Tente de novo." — reenvio usa a mesma chave). Sucesso → apaga a sacola e vai para a URL devolvida.

- [ ] **Step 1: testes que falham**

```python
def test_checkout_lista_so_formas_do_tipo(client, cenario): ...
def test_usar_cadastro_anterior_so_do_proprio_aparelho(client, cenario):
    # aparelho A salvou endereço; cliente sem cookie (ou com cookie de B) não vê
def test_enviar_cria_pedido_e_devolve_url(client, cenario): ...
def test_enviar_com_erro_devolve_campo(client, cenario): ...       # bairro faltando -> campo "bairro"
def test_lembrar_de_mim_seta_cookie_httponly(client, cenario): ...
def test_limite_de_envios_por_telefone(client, cenario): ...       # 6º -> 429
def test_enviar_exige_csrf(cenario): ...
def test_complemente_mostra_so_sugeridos_disponiveis(client, cenario): ...
```

- [ ] **Step 2:** FAIL. **Step 3:** implementar (layout base: `checkout.html`/`checkout.js` do protótipo). **Step 4:** PASS + smoke JS. **Step 5:** commit `feat: tela de checkout`.

---

### Task 7: Pedido recebido, WhatsApp e acompanhar

**Files:**
- Create: `pedidos/whatsapp.py`, `pedidos/views_acompanhar.py`, `pedidos/templates/pedidos/{acompanhar,_status}.html`
- Modify: `pedidos/urls.py`
- Test: `pedidos/tests/test_whatsapp.py`, `pedidos/tests/test_acompanhar.py`

**Interfaces:**
- Produces:
  - `mensagem_pedido(pedido: Pedido) -> str` e `link_whatsapp(pedido: Pedido) -> str` (`https://wa.me/<Configuracao.whatsapp>?text=...`).
  - `GET /pedido/<codigo>/` → tela "Pedido recebido": nº grande, resumo, chave Pix + titular + banco (se Pix), botão "Confirmar no WhatsApp" (abre sozinho uma vez por pedido, controlado com `sessionStorage`), e o status. `404` para código inexistente.
  - `GET /pedido/<codigo>/status/` → fragmento `_status.html`; a tela recarrega com HTMX a cada 15 s (`hx-trigger="every 15s"`) até `concluido`/`cancelado`.
  - Textos de status para o cliente: agendado "Agendado para qua, 18/11 às 18:15", preparo "Em preparo", pronto (retirada/local) "Pronto! Pode vir buscar", saiu "Saiu para entrega 🛵", concluido "Entregue", cancelado "Cancelado".

Formato da mensagem (base OlaClick, Rodada 4):

```
Olá! Quero confirmar meu pedido 🍔
*Pedido #12* · {codigo}
🗓️ 18/11/2026 ⏰ 18:15            ← só se agendado
*Tipo de serviço: Delivery*
Nome: …
Telefone: (81) 98888-7777
Endereço: Rua …, 505 — Paratibe
Referência: …                      ← só se houver
*📝 Produtos*
*2x Brasa Premium  R$ 50,00*
    + Ao ponto
    + 2x Bacon R$ 5,00
    _Obs.: sem picles_
Subtotal: R$ 50,00
Entrega: R$ 5,00
Acréscimo cartão: R$ 2,20          ← só se houver
*Total: R$ 57,20*
*💲 Pagamento:* Cartão de crédito
Troco para R$ 100,00 (troco de R$ 42,80)   ← só dinheiro com troco
Chave Pix: … · Titular: … · Banco: …       ← só Pix (titular/banco se preenchidos)
Observação: …                      ← só se houver
```

- [ ] **Step 1: testes que falham:** `test_mensagem_delivery_credito` (texto completo do exemplo acima, sem as linhas marcadas com ← que não se aplicam a um pedido não agendado, em crédito, sem observação geral; comparado linha a linha); `test_mensagem_agendado_tem_data_e_hora`; `test_mensagem_pix_com_titular_e_banco`; `test_link_whatsapp_usa_numero_da_loja_e_codifica_texto`; `test_acompanhar_404_codigo_errado`; `test_status_texto_retirada_pronto`; `test_acompanhar_nao_mostra_outro_pedido` (código de A não mostra dados de B).
- [ ] **Step 2:** FAIL. **Step 3:** implementar (base: `mensagem_whatsapp` do protótipo). **Step 4:** PASS + suíte. **Step 5:** commit `feat: pedido recebido, whatsapp e acompanhar`.

---

## Próximos planos

- **Plano 3 — No ar:** itens 1–4, 7 e 8 de `notas-para-plano-2.md` (fotos persistentes, whitenoise, HTTPS, limite de login, upload) + Railway + domínio `brasaburguer.com.br`. Precisa do Matheus para criar as contas.
- **Plano 4 — Painel:** painel de pedidos, **PDV com o cardápio dentro do painel**, tela da cozinha, esgotado na hora, logins Dono/Equipe/Entregador (PWA), clientes (lista, bloqueio), botões de WhatsApp.
- **Plano 5 — Impressão, entregadores e resumo do dia.**
