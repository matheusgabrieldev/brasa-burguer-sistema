# Fundação + Cardápio Online — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Projeto Django novo em `sistema/`, com banco, cardápio real importado (com as correções) e o cardápio online do cliente funcionando local: cardápio → produto → sacola (sem checkout).

**Architecture:** Django 5.2 com apps por assunto: `loja` (configuração, horário, bairros, formas de pagamento), `cardapio` (categorias, produtos, grupos e opções, importação, preço). O navegador só guarda a sacola (localStorage); todo preço é recalculado no servidor por `cardapio/precos.py`, que o checkout (plano 2) vai reutilizar. HTMX carrega o modal do produto; JS mínimo para a sacola.

**Tech Stack:** Python 3.15, Django 5.2.18, HTMX 2.0.4 (arquivo local em static), Pillow, dj-database-url, pytest + pytest-django. SQLite local; PostgreSQL em produção (plano 2).

**Spec:** `docs/PRD-sistema.md` (seções 5, 6 "Esgotado", 11, 12, 14). Referência visual e de regras: `versao-1-prototipo/codigo-inicial/` (copiar e adaptar, não importar).

## Global Constraints

- Tudo em Python; textos da interface em português do Brasil.
- Código do sistema novo fica em `sistema/` (raiz do projeto). O protótipo não é alterado.
- Fuso: `TIME_ZONE = "America/Recife"`, `LANGUAGE_CODE = "pt-br"`, `USE_TZ = True`.
- Banco por `DATABASE_URL` (dj-database-url); sem variável = `sqlite:///db.sqlite3`. `psycopg` fica só em `requirements-prod.txt` (pode não ter wheel para 3.15 no Windows).
- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` vêm de variáveis de ambiente; `DEBUG` padrão `False` fora do `.env` local.
- Preço **sempre** recalculado no servidor; nunca confiar no valor do navegador.
- Valores em `Decimal` com 2 casas, arredondamento `ROUND_HALF_UP`.
- Observação do item: até **140** caracteres.
- Horário: qua–sáb 18:15–22:30, dom 18:00–22:30, seg e ter fechado. Pedido mínimo R$ 10 (delivery). Prazo "15 - 80 min".
- Visual: Tema 1 do protótipo (fundo #f5f6f8, cartões brancos, principal #111111, apoio #F2B705 sempre com texto preto, alerta #e5483d). Fundo com estampa: variável CSS `--fundo-estampa`, por enquanto `none` (arte do Matheus vem depois).
- O Matheus está aprendendo: docstrings curtas em português explicando o porquê das partes importantes.

## Review Focus

1. **Reimportar o cardápio** perto da entrega (PRD 6, "Carga inicial") não pode duplicar produtos nem apagar edições de foto/visibilidade feitas pelo Dono → importação é *upsert* por `slug`/`codigo` e não mexe em `imagem`, `visivel`, `ordem` de quem já existe. Teste em Task 4.
2. **Sacola antiga com produto que esgotou, sumiu ou mudou de preço** (PRD 5, "Carrinho") → `/sacola/validar/` devolve o item removido com aviso, e o JS mostra o aviso. Teste em Task 6.
3. **Opção manipulada no navegador** (opção de outro produto, opção esgotada, quantidade acima do máximo, grupo única com 2 escolhas) → `PrecoInvalido` com mensagem clara. Testes em Task 5.
4. **Virada do dia / loja fechada com sacola cheia** → sacola tem `turno`; se o turno do servidor mudou ou a loja está fechada, o JS esvazia. Teste do valor de `turno` em Task 3, comportamento conferido manualmente em Task 7.
5. **Horário perto da borda** (18:14 vs 18:15, 22:30 vs 22:31, segunda à noite procurando a próxima abertura, modo forçado) → textos exatos testados em Task 3.

---

### Task 1: Projeto Django em `sistema/`

**Files:**
- Create: `sistema/manage.py`, `sistema/config/{__init__,settings,urls,wsgi,asgi}.py`
- Create: `sistema/requirements.txt`, `sistema/requirements-prod.txt`, `sistema/pytest.ini`, `sistema/.gitignore`, `sistema/.env.exemplo`, `sistema/README.md`
- Create: `sistema/loja/` (app vazio + `views.py` com `saude`)
- Test: `sistema/loja/tests/test_saude.py`

**Interfaces:**
- Produces: `GET /saude/` → `200`, corpo `ok` (usado pelo Railway no plano 2). Apps instalados: `loja`, `cardapio`.

- [ ] **Step 1:** `git init` em `sistema/`; `.gitignore` com `.venv/`, `db.sqlite3`, `media/`, `.env`, `__pycache__/`, `staticfiles/`.
- [ ] **Step 2:** criar venv, `requirements.txt` = `Django==5.2.18`, `Pillow==13.0.0`, `dj-database-url`, `python-dotenv`, `pytest`, `pytest-django` (fixar as versões instaladas). `requirements-prod.txt` = `-r requirements.txt` + `psycopg[binary]`, `gunicorn`, `whitenoise`.
- [ ] **Step 3: teste que falha**

```python
def test_saude(client):
    r = client.get("/saude/")
    assert r.status_code == 200
    assert r.content == b"ok"
