# Painel de pedidos — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A loja vê e move os pedidos numa tela só (PC e celular): colunas por etapa, filtro por tipo, busca, alarme de pedido novo, detalhe com WhatsApp pronto, pago, cancelar e aceitar/recusar; o Caio entra com login de Equipe.

**Architecture:** As regras ficam em `pedidos/painel.py` (transições, com histórico e usuário) e `pedidos/painel_consultas.py` (colunas, contagens, total, versão). Os textos de WhatsApp ficam em `pedidos/mensagens_status.py`. As telas ficam em `gerenciar/views_pedidos.py` com parciais HTMX: as colunas são consultadas a cada 5 s e só são trocadas quando a "versão" muda (resposta 204 quando nada mudou). O JS (`static/js/painel.js`) cuida do alarme (WebAudio, sem arquivo de som), do título piscando, das abas no celular e do atalho "Avisar no WhatsApp".

**Tech Stack:** Django 5.2, HTMX 2.0.4, JS puro, pytest-django, node (smoke de JS).

**Spec:** `docs/superpowers/specs/2026-11-11-painel-de-pedidos-design.md` (aprovado em 11/11). Mockups: `../.superpowers/brainstorm/1084-1794425446/content/painel-pedidos.html` e `detalhe-pedido.html`.

## Global Constraints

- Textos em português do Brasil; docstrings curtas explicando o porquê.
- **Nenhum arquivo passa de 1000 linhas** (alvo ≤ 400). Painel em arquivos próprios, não engordar `gerenciar/views.py`.
- Toda tela funciona em **360 px e ~1366 px**, sem rolagem horizontal; botões de toque com ≥ 40 px de altura.
- Visual com os tokens de `static/css/base.css` (preto, amarelo `--apoio` só com texto preto, vermelho `--alert` só para alerta).
- Fuso `America/Recife`; "hoje" = `timezone.localdate()`.
- Etapas: `aguardando`, `agendado`, `preparo`, `pronto`, `saiu`, `concluido`, `cancelado` (já existem em `Pedido.STATUS`).
- Tempo vermelho no cartão a partir de **40 min**. Agendado vira "Em preparo" **30 min antes** de `agendado_para`. Consulta das colunas a cada **5 s**. Coluna Concluído mostra **20** e depois "ver todos".
- **Equipe**: não vê total nem quantidade do dia (o bloco não vai para o HTML); não cancela (403); não acessa produtos/categorias/opções/loja (403). Vê o valor de cada pedido.
- Cancelar: só Dono, motivo obrigatório, de qualquer etapa menos `cancelado`. Recusar: Dono e Equipe, só de `aguardando`, motivo opcional.
- Mensagens de status no WhatsApp só para Delivery e Retirada; "Falar com o cliente" sempre. Textos exatos na Task 3.
- Pago/Não pago é só informativo: nada exige pagamento para avançar ou finalizar.
- Toda rota nova entra em `gerenciar/tests/test_permissoes.py`.
- Cada tarefa termina com commit **e `git push`**.

## Review Focus

1. **Sessão expirada no meio da noite** → a consulta das colunas não pode colar a tela de login dentro do painel; requisição HTMX sem login recebe `HX-Redirect` para `/gerenciar/entrar/`. Teste na Task 4.
2. **Dois aparelhos ao mesmo tempo** (Caio toca "Pronto" num pedido que a Ana acabou de cancelar) → nada muda, sem erro. Teste na Task 2.
3. **Pedido de ontem ainda aberto depois da meia-noite** → continua nas colunas, mas não entra no total nem no Concluído de hoje. Teste na Task 2 (consultas).
4. **Busca com telefone formatado** ("(81) 98888-7777", "988887777") → acha pelos dígitos. Teste na Task 2 (consultas).
5. **Aba do notebook escondida/hibernada** → a consulta pausa e, ao voltar, atualiza na hora e o alarme volta a tocar se ainda houver pedido novo. Conferência manual na Task 6 + smoke.

---

### Task 1: Papel Equipe, campos novos e regras de etapa