```

- [ ] **Step 4:** `pytest loja/tests/test_saude.py -v` → FAIL (404).
- [ ] **Step 5:** `django-admin startproject config .`, apps `loja` e `cardapio`, settings conforme Global Constraints (lê `.env` com python-dotenv), `STATIC_ROOT=staticfiles`, `MEDIA_ROOT=media`, view `saude`.
- [ ] **Step 6:** `pytest -v` → PASS; `python manage.py check` sem avisos.
- [ ] **Step 7:** README com "como rodar" (venv, `migrate`, `importar_cardapio`, `runserver 0.0.0.0:8000`). Commit `chore: cria projeto Django do sistema`.

---

### Task 2: Modelos da loja e do cardápio + admin

**Files:**
- Create: `sistema/loja/models.py`, `sistema/loja/admin.py`
- Create: `sistema/cardapio/models.py`, `sistema/cardapio/admin.py`
- Test: `sistema/loja/tests/test_models.py`, `sistema/cardapio/tests/test_models.py`

**Interfaces:**
- Produces (`loja.models`):
  - `Configuracao` (linha única, `Configuracao.atual() -> Configuracao`): `modo_loja` (`"auto"|"aberta"|"fechada"`, padrão `auto`), `nome`, `slogan`, `endereco`, `whatsapp` (só dígitos, com 55), `instagram`, `chave_pix`, `prazo` (texto), `pedido_minimo: Decimal`, `vias_padrao: int=1`.
  - `Horario`: `dia_semana` (0=seg … 6=dom, único), `abre: time`, `fecha: time`, `ativo: bool`.
  - `Bairro`: `nome` (único), `taxa: Decimal`, `ativo`.
  - `FormaPagamento`: `codigo` (slug único), `nome`, `acrescimo_pct: Decimal`, `aceita_delivery`, `aceita_retirada`, `aceita_local` (todos padrão `True`), `ordem`.
- Produces (`cardapio.models`):
  - `Categoria`: `nome`, `ordem`, `visivel`.
  - `GrupoOpcao`: `codigo` (único, = uuid do OlaClick ou slug), `nome`, `tipo` (`UNICA="unica"`, `VARIAS="varias"`), `minimo`, `maximo`, `obrigatorio`.
  - `Opcao`: `grupo` FK, `nome`, `preco`, `qtd_maxima=1`, `ordem`, `esgotado_em: date|None`; método `esta_esgotada(hoje: date) -> bool` (`esgotado_em == hoje`).
  - `Produto`: `categoria` FK, `slug` (único), `nome`, `descricao`, `preco`, `foto_url`, `imagem` (ImageField `produtos/`), `destaque`, `mais_pedido`, `visivel`, `ordem`, `esgotado_em: date|None`, `grupos` M2M via `ProdutoGrupo(produto, grupo, ordem)`; property `foto` (imagem se houver, senão `foto_url`); método `esta_esgotado(hoje)`.
  - Esgotado guarda **a data**: "volta sozinho no dia seguinte" sem precisar de tarefa agendada. Desmarcar na mão = `esgotado_em=None`.

- [ ] **Step 1: testes que falham**

```python
def test_configuracao_e_linha_unica(db):
    assert Configuracao.atual().pk == Configuracao.atual().pk == 1

def test_produto_esgotado_volta_no_dia_seguinte(db, produto):  # fixture em conftest
    hoje = date(2026, 11, 14)
    produto.esgotado_em = hoje
    assert produto.esta_esgotado(hoje) is True
    assert produto.esta_esgotado(hoje + timedelta(days=1)) is False

def test_foto_usa_url_do_olaclick_quando_sem_imagem(db, produto):
    produto.foto_url = "https://x/a.jpg"
    assert produto.foto == "https://x/a.jpg"
```

- [ ] **Step 2:** `pytest -v` → FAIL (import).
- [ ] **Step 3:** implementar modelos, `makemigrations`, admin com `ProdutoGrupo` e `Opcao` como inlines; `sistema/conftest.py` com fixtures `categoria`, `produto`, `grupo_unica`, `grupo_varias`.
- [ ] **Step 4:** `pytest -v` → PASS.
- [ ] **Step 5:** commit `feat: modelos da loja e do cardápio`.

---

### Task 3: Horário e status da loja

**Files:**
- Create: `sistema/loja/horario.py`
- Test: `sistema/loja/tests/test_horario.py`

**Interfaces:**
- Consumes: `Configuracao`, `Horario` (Task 2).
- Produces:
  - `@dataclass StatusLoja: aberta: bool, texto: str, turno: str`
  - `status_loja(agora: datetime | None = None) -> StatusLoja`
  - `proxima_abertura(agora: datetime) -> datetime | None` (usado no agendamento do plano 2)
  - `turno` = data (`AAAA-MM-DD`) do dia de funcionamento atual quando aberta; quando fechada, `""`. O JS usa para esvaziar a sacola.

- [ ] **Step 1: testes que falham** (fixture cria os 7 `Horario` do PRD; datas: 11/11/2026 é quarta)

```python
@pytest.mark.parametrize("quando, aberta, texto", [
    ("2026-11-11 18:14", False, "Fechado · Abrimos às 18:15"),
    ("2026-11-11 18:15", True,  "Aberto até 22:30"),
    ("2026-11-11 22:30", True,  "Aberto até 22:30"),
    ("2026-11-11 22:31", False, "Fechado · Abrimos amanhã às 18:15"),
    ("2026-11-15 17:00", False, "Fechado · Abrimos às 18:00"),        # domingo
    ("2026-11-16 20:00", False, "Fechado · Abrimos quarta às 18:15"),  # segunda
])
def test_status(db, horarios, quando, aberta, texto): ...

def test_forcar_aberta_e_fechada(db, horarios): ...  # "Aberto agora" / "Fechado no momento"
def test_turno_e_data_quando_aberta_e_vazio_quando_fechada(db, horarios): ...
def test_proxima_abertura_segunda_cai_na_quarta(db, horarios):
    assert proxima_abertura(dt("2026-11-16 20:00")) == dt("2026-11-18 18:15")