**Files:**
- Create: `gerenciar/migrations/0002_grupo_equipe.py`, `pedidos/migrations/0005_painel.py`, `pedidos/painel.py`, `pedidos/tests/test_painel_regras.py`
- Modify: `gerenciar/permissoes.py`, `pedidos/models.py`, `gerenciar/tests/conftest.py`

**Interfaces:**
- Produces (permissoes): `eh_equipe(user) -> bool` (grupo "Equipe" **ou** Dono), `equipe_obrigatorio(view)` (anônimo → login; logado sem papel → 403).
- Produces (models): `Pedido.visto_em: DateTimeField(null)`, `Pedido.motivo_cancelamento: CharField(200, blank)`, `HistoricoStatus.usuario: FK(User, null, SET_NULL)`, `HistoricoStatus.nota: CharField(200, blank)`.
- Produces (`pedidos/painel.py`), todas devolvem `bool` (True = mudou) e gravam `HistoricoStatus(status=<novo status>, usuario=..., nota=...)` dentro de `transaction.atomic` com `select_for_update` no pedido:
  - `proxima_etapa(pedido) -> tuple[str, str] | None` → `(status, rótulo)`: preparo→`("pronto","✓ Pronto")`; pronto+delivery→`("saiu","🛵 Saiu para entrega")`; pronto+retirada/local→`("concluido","✓ Entregue")`; saiu→`("concluido","✓ Entregue")`; outros→`None`.
  - `avancar(pedido_id, de, usuario)`; `voltar(pedido_id, de, usuario)` (volta para o status do registro anterior do histórico que esteja em {preparo, pronto, saiu}; nota `"voltou"`; não vale de `cancelado`, `aguardando`, `agendado`).
  - `aceitar(pedido_id, usuario, agora)` → `preparo`, ou `agendado` se `agendado_para > agora + 30 min`; preenche `visto_em`.
  - `recusar(pedido_id, usuario, motivo="")` → `cancelado`, nota `"recusado"` (+ `": motivo"`).
  - `cancelar(pedido_id, usuario, motivo)` → `cancelado`; `ValueError` se motivo vazio; grava `motivo_cancelamento`.
  - `comecar_agora(pedido_id, usuario)` → agendado→preparo, `visto_em=None` (conta como novo).
  - `marcar_pago(pedido_id, pago: bool, usuario)` → nota `"pago"`/`"não pago"`, status repetido.
  - `marcar_visto(pedido_id)` → preenche `visto_em` se vazio (não grava histórico).
  - `finalizar_todos(usuario) -> int` → preparo/pronto/saiu de qualquer dia → concluido, nota `"finalizar todos"`.
- Regra de corrida: `de` é o status que o aparelho viu; se diferente do atual, devolve `False` e não grava nada.

- [ ] **Step 1: Testes que falham** em `pedidos/tests/test_painel_regras.py` (criar pedidos com `cenario` + `criar_pedido`):
  - `test_proxima_etapa_por_tipo`: os 4 casos acima e `None` para concluido/cancelado/aguardando.
  - `test_avancar_grava_historico_com_usuario`: preparo→pronto; último histórico tem `status="pronto"` e `usuario=dono`.
  - `test_avancar_com_status_velho_nao_faz_nada`: cancela, depois `avancar(id, "preparo", equipe)` → `False`, status continua `cancelado`, nenhum histórico novo.
  - `test_voltar_desfaz_toque_errado`: preparo→pronto→`voltar` → preparo, nota `"voltou"`; `voltar` de cancelado → `False`.
  - `test_aceitar_agendado_longe_vai_para_agendado` e `test_aceitar_sem_horario_vai_para_preparo` (com `Configuracao.entrada_pedidos="manual"`).
  - `test_recusar_so_de_aguardando` (de preparo → `False`), nota começa com `"recusado"`.
  - `test_cancelar_exige_motivo` (`ValueError`), `test_cancelar_de_concluido` funciona, `test_cancelar_duas_vezes` → segunda `False`.
  - `test_finalizar_todos_nao_mexe_em_aguardando_nem_agendado`: devolve a contagem certa.
  - `test_marcar_pago_nao_muda_status`.
  - `test_eh_equipe`: usuário do grupo Equipe → True; Dono → True; comum → False.