```

- [ ] **Step 2:** `pytest loja/tests/test_horario.py -v` → FAIL.
- [ ] **Step 3:** implementar (base: `status_loja` do protótipo, lendo `Horario` do banco em vez do JSON; dia sem `Horario` ativo = fechado).
- [ ] **Step 4:** PASS. Commit `feat: horário e status da loja`.

---

### Task 4: Importar o cardápio do OlaClick (com correções)

**Files:**
- Create: `sistema/cardapio/importacao.py`, `sistema/cardapio/management/commands/importar_cardapio.py`
- Create: `sistema/cardapio/tests/fixtures/cardapio_mini.json` (2 categorias normais + 1 FAVORITE, 3 produtos, os grupos de cebola/retirar/ketchup)
- Test: `sistema/cardapio/tests/test_importacao.py`

**Interfaces:**
- Produces: `importar(dados: dict) -> ResumoImportacao(criados: int, atualizados: int, ausentes: list[str])`; comando `python manage.py importar_cardapio [caminho] [--baixar-fotos]` (padrão `../dados/cardapio-2026-11-05.json`).

Regras de importação (decisões deste plano):
- Categoria `tipo == "FAVORITE"` (Destaques) **não vira categoria**: os produtos dela ganham `destaque=True` no produto da categoria normal (mesmo `slug`).
- Preço = `variantes[0].preco`. `disponivel: SOLD_OUT` do OlaClick é **ignorado** (é estado do momento do levantamento).
- Grupo não obrigatório → `minimo = 0` (OlaClick grava `min: 1` mesmo opcional).
- **Correções do PRD 5:**
  - `9e5f41ff…` "Cebola Crua ou Caramelizada?" → nome "Cebola", `unica`, min 0, max 1, opções "Cebola crua", "Cebola caramelizada", "Sem cebola".
  - `9e5b6281…` "Escolha como deseja a seu hambúrguer" → nome "Quer tirar algum ingrediente?", `varias`, max 2, só "Sem alface" e "Sem tomate".
  - Novo grupo `molho-onion` "Escolha o molho", `unica`, obrigatório, min 1, max 1, opções "Barbecue", "Maionese artesanal"; ligado ao produto "Onion Ring + molho barbecue" como 1º grupo.
- `mais_pedido=True` para: "Brasa Premium", "Combo Brasa Premium", "Cheddar Bacon", "Coalho Nordestino em dobro" (mesma escolha do protótipo; Dono ajusta depois).
- *Upsert*: produto existente (por `slug`) atualiza `nome`, `descricao`, `preco`, `foto_url`, `categoria`, grupos; **não** mexe em `imagem`, `visivel`, `ordem`, `esgotado_em`. Produto do banco que não está no JSON entra em `ausentes` (não é apagado).
- Também cria, se não existirem: `Configuracao` com os dados da loja (nome "Brasa Burguer", slogan "O hambúrguer na brasa do bairro", endereço "Rua das Flores, 120 - Centro, Recife - PE", whatsapp "5581990001234", instagram "brasa.burguer", prazo "15 - 80 min", pedido mínimo 10, chave Pix "81990001234"); os 7 `Horario` a partir de `horarios` do JSON (`is_active`); os bairros (taxa e ativo do JSON); formas de pagamento: Pix 0%, Cartão de crédito 4%, Cartão de débito 1%, Dinheiro 0% com `aceita_delivery=True` (como no OlaClick hoje — **pendência da Ana**, é só um liga/desliga).

- [ ] **Step 1: testes que falham**

```python
def test_cardapio_real(db):
    importar(carregar_json(REAL))
    assert Produto.objects.count() == 69
    assert Categoria.objects.count() == 7
    assert GrupoOpcao.objects.count() == 8
    assert Bairro.objects.count() == 31 and Bairro.objects.filter(ativo=False).count() == 2
    assert Produto.objects.filter(destaque=True).count() == 4
    onion = Produto.objects.get(nome="Onion Ring + molho barbecue")
    primeiro = onion.produtogrupo_set.order_by("ordem").first().grupo
    assert primeiro.obrigatorio and [o.nome for o in primeiro.opcoes.all()] == ["Barbecue", "Maionese artesanal"]
    cebola = GrupoOpcao.objects.get(nome="Cebola")
    assert cebola.tipo == "unica"
    retirar = GrupoOpcao.objects.get(nome="Quer tirar algum ingrediente?")
    assert [o.nome for o in retirar.opcoes.all()] == ["Sem alface", "Sem tomate"]
    assert Horario.objects.get(dia_semana=0).ativo is False  # segunda