- [ ] **Step 2:** `python -m pytest pedidos/tests/test_painel_regras.py -q` → falham (módulo inexistente).
- [ ] **Step 3:** Migração de dados `gerenciar/0002_grupo_equipe.py` (cria grupo "Equipe", mesmo padrão da `0001_grupo_dono.py`); campos novos em `pedidos/models.py` + `makemigrations pedidos --name painel`; `eh_equipe`/`equipe_obrigatorio` em `permissoes.py`; funções em `pedidos/painel.py`. Fixtures novas em `gerenciar/tests/conftest.py`: `usuario_equipe`, `client_equipe` (mesmo padrão de `client_dono`).
- [ ] **Step 4:** Rodar o teste da Step 2 e `python -m pytest -q` → tudo passa; `python manage.py makemigrations --check` sem mudanças.
- [ ] **Step 5:** Commit `feat: papel Equipe e regras de etapa dos pedidos` + `git push`.

### Task 2: Consultas do painel (colunas, filtros, busca, total, versão)

**Files:**
- Create: `pedidos/painel_consultas.py`, `pedidos/tests/test_painel_consultas.py`

**Interfaces:**
- Consumes: `Pedido` (Task 1).
- Produces:
  - `com_dia_efetivo(qs) -> QuerySet` anotando `dia_efetivo` = data local (Recife) de `agendado_para` se houver, senão `dia` (`Coalesce(TruncDate("agendado_para", tzinfo=Recife), "dia")`).
  - `promover_agendados(agora) -> int`: agendados com `agendado_para - 30 min <= agora` → preparo, `visto_em=None`, histórico nota `"agendado: começou"`, `usuario=None`.
  - `montar_painel(hoje, tipo="", busca="", todos_concluidos=False) -> Painel` (dataclass) com:
    - `colunas: list[Coluna]` — `Coluna(status, titulo, pedidos, total_itens)`; ordem: `aguardando` (só se `Configuracao.entrada_pedidos=="manual"` **ou** existir pedido aguardando), `preparo`, `pronto`, `saiu`, `concluido`. Abertas: qualquer dia, mais antigo primeiro. Concluído: `concluido`+`cancelado` com `dia_efetivo==hoje`, mais recente primeiro, até 20 (todos se `todos_concluidos`).
    - `agendados: list[Pedido]` (status `agendado`, por `agendado_para`).
    - `contagem_tipo: dict` com chaves `"tudo","delivery","retirada","local","agendados"` (só pedidos abertos: aguardando/preparo/pronto/saiu; agendados à parte).
    - `novos: int` = pedidos em aguardando/preparo com `visto_em` nulo.
    - `tipo="agendados"` mostra só a lista de agendados; outros valores filtram `Pedido.tipo`.
    - `busca`: se só dígitos (após tirar não-dígitos) com até 3 dígitos → nº do dia; com 4+ → `telefone__contains`; texto → `nome__icontains`. Universo: abertos + `dia_efetivo==hoje`. Resultado vem numa única coluna "Resultado".
  - `total_do_dia(hoje) -> tuple[int, Decimal]`: pedidos com `dia_efetivo==hoje`, sem cancelados (e sem aguardando).
  - `versao_painel(hoje) -> str`: muda quando há histórico novo, `visto_em` novo ou virada do dia (ex.: `f"{hoje}:{max_hist_id}:{max_visto}:{n_vistos}"`).