def test_reimportar_nao_duplica_e_preserva_edicoes_do_dono(db): ...  # muda visivel/imagem, reimporta, confere
def test_produto_fora_do_json_vai_para_ausentes_e_nao_e_apagado(db): ...
def test_grupo_opcional_fica_com_minimo_zero(db): ...
```

- [ ] **Step 2:** `pytest cardapio/tests/test_importacao.py -v` → FAIL.
- [ ] **Step 3:** implementar `importar` em `transaction.atomic`; o comando imprime o resumo. `--baixar-fotos`: baixa `foto_url` para `media/produtos/` só para produtos sem `imagem` (base: `baixar_fotos` do protótipo; falha de rede só avisa).
- [ ] **Step 4:** PASS. Rodar `python manage.py importar_cardapio --baixar-fotos` de verdade e conferir no /admin.
- [ ] **Step 5:** commit `feat: importa cardápio do OlaClick com correções`.

---

### Task 5: Cálculo de preço no servidor

**Files:**
- Create: `sistema/cardapio/precos.py`
- Test: `sistema/cardapio/tests/test_precos.py`

**Interfaces:**
- Consumes: modelos da Task 2.
- Produces (o checkout do plano 2 usa exatamente isto):
  - `class PrecoInvalido(Exception)` — mensagem pronta para mostrar ao cliente.
  - `@dataclass OpcaoEscolhida: grupo: str, nome: str, qtd: int, preco: Decimal`
  - `@dataclass ItemCalculado: produto: Produto, nome: str, preco_unitario: Decimal, quantidade: int, opcoes: list[OpcaoEscolhida], observacao: str` + property `total`.
  - `calcular_item(produto_id: int, quantidade: int, opcoes: dict[int, int], observacao: str = "", hoje: date | None = None) -> ItemCalculado` (`opcoes` = `{opcao_id: qtd}`).

Regras: produto precisa existir, estar visível e não esgotado; quantidade limitada a 1..50; opção precisa pertencer a um grupo do produto e não estar esgotada; `qtd` da opção ≥1 e ≤ `qtd_maxima` (acima → erro, não corta); grupo `unica` aceita 1 opção; grupo `varias` soma de qtds ≤ `maximo`; grupo obrigatório precisa de ≥ `max(minimo, 1)`; observação cortada em 140; `preco_unitario = produto.preco + Σ(opcao.preco × qtd)`; opções saem na ordem dos grupos do produto.

- [ ] **Step 1: testes que falham**

```python
def test_preco_com_adicionais_vezes_quantidade(db, burger):  # burger R$ 20; bacon R$ 2,50
    item = calcular_item(burger.id, 2, {bacon.id: 2, ponto.id: 1})
    assert item.preco_unitario == Decimal("25.00")
    assert item.total == Decimal("50.00")

def test_obrigatorio_faltando(db, burger):
    with pytest.raises(PrecoInvalido, match="escolha uma opção em 'Escolha o ponto da carne'"): ...
def test_opcao_de_outro_produto(db, burger, batata): ...       # "Opção inválida"
def test_opcao_esgotada_hoje(db, burger): ...                  # "Bacon está esgotado"
def test_produto_esgotado_ou_oculto(db, burger): ...           # "não está mais disponível"
def test_unica_com_duas_escolhas(db, burger): ...
def test_qtd_acima_do_maximo(db, burger): ...
def test_observacao_cortada_em_140(db, burger): ...
```

- [ ] **Step 2:** FAIL. **Step 3:** implementar (base: laço de itens de `criar_pedido` no protótipo). **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: cálculo de preço no servidor`.

---

### Task 6: Cardápio online — página, modal do produto e validação da sacola

**Files:**
- Create: `sistema/cardapio/views.py`, `sistema/cardapio/urls.py`
- Create: `sistema/templates/base_cliente.html`, `sistema/cardapio/templates/cardapio/{cardapio,_produto_modal}.html`
- Create: `sistema/static/css/{base,cliente}.css`, `sistema/static/js/{cardapio,produto,sacola}.js`, `sistema/static/vendor/htmx.min.js` (2.0.4), fontes e imagens copiadas de `versao-1-prototipo/codigo-inicial/core/static/core/`
- Create: `sistema/cardapio/templatetags/brl.py` (filtro `brl`: `Decimal("1234.5")` → `"R$ 1.234,50"`)
- Test: `sistema/cardapio/tests/test_views.py`

**Interfaces:**
- Consumes: `status_loja` (Task 3), `calcular_item`/`PrecoInvalido` (Task 5).
- Produces:
  - `GET /` → cardápio. Contexto: `loja` (Configuracao), `status` (StatusLoja), `categorias` (visíveis, com produtos visíveis), `destaques`, `hoje`. `<body data-turno="{{ status.turno }}" data-aberta="1|0">`.
  - `GET /produto/<slug>/` → fragmento HTML do modal (HTMX), `404` se oculto. Campo observação com `maxlength="140"`.
  - `POST /sacola/validar/` JSON `{"itens":[{"produto_id","quantidade","opcoes":{"<id>":qtd},"observacao"}]}` → JSON `{"itens":[{indice, nome, preco_unitario, total, opcoes:[...]}], "removidos":[{"indice", "motivo"}], "subtotal": "0.00"}`. Valores como string com 2 casas. Item com `PrecoInvalido` vai para `removidos` com a mensagem.

- [ ] **Step 1: testes que falham**