- [ ] **Step 1: Testes que falham:**
  - `test_colunas_na_ordem_sem_aguardando_no_automatico` / `test_coluna_aguardando_no_manual`.
  - `test_pedido_de_ontem_aberto_fica_nas_colunas_mas_fora_do_total` (Review Focus 3).
  - `test_concluido_so_de_hoje_e_ate_20` (21 pedidos → 20; `todos_concluidos=True` → 21).
  - `test_agendado_conta_no_dia_da_entrega`: feito na segunda (`cenario.fechada`) para quarta → `total_do_dia(quarta)` inclui, `total_do_dia(segunda)` não.
  - `test_promover_agendados_30_min_antes`: 31 min antes → 0; 30 min antes → 1, status preparo, `novos==1`.
  - `test_cancelado_fora_do_total_e_no_concluido`.
  - `test_filtro_tipo_e_contadores`.
  - `test_busca_por_numero_nome_e_telefone_formatado` (Review Focus 4): `"(81) 98888-7777"`, `"988887777"`, `"ana"`, `"3"`.
  - `test_versao_muda_com_historico_e_visto`: igual em duas chamadas seguidas; muda após `avancar` e após `marcar_visto`.
- [ ] **Step 2:** `python -m pytest pedidos/tests/test_painel_consultas.py -q` → falham.
- [ ] **Step 3:** Implementar `pedidos/painel_consultas.py` (`select_related`/`prefetch_related("itens")` para não fazer N consultas).
- [ ] **Step 4:** Rodar o teste da Step 2 + `python -m pytest -q` → passa.
- [ ] **Step 5:** Commit `feat: consultas do painel de pedidos` + `git push`.

### Task 3: Mensagens de WhatsApp do painel

**Files:**
- Create: `pedidos/mensagens_status.py`, `pedidos/tests/test_mensagens_status.py`

**Interfaces:**
- Produces:
  - `MENSAGENS: dict[str, str]` com chaves `"aceito","pronto","saiu","falar","cancelado"`.
  - `mensagem_status(pedido, chave) -> str`; `link_cliente(pedido, chave) -> str` = `https://wa.me/55{pedido.telefone}?text=...` (`urlencode`).
  - `mensagens_disponiveis(pedido) -> list[tuple[str, str]]` → `(chave, rótulo)`; rótulos: "Pedido aceito", "Pronto p/ retirada", "Saiu p/ entrega", "Falar com o cliente", "Avisar cancelamento". Regras: `falar` sempre; `aceito` para delivery/retirada não cancelados; `pronto` só retirada; `saiu` só delivery; `cancelado` só se cancelado. Pedido `local` → só `falar`.
  - `atalho_depois_de(pedido) -> tuple[str, str] | None` → mensagem sugerida após a mudança: status `pronto`+retirada → `pronto`; `saiu` → `saiu`; `cancelado` (delivery/retirada) → `cancelado`; senão `None`.
- Textos exatos (`{nome}` = `pedido.nome`, `{n}` = `pedido.numero`):
  - aceito: `✅ Oi {nome}, seu pedido Nº {n} foi aceito. Estamos preparando tudo.`
  - saiu: `🛵 Seu pedido Nº {n} já está a caminho, {nome}.`
  - pronto: `🛍️ Seu pedido Nº {n} está pronto, {nome}. Pode vir buscar!`
  - falar: `Olá, {nome}! Aqui é da Brasa Burguer, sobre o seu pedido Nº {n}: `
  - cancelado: `🚫 Lamentamos informar que o pedido Nº {n} foi cancelado. Motivo: {motivo}.` — sem `" Motivo: ..."` quando `motivo_cancelamento` vazio.

- [ ] **Step 1: Testes que falham:** `test_textos_exatos` (cada chave), `test_cancelado_sem_motivo`, `test_link_tem_55_e_texto_codificado`, `test_disponiveis_por_tipo` (delivery, retirada, local, cancelado), `test_atalho_depois_de`.
- [ ] **Step 2:** `python -m pytest pedidos/tests/test_mensagens_status.py -q` → falham.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar de novo → passa.
- [ ] **Step 5:** Commit `feat: mensagens de status para o WhatsApp do painel` + `git push`.

### Task 4: Tela do painel (colunas, filtros, busca, total do Dono, navegação)