```python
def test_cardapio_mostra_produtos_visiveis_e_esconde_ocultos(client, cardapio_basico): ...
def test_produto_esgotado_aparece_com_selo_e_sem_botao(client, cardapio_basico):
    # HTML contém "Esgotado" e não contém o link do modal daquele produto
def test_status_fechado_aparece_no_topo(client, cardapio_basico, loja_fechada):
    assert "Fechado no momento" in client.get("/").content.decode()
def test_modal_tem_contador_obrigatorio(client, burger):
    assert "0/1 OBRIGATÓRIO" in client.get(f"/produto/{burger.slug}/").content.decode()
def test_modal_de_produto_oculto_da_404(client, burger): ...
def test_validar_sacola_recalcula_e_remove_esgotado(client, burger, batata):
    # batata esgotada hoje -> sai em "removidos" com motivo; burger volta com preco do banco
    # mesmo que o navegador mande "preco": "0.01"
def test_brl():
    assert brl(Decimal("1234.5")) == "R$ 1.234,50"
```

- [ ] **Step 2:** FAIL. 
- [ ] **Step 3:** views + templates. Layout e CSS: adaptar `cardapio.html`, `base_cliente.html`, `cliente.css`, `base.css` do protótipo, **só Tema 1** (remover `[data-tema="2"]` e troca de tema). Banner, logo, nome, endereço, status, prazo, pedido mínimo, categorias fixas ao rolar, busca (filtra no navegador), Destaques, selo "Mais pedido", esgotado apagado. Botão "Calcular taxa de entrega" abre lista de bairros ativos com taxa (sem navegar). `body` usa `background-image: var(--fundo-estampa)`.
- [ ] **Step 4:** PASS. Commit `feat: cardápio online e modal do produto`.

---

### Task 7: Sacola no navegador

**Files:**
- Modify: `sistema/static/js/sacola.js`, `sistema/static/js/produto.js`, `sistema/cardapio/templates/cardapio/cardapio.html`
- Test: manual (passos abaixo) + `test_views.py` já cobre o servidor

**Interfaces:**
- Consumes: `POST /sacola/validar/`, `data-turno`/`data-aberta` (Task 6).
- Produces: `localStorage["sacola"] = {"turno": "AAAA-MM-DD", "itens": [{produto_id, quantidade, opcoes: {id: qtd}, observacao}]}` — o checkout (plano 2) lê esta chave. Envolver todo acesso em `try/catch`.

Comportamento:
- Ao carregar: se `data-aberta="0"` ou `turno` salvo ≠ `data-turno` → apaga a sacola.
- "Adicionar R$ X" no modal soma à sacola (preço exibido vem do servidor). Barra fixa embaixo com quantidade e subtotal.
- Abrir a sacola chama `/sacola/validar/`; itens em `removidos` saem com aviso ("X saiu da sacola: está esgotado"). Itens com + / −; "Continuar" leva a `/checkout/` (página ainda não existe → por enquanto botão desabilitado com texto "Checkout em breve").
- Loja fechada: botão de adicionar fica desabilitado com "Loja fechada" (agendamento vem no plano 2).

- [ ] **Step 1:** implementar (base: `sacola.js`/`produto.js` do protótipo).
- [ ] **Step 2: conferência manual** com `runserver` e `importar_cardapio`:
  1. Adicionar "Brasa Premium" com 2 bacons → subtotal certo.
  2. No /admin marcar o produto como esgotado hoje → reabrir a sacola → some com aviso.
  3. Forçar loja fechada no /admin → recarregar → sacola vazia e botões desabilitados.
  4. Abrir no celular (mesma rede) pela largura de 360 px: sem rolagem horizontal.
- [ ] **Step 3:** `pytest -v` completo → tudo PASS. Commit `feat: sacola no navegador`.

---

### Task 8: Área do Dono — produtos e categorias pelo celular

**Files:**
- Create: `sistema/gerenciar/` (app): `views.py`, `forms.py`, `urls.py`, `templates/gerenciar/{base,entrar,lista,produto,categorias}.html`
- Create: `sistema/cardapio/fotos.py` (`otimizar_foto(arquivo, lado_max=1000) -> ContentFile`, base: protótipo)
- Create: `sistema/static/css/gerenciar.css`
- Test: `sistema/gerenciar/tests/test_produtos.py`