**Files:**
- Create: `gerenciar/views_pedidos.py`, `gerenciar/templates/gerenciar/pedidos/painel.html`, `.../pedidos/_colunas.html`, `.../pedidos/_cartao.html`, `static/css/painel.css`, `gerenciar/tests/test_painel.py`
- Modify: `gerenciar/urls.py`, `gerenciar/templates/gerenciar/_topo.html`, `gerenciar/tests/test_permissoes.py`, `gerenciar/tests/test_produtos.py:21-44`

**Interfaces:**
- Consumes: `montar_painel`, `promover_agendados`, `total_do_dia`, `versao_painel` (Task 2); `proxima_etapa` (Task 1); `equipe_obrigatorio`, `eh_dono`.
- Produces (rotas, nomes no namespace `gerenciar`):
  - `""` → `views_pedidos.painel` name `"pedidos"` (GET). **A lista de produtos muda para `"produtos/"`** (name `"lista"` continua); ajustar `test_produtos.py` de `"/gerenciar/"` para `reverse("gerenciar:lista")`.
  - `"pedidos/colunas/"` → `views_pedidos.colunas` name `"pedidos_colunas"` (GET; parâmetros `tipo`, `q`, `todos`, `v`).
- Comportamento de `colunas`: chama `promover_agendados(agora)`; se `v` == `versao_painel(hoje)` → **204**; senão devolve `_colunas.html` com `data-versao`, `data-novos`.
- `painel.html`: topo (busca com `hx-get` e `hx-trigger="input changed delay:400ms"`, menu ⋯ com "Finalizar todos"), pílulas de tipo com contador, faixa "Toque para ativar o som dos pedidos" (escondida pelo JS), contêiner `#colunas` com `hx-get` de `pedidos_colunas` a cada 5 s, só com a aba visível (`every 5s [document.visibilityState=='visible']`), enviando a versão atual.
- Bloco `#total-dia` (quantidade + R$ + olho) **só renderizado se `eh_dono`**.
- `_cartao.html`: nº, ícone/rótulo do tipo + origem, "📅 feito em dd/mm" se `agendado_para` e `dia` diferente do dia de entrega, minutos desde `criado_em` (classe `tempo-vermelho` ≥ 40), nome, bairro/mesa, total (riscado se cancelado, com motivo embaixo), Pago/Não pago, botão de `proxima_etapa` (`hx-post` da Task 5, `hx-swap="none"`, com `de`), classe `novo` se `visto_em` nulo. Cartão inteiro abre o detalhe (Task 5).
- Navegação `_topo.html`: abas **Pedidos** (primeira) + Produtos/Categorias/Opções/Loja só para Dono; Equipe vê só Pedidos e Sair. Título do topo vem do bloco da página.
- Requisição HTMX (`HX-Request: true`) sem login em qualquer rota de pedidos → status 200 com header `HX-Redirect: /gerenciar/entrar/`; sem HTMX continua 302.
- `test_permissoes.py`: `ROTAS` ganha um 4º campo `acesso` (`"equipe"` ou `"dono"`); novo teste parametrizado `test_equipe_so_entra_nas_rotas_de_equipe` (equipe → 403 nas de dono, ≠403 nas de equipe). Rotas da Task 5 entram lá também, na Task 5.

- [ ] **Step 1: Testes que falham** em `gerenciar/tests/test_painel.py`:
  - `test_dono_e_equipe_caem_no_painel` (GET `/gerenciar/` → 200 para os dois).
  - `test_equipe_nao_recebe_total_do_dia` (`b'id="total-dia"'` ausente) e `test_dono_recebe_total_do_dia` (presente, com quantidade e valor).
  - `test_equipe_ve_valor_do_pedido` (total do pedido aparece no cartão).
  - `test_colunas_204_quando_versao_igual` e `200` quando diferente, com `data-novos`.
  - `test_cartao_vermelho_aos_40_min` (39 → sem classe; 40 → com classe), usando `criado_em` ajustado.
  - `test_busca_mostra_resultado`, `test_filtro_agendados`.
  - `test_htmx_sem_login_recebe_hx_redirect` (Review Focus 1).
  - `test_equipe_ve_so_aba_pedidos` (sem link de Produtos).
  - `test_permissoes.py` atualizado e `test_todas_rotas_gerenciar_tem_cobertura` passando.
- [ ] **Step 2:** `python -m pytest gerenciar/tests -q` → novos falham.
- [ ] **Step 3:** Implementar views, rotas, templates e `painel.css` (PC: grade de colunas lado a lado; ≤ 760 px: abas de etapa com contador, uma coluna por vez — o JS da Task 6 só troca a classe ativa; sem JS a página ainda mostra as colunas empilhadas).
- [ ] **Step 4:** `python -m pytest -q` → tudo passa.
- [ ] **Step 5:** Commit `feat: painel de pedidos com colunas, filtros e busca` + `git push`.

### Task 5: Detalhe do pedido e ações

**Files:**
- Create: `gerenciar/templates/gerenciar/pedidos/_detalhe.html`, `gerenciar/tests/test_painel_acoes.py`
- Modify: `gerenciar/views_pedidos.py`, `gerenciar/urls.py`, `gerenciar/tests/test_permissoes.py`, `gerenciar/templates/gerenciar/pedidos/painel.html` (contêiner `#detalhe`)

**Interfaces:**
- Consumes: Task 1 (todas as ações), Task 3 (`mensagens_disponiveis`, `link_cliente`, `atalho_depois_de`).
- Produces (rotas, todas `equipe_obrigatorio` salvo indicado; POST levam `de`):
  - `"pedido/<int:pk>/"` name `"pedido"` (GET) → `_detalhe.html` e chama `marcar_visto`.
  - `"pedido/<int:pk>/avancar/"` `"pedido_avancar"`, `"pedido/<int:pk>/voltar/"` `"pedido_voltar"`, `"pedido/<int:pk>/aceitar/"` `"pedido_aceitar"`, `"pedido/<int:pk>/recusar/"` `"pedido_recusar"` (campo `motivo` opcional), `"pedido/<int:pk>/comecar/"` `"pedido_comecar"`, `"pedido/<int:pk>/pago/"` `"pedido_pago"` (campo `pago` = `"1"`/`"0"`).
  - `"pedido/<int:pk>/cancelar/"` `"pedido_cancelar"` — **`dono_obrigatorio`**; motivo vazio → devolve o detalhe com erro "Informe o motivo do cancelamento." e nada muda.
  - `"pedidos/finalizar/"` `"pedidos_finalizar"` (POST) → `finalizar_todos`; o botão pede confirmação com `hx-confirm` mostrando a quantidade ("Finalizar N pedidos?").
- Resposta das ações: o `_detalhe.html` atualizado + header `HX-Trigger` com `{"painel-mudou": true}` e, quando `atalho_depois_de` devolver algo, `{"avisar-whatsapp": {"url": ..., "rotulo": ...}}`. Ação com `de` velho → mesmo retorno (detalhe atual), sem erro.
- `_detalhe.html` (spec 4.2): cabeçalho (nº, tipo, origem, etapa + minutos), cliente/telefone, endereço+referência, "agendado para", itens com opções, observações em destaque amarelo, subtotal/taxa/acréscimo/desconto/total, forma + troco, Pago/Não pago, botão de próxima etapa, "Começar agora" (agendado), Aceitar/Recusar (aguardando), "↩ voltar para …", WhatsApps de `mensagens_disponiveis` (links `target="_blank" rel="noopener"`), Marcar pago/não pago, Cancelar (só Dono; formulário com motivo obrigatório), histórico (hora, etapa, nota, nome do usuário).

- [ ] **Step 1: Testes que falham** em `gerenciar/tests/test_painel_acoes.py`:
  - `test_abrir_detalhe_marca_visto`.
  - `test_avancar_responde_detalhe_e_hx_trigger` (`painel-mudou`).
  - `test_pronto_retirada_sugere_whatsapp` (`avisar-whatsapp` com `wa.me/5581988887777`), `test_pronto_no_local_nao_sugere`.
  - `test_equipe_nao_cancela` (403) e `test_dono_cancela_com_motivo`; `test_cancelar_sem_motivo_mostra_erro`.
  - `test_equipe_pode_recusar` (modo manual).
  - `test_status_velho_nao_quebra` (POST com `de` antigo → 200, status inalterado).
  - `test_finalizar_todos_pela_tela`.
  - `test_detalhe_local_so_tem_falar_com_cliente`.
  - `test_permissoes.py`: todas as rotas novas na tabela (`pedido_cancelar` com acesso `"dono"`, as outras `"equipe"`).