**Interfaces:**
- Consumes: modelos da Task 2.
- Produces:
  - Grupo de usuários `Dono` (criado por migração de dados). Decorator `dono_obrigatorio` em `gerenciar/permissoes.py`: sem login → `/gerenciar/entrar/`; logado sem ser Dono → 403. (Equipe/Entregador ficam para o plano 3.)
  - Rotas: `/gerenciar/` (lista por categoria, busca), `/gerenciar/produto/novo/`, `/gerenciar/produto/<id>/` (editar), `POST /gerenciar/produto/<id>/visivel/` (alternar, HTMX), `POST /gerenciar/produto/<id>/excluir/` (com confirmação), `POST /gerenciar/produto/<id>/mover/` (`direcao=cima|baixo`), `/gerenciar/categorias/` (criar, renomear, ocultar, reordenar).
- Produto: nome, descrição, preço (aceita "12,50"), categoria, foto (upload → `otimizar_foto`), destaque, mais pedido, visível, grupos de opção ligados (com ordem). `slug` gerado do nome, único (sufixo `-2`, `-3`).
- Excluir produto: apaga de verdade. Pedidos antigos não quebram porque o item do pedido guarda nome e preço (plano 2 usa `on_delete=SET_NULL`). Excluir categoria só se estiver vazia (mensagem: "Mova ou exclua os produtos antes").

- [ ] **Step 1: testes que falham**

```python
def test_sem_login_vai_para_entrar(client): ...
def test_usuario_sem_grupo_dono_recebe_403(client, usuario_comum): ...
def test_dono_cria_produto_com_preco_em_reais(client_dono, categoria):
    client_dono.post("/gerenciar/produto/novo/", {"nome": "X Teste", "preco": "12,50", "categoria": categoria.id, ...})
    assert Produto.objects.get(nome="X Teste").preco == Decimal("12.50")
def test_slug_repetido_ganha_sufixo(client_dono, categoria): ...
def test_ocultar_tira_do_cardapio(client_dono, client, produto): ...  # some de "/"
def test_excluir_produto(client_dono, produto): ...
def test_nao_exclui_categoria_com_produto(client_dono, produto): ...
def test_foto_enviada_vira_jpeg_de_ate_1000px(client_dono, produto): ...  # PNG 3000x2000 -> JPEG 1000x667
```

- [ ] **Step 2:** FAIL. **Step 3:** implementar (base: `views_gerenciar.py`, `forms.py` e templates do protótipo; telas pensadas para celular). **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: dono gerencia produtos e categorias`.

---

### Task 9: Área do Dono — grupos de opção

**Files:**
- Modify: `sistema/gerenciar/{views,forms,urls}.py`
- Create: `sistema/gerenciar/templates/gerenciar/{grupos,grupo}.html`
- Test: `sistema/gerenciar/tests/test_grupos.py`

**Interfaces:**
- Produces: `/gerenciar/grupos/` (lista com quantos produtos usam cada um), `/gerenciar/grupo/novo/`, `/gerenciar/grupo/<id>/` — nome, tipo (única/várias), mín, máx, obrigatório e as opções num formset (nome, preço, qtd máx, ordem; adicionar e remover linha).
- Validação: `minimo <= maximo`; obrigatório exige `minimo >= 1`; tipo única força `maximo = 1`. Excluir grupo usado por produto pede confirmação mostrando os produtos afetados.

- [ ] **Step 1: testes que falham**

```python
def test_cria_grupo_com_opcoes(client_dono): ...
def test_minimo_maior_que_maximo_da_erro(client_dono): ...
def test_unica_forca_maximo_1(client_dono): ...
def test_editar_preco_da_opcao_reflete_no_calculo(client_dono, burger, bacon):
    # muda bacon para 3,00 -> calcular_item usa 3,00
```

- [ ] **Step 2:** FAIL. **Step 3:** implementar. **Step 4:** PASS; `pytest -v` completo.
- [ ] **Step 5:** commit `feat: dono gerencia grupos de opção`.

---

## Próximos planos (não fazem parte deste)

2. Checkout + clientes (lembrar de mim, bloqueio) + agendamento + pedido + mensagem WhatsApp + deploy (Railway + domínio) — **trava em "dinheiro no delivery" (Ana), ~13/11**.
3. Painel de pedidos, PDV, esgotado na hora, login por função (Equipe/Entregador), botões de WhatsApp, Dono edita bairros/taxas, horários, chave Pix, acréscimos e pedido mínimo.
4. Programa de impressão (ESC/POS) + entregadores + resumo do dia.