- [ ] **Step 2:** `python -m pytest gerenciar/tests -q` → novos falham.
- [ ] **Step 3:** Implementar views, rotas e template.
- [ ] **Step 4:** `python -m pytest -q` → passa.
- [ ] **Step 5:** Commit `feat: detalhe do pedido com acoes e whatsapp` + `git push`.

### Task 6: Alarme, título, celular e atalho do WhatsApp (JS) + conferência no navegador

**Files:**
- Create: `static/js/painel.js`, `static/js/tests/painel.smoke.js`
- Modify: `gerenciar/templates/gerenciar/pedidos/painel.html` (incluir o JS), `static/css/painel.css`

**Interfaces:**
- Consumes: `data-novos`/`data-versao` em `#colunas` (Task 4); eventos HTMX `painel-mudou` e `avisar-whatsapp` (Task 5).
- Produces (expostos em `window.Painel` para o smoke): `deveTocar(novos: number, somLiberado: boolean) -> boolean`, `tituloPiscando(base: string, novos: number, tick: number) -> string` (alterna entre `base` e `"(N) 🔔 Pedido novo!"`), `abaAtiva(guardada: string|null, colunas: string[]) -> string`.
- Comportamento:
  - Alarme por **WebAudio** (bipe curto repetido a cada ~2 s) enquanto `novos > 0`; para quando `novos == 0`. O som só é liberado depois do primeiro toque na faixa "Toque para ativar o som dos pedidos"; até lá a faixa fica visível e o título pisca mesmo assim.
  - `painel-mudou` → dispara a consulta das colunas na hora (`htmx.trigger`); `visibilitychange` para visível → idem.
  - `avisar-whatsapp` → mostra por ~8 s um botão verde "Avisar no WhatsApp" (link `target="_blank"`, o toque é do usuário, então não é bloqueado como popup).
  - Detalhe: no PC abre como painel lateral à direita sobre as colunas; ≤ 760 px em tela cheia com "← voltar". Fecha com Esc/voltar.
  - Celular: abas de etapa com contador; a aba escolhida fica em `localStorage` (com `try/catch`). Olho do total do dia também em `localStorage`.
- [ ] **Step 1:** Escrever `static/js/tests/painel.smoke.js` (mesmo estilo de `sacola.smoke.js`): carrega o script com `document` falso, confere `deveTocar(1,true)===true`, `deveTocar(0,true)===false`, `deveTocar(1,false)===false`, título alterna com `tick`, `abaAtiva("pronto",[...])==="pronto"` e cai em `"preparo"` quando a guardada não existe.
- [ ] **Step 2:** `node static/js/tests/painel.smoke.js` → falha (arquivo não existe).
- [ ] **Step 3:** Implementar `static/js/painel.js` e ajustes de CSS.
- [ ] **Step 4:** `node static/js/tests/painel.smoke.js` e os outros três smokes → OK; `python -m pytest -q` → passa.
- [ ] **Step 5: Conferência no navegador** (`python manage.py runserver`, Dono e Equipe), em **360 px e 1366 px**: criar pedido pelo site → aparece em ≤ 8 s com alarme e título piscando; abrir no celular apaga o aviso no PC; Pronto → atalho do WhatsApp; Saiu → Entregue; cancelar (Dono) com motivo; modo Manual com Aceitar/Recusar; agendado aparece no filtro; aba escondida e de volta atualiza; nenhuma rolagem horizontal. Anotar o que foi visto no commit.
- [ ] **Step 6:** Commit `feat: alarme e uso no celular do painel de pedidos` + `git push`.
