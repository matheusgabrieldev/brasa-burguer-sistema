# Publicação — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publicar o sistema com PostgreSQL, fotos persistentes, HTTPS e domínio `brasaburguer.com.br`, com restauração e fluxo de pedido verificados.

**Architecture:** Proposta técnica a validar quanto a custo e serviços disponíveis. Django/Gunicorn no Railway, PostgreSQL para dados, WhiteNoise para estáticos e armazenamento de objetos compatível com S3 para fotos via Django Storage. O freio do checkout conta pedidos no próprio PostgreSQL (sem Redis, decisão de 11/11), e django-axes persiste tentativas de login no PostgreSQL. As tarefas 1–3 corrigem requisitos anteriores à publicação, as tarefas 4–8 preparam produção e as tarefas 9–10 dependem dos serviços externos.

**Tech Stack:** Django 5.2, HTMX, JS puro, pytest-django, Node, Gunicorn, psycopg, WhiteNoise, django-storages/boto3 e django-axes. Resolver e fixar versões compatíveis durante a implementação, consultando a documentação oficial de cada integração.

**Spec:** `../docs/PRD-sistema.md` (seções 5, 6, 9, 12–14), `docs/planos/notas-para-plano-2.md` e a divisão dos Planos 3 e 4 em `docs/planos/2026-11-10-checkout-e-pedido.md`.

## Global Constraints

- Textos em português do Brasil e interface utilizável em 360 px.
- Preço sempre recalculado no servidor por `cardapio.precos.calcular_item`.
- PostgreSQL em produção, com cópia diária automática do banco.
- Domínio decidido `brasaburguer.com.br`. A PRD informa que o `.com` pertence ao OlaClick.
- Fotos precisam continuar disponíveis após um deploy e após 17/12/2026, término informado do OlaClick.
- Senha mínima de 10 caracteres. Limitar tentativas em `/gerenciar/entrar/` e `/admin/login/`.
- `manage.py check --deploy` deve passar sem avisos na configuração de produção.
- Preservar checkout, agendamento, idempotência por chave, número diário e configuração pelo Dono.
- Caminhos e comandos deste plano são relativos a `sistema/`, salvo quando indicado. Segredos, dados exportados e fotos ficam fora do Git.
- Este plano termina na publicação verificada. Painel de pedidos, PDV, cozinha e impressão têm planos próprios.

## Review Focus

1. Sacola antiga sem `preco_unit` deve receber o preço recalculado e continuar utilizável. Teste na tarefa 1.
2. Esgotamento deixa um grupo obrigatório impossível de preencher. O produto explica a indisponibilidade e o servidor recusa o pedido. Teste na tarefa 2.
3. Uma nova rota de `gerenciar` pode escapar da lista manual de testes. A enumeração do namespace deve tornar essa omissão visível. Teste na tarefa 3.
4. Workers e solicitações simultâneas devem respeitar o freio de 30 pedidos por rede em dez minutos. A conta é feita no banco, sob a trava do contador do dia (tarefa 7).
5. Banco restaurado ou aplicação redeployada deve continuar encontrando as fotos pelos mesmos nomes e preservar numeração, permissões e pedidos. Testes na tarefa 8 e ensaio na tarefa 9.

## Arquivos e responsabilidades

| Arquivos | Responsabilidade |
| --- | --- |
| `static/js/sacola.js`, `static/js/tests/sacola.smoke.js` | Compatibilidade de preços da sacola |
| `cardapio/disponibilidade.py`, `cardapio/views.py`, `cardapio/precos.py`, `cardapio/templates/cardapio/_produto_modal.html` | Capacidade e disponibilidade efetiva dos grupos |
| `gerenciar/forms_grupos.py`, `gerenciar/views_grupos.py`, `gerenciar/tests/test_grupos.py` | Validar conjunto grupo/opções antes da transação |
| `gerenciar/tests/test_permissoes.py` | Cobrir todas as rotas do namespace |
| `gerenciar/forms.py`, `cardapio/fotos.py`, `gerenciar/tests/test_produtos.py` | Validar foto antes de salvar |
| `config/settings.py`, `requirements-prod.txt`, `.env.exemplo` | Integrações e variáveis de produção |
| `config/tests/test_producao.py`, `gerenciar/tests/test_login.py` | Segurança, estáticos e bloqueio de login |
| `pedidos/limite.py`, `pedidos/views_checkout.py`, `pedidos/servicos.py`, `pedidos/tests/test_checkout.py` | Freio contra robô contado no banco |
| `cardapio/management/commands/importar_cardapio.py`, `cardapio/management/commands/transferir_fotos.py`, `cardapio/tests/test_transferir_fotos.py` | Importação e transporte de mídia pelo Storage |
| `railway.json`, `.python-version`, `README.md`, `docs/publicacao.md` | Build, execução, variáveis, migração e evidências operacionais |

## Requisitos de correção antes do deploy

### Task 1: Sacola com preço ausente

**Files:** Modify `static/js/sacola.js`, `static/js/tests/sacola.smoke.js`.

**Interfaces:** Consome a resposta existente de `POST /sacola/validar/`, com `preco_unitario` decimal em texto. Preserva `window.Sacola` e o formato salvo, preenchendo `preco_unit` numérico quando ausente.

- [x] **Step 1:** Estender o smoke para abrir a sacola e simular a validação assíncrona. Assertar que item sem `preco_unit` recebe 10 e permanece, preço conhecido 9 contra servidor 10 remove com aviso, preço conhecido 0 contra servidor 0 permanece. Assertar que `null`, `""` e texto inválido são tratados como preço desconhecido.
- [x] **Step 2:** Rodar `node static/js/tests/sacola.smoke.js`. Esperado antes da alteração, falha do caso sem preço.
- [x] **Step 3:** Ajustar a comparação em `static/js/sacola.js` para comparar somente preço anterior presente e numérico. Preencher o desconhecido com o valor devolvido pelo servidor antes de salvar. Preservar a proteção existente contra resposta tardia de uma sacola que mudou.
- [x] **Step 4:** Rodar `node static/js/tests/sacola.smoke.js` e `node static/js/tests/checkout.smoke.js`. Esperado, ambos OK.
- [x] **Step 5:** Commit `fix: preservar item antigo da sacola sem preço salvo` com os dois arquivos desta tarefa.

### Task 2: Capacidade dos grupos e indisponibilidade explicada

**Files:** Create `cardapio/disponibilidade.py`; modify `gerenciar/forms_grupos.py`, `gerenciar/views_grupos.py`, `cardapio/views.py`, `cardapio/precos.py`, `cardapio/templates/cardapio/_produto_modal.html`; test `gerenciar/tests/test_grupos.py`, `cardapio/tests/test_views.py`, `cardapio/tests/test_precos.py`.

**Interfaces:** Produz `capacidade_grupo(tipo: str, opcoes: iterable) -> int` e `grupo_disponivel(grupo: GrupoOpcao, hoje: date) -> bool`. Capacidade cadastrada de `unica` é 1 havendo alguma opção, de `varias` é a soma de `qtd_maxima`. Disponibilidade usa somente opções que não estão esgotadas em `hoje`, com mínimo efetivo `max(minimo, 1)` para obrigatório e 0 para opcional.

- [x] **Step 1:** Criar testes com asserts para rejeitar mínimo obrigatório 3 com capacidade 2, rejeitar máximo 4 com capacidade 2, aceitar igualdade, excluir formulários marcados DELETE da capacidade e impedir salvamento parcial do grupo quando o formset é inválido. Validar a capacidade cadastrada sem descontar esgotamentos temporários.
- [x] **Step 2:** Criar testes em que todas as opções obrigatórias estão esgotadas, ou a capacidade disponível fica menor que o mínimo. Assertar texto `Indisponível no momento` e botão Adicionar desabilitado no modal, `PrecoInvalido` no servidor e recuperação automática no dia seguinte. Grupo opcional totalmente esgotado continua permitindo o produto.
- [x] **Step 3:** Rodar `python -m pytest gerenciar/tests/test_grupos.py cardapio/tests/test_views.py cardapio/tests/test_precos.py -q`. Esperado, falhas nos novos casos.
- [x] **Step 4:** Implementar as duas funções e reutilizar a capacidade na validação conjunta de `GrupoForm` e `OpcaoFormSet`. Em `grupo_editar(request, pk=None)`, validar ambos antes de salvar em `transaction.atomic`. Usar disponibilidade no modal e em `calcular_item`, com mensagem indicando o grupo que impede o pedido. Preservar regras existentes para seleção, quantidades e preço.
- [ ] **Step 5:** Rodar o comando da Step 3. Esperado, todos passam. Conferir o modal em 360 px com grupo obrigatório indisponível e opcional esgotado.
- [x] **Step 6:** Commit `fix: validar capacidade e disponibilidade dos grupos` com os arquivos desta tarefa.

Verificação parcial da Step 5 em 10/11. Os 69 testes específicos passaram. A conferência visual em 360 px permanece pendente por indisponibilidade do navegador integrado.

### Task 3: Cobertura automática das permissões

**Files:** Modify `gerenciar/tests/test_permissoes.py`; test `gerenciar/tests/test_loja.py`.

**Interfaces:** Consome `get_resolver()` e o namespace `gerenciar`. As únicas exceções à proteção Dono são `entrar` e `sair`, que mantêm os contratos de autenticação existentes.

- [x] **Step 1:** Adicionar teste que enumera recursivamente os nomes de URL no namespace e asserta igualdade com as rotas protegidas testadas mais as duas exceções explícitas. Uma rota nova sem caso na tabela deve causar falha.
- [x] **Step 2:** Manter asserts por método para anônimo redirecionado ao login e usuário comum recebendo 403. Confirmar teste existente de horário ativo com `fecha <= abre` recusado e horário válido aceito.
- [x] **Step 3:** Rodar `python -m pytest gerenciar/tests/test_permissoes.py gerenciar/tests/test_loja.py -q`. Esperado, passa. Conferir que a enumeração encontra todas as rotas atuais.
- [x] **Step 4:** Commit `test: enumerar permissões de todas as rotas gerenciar` com o teste alterado e eventual teste de horário que faltar.

## Preparação do código de produção

### Task 4: Upload com limite e erro de formulário

**Files:** Modify `gerenciar/forms.py`, `cardapio/fotos.py`, `config/settings.py`; test `gerenciar/tests/test_produtos.py`.

**Interfaces:** Preserva `otimizar_foto(arquivo, lado_max=1000) -> ContentFile` e `ProdutoForm.save(commit=True)`. Define `MAX_FOTO_BYTES = 10 * 1024 * 1024`, decisão deste plano para aceitar fotos comuns de celular.

- [x] **Step 1:** Criar casos que aceitam arquivo válido de até 10 MiB e recusam arquivo acima do limite, imagem inválida e `Image.DecompressionBombError`. Assertar erro no campo `imagem`, resposta de formulário e ausência de gravação de produto/foto em falha.
- [x] **Step 2:** Rodar `python -m pytest gerenciar/tests/test_produtos.py -q`. Esperado, novos casos falham.
- [x] **Step 3:** Validar tamanho e otimizar durante limpeza do formulário, convertendo falhas previstas do Pillow em `ValidationError` em português. Salvar somente a imagem já validada. Manter redução para 1000 px, orientação EXIF, fundo branco e JPEG existentes.
- [x] **Step 4:** Rodar o comando da Step 2. Esperado, passa incluindo criação e edição com foto.
- [x] **Step 5:** Commit `fix: limitar e validar fotos antes de salvar` com os arquivos desta tarefa.

### Task 5: Configuração HTTPS, estáticos e processo de produção

**Files:** Modify `config/settings.py`, `requirements-prod.txt`, `.env.exemplo`, `README.md`; create `config/tests/__init__.py`, `config/tests/test_producao.py`, `railway.json`, `.python-version`.

**Interfaces:** Consome `DEBUG`, `SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`. Produz configuração validada de produção, estáticos coletados e processo Gunicorn ouvindo a porta fornecida pelo ambiente.

- [x] **Step 1:** Criar testes que carregam settings em subprocesso com variáveis explícitas, sem `.env` local. Assertar WhiteNoise após SecurityMiddleware, storage de estáticos comprimidos com manifesto, `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`, cookies seguros, redirect HTTPS, `SECURE_HSTS_SECONDS = 31536000`, include subdomains e preload ativos em produção. Em DEBUG, manter desenvolvimento HTTP utilizável.
- [x] **Step 2:** Rodar `python -m pytest config/tests/test_producao.py -q`. Esperado, falha das configurações ausentes.
- [x] **Step 3:** Permitir `load_dotenv` somente como preenchimento local, com opção explícita `LOAD_DOTENV=0` para subprocessos e produção. Configurar as opções da Step 1, X_FRAME_OPTIONS DENY e validadores de senha com mínimo 10. Exigir em produção banco PostgreSQL e hosts/origens HTTPS explícitos. Documentar o vínculo entre domínio, proxy confiável e CSRF. Comentar que `*` em ALLOWED_HOSTS é exclusivo do exemplo local.
- [ ] **Step 4:** Resolver versões em ambiente Linux compatível e fixar todos os pacotes de `requirements-prod.txt`, incluindo dependências transitivas de produção. Manter o include existente de `requirements.txt`. Selecionar versão Python suportada pelas dependências e gravar `.python-version`. Validar instalação limpa com `pip install -r requirements-prod.txt` e `pip check`.
- [x] **Step 5:** Em `railway.json`, configurar build que instala `requirements-prod.txt` e executa `collectstatic --noinput`; pre-deploy que executa `migrate --noinput`; start com `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2`; healthcheck `/saude/`. Conferir a sintaxe atual no esquema/documentação oficial do Railway na execução. Variáveis de build devem permitir collectstatic sem conexão ao banco ou aos objetos.
- [ ] **Step 6:** Rodar teste da Step 2, `python manage.py collectstatic --noinput` e `python manage.py check --deploy --fail-level WARNING` com ambiente de produção isolado. Esperado, testes passam, coleta termina e zero avisos. Em Linux, iniciar Gunicorn e receber 200 em `/saude/` usando host permitido e cabeçalho HTTPS do proxy.
- [x] **Step 7:** Commit `feat: preparar HTTPS estáticos e execução de produção` com os arquivos desta tarefa.

Execução local. Os 15 testes de configuração passaram, e check --deploy --fail-level WARNING passou sem avisos com configuração isolada. Instalação limpa, lock transitivo, collectstatic e runtime Linux permanecem pendentes.

### Task 6: Bloqueio persistente dos dois logins

**Files:** Modify `config/settings.py`, `requirements-prod.txt`; create `gerenciar/tests/test_login.py`; modify `.env.exemplo`, `README.md`.

**Interfaces:** django-axes com backend de banco, aplicado tanto ao LoginView de `gerenciar` quanto ao Django Admin. Decisão deste plano, cinco falhas por IP em quinze minutos, resposta 429 com texto `Muitas tentativas. Aguarde 15 minutos para tentar novamente.`.

- [x] **Step 1:** Criar testes parametrizados para `/gerenciar/entrar/` e `/admin/login/`, com cinco credenciais incorretas bloqueando a tentativa seguinte mesmo que correta, outro IP livre, liberação após quinze minutos e bloqueio persistindo após limpeza do cache. Assertar que o backend usado é o de banco e que senha de nove caracteres é recusada pelos validadores.
- [x] **Step 2:** Rodar `python -m pytest gerenciar/tests/test_login.py -q`. Esperado, casos novos falham.
- [x] **Step 3:** Integrar django-axes em apps, backends, middleware e configurações usando a API da versão fixada e sua documentação oficial. Configurar IP conforme o proxy verificado, sem aceitar cabeçalho arbitrário direto do cliente. Incluir migrações do pacote no deploy. Documentar procedimento autenticado de desbloqueio pelo comando do pacote.
- [x] **Step 4:** Rodar o comando da Step 2 e `python manage.py check --deploy --fail-level WARNING`. Esperado, passa sem avisos.
- [x] **Step 5:** Commit `feat: limitar tentativas nos logins do dono e admin` com os arquivos desta tarefa.

Executada em 11/11 com django-axes 8.3.1 (a 9.0.0 tinha 12 dias de publicada). O pacote foi para `requirements.txt`, porque `axes` está em INSTALLED_APPS também no desenvolvimento e nos testes. O axes responde 429 já na 5ª senha errada; a 6ª, mesmo correta, continua bloqueada. O IP vem de `pedidos.limite.ip_do_cliente`, a mesma regra do checkout. Errar durante o bloqueio não reinicia os 15 minutos. 17 testes de login e a suíte completa (452) passaram. O `check --deploy --fail-level WARNING` passou sem avisos com ambiente de produção isolado.

### Task 7: Freio contra robô no checkout (sem Redis)

**Decisão do Matheus em 11/11:** o OlaClick não tem limite nenhum, e um limite apertado barraria cliente de verdade (indeciso, mesas, Wi-Fi compartilhado). Ficou só um freio contra robô. Substitui o plano anterior de Redis com cinco envios por IP e telefone.

**Files:** `pedidos/limite.py`, `pedidos/servicos.py`, `pedidos/views_checkout.py`, `pedidos/models.py` (+ migração `0004_ip_hash_freio`), `pedidos/tests/test_checkout.py`.

**Interfaces:** `limite.codigo_ip(ip) -> str` (HMAC, 64 caracteres; o IP não é guardado), `limite.conferir(ip_hash)` levanta `LimiteExcedido`, `criar_pedido(dados, agora=None, ip_hash="")`. 30 pedidos criados em 10 minutos pela mesma rede; telefone sem limite; Dono logado sem freio; tentativas com erro não contam; reenvio da mesma chave sempre passa.

- [x] **Step 1:** Testes: mesmo telefone pede 8 vezes; 4º pedido da mesma rede com limite 3 recebe 429 sem gravar nem pular o número do dia; outra rede livre; libera após 10 min; erros não contam; reenvio na borda passa; Dono sem freio; IP guardado só como código; X-Forwarded-For só com configuração; constantes 30/10 min.
- [x] **Step 2:** Rodados antes da implementação: 6 falharam.
- [x] **Step 3:** Conta feita em `criar_pedido`, dentro da transação, logo depois de `proximo_numero` (que trava a linha do contador do dia), então pedidos simultâneos são serializados no PostgreSQL com qualquer número de workers. Recusa desfaz a transação (o número não é consumido).
- [x] **Step 4:** `python -m pytest -q`: 463 passaram. Três smokes JS OK. `makemigrations --check` sem mudanças.
- [x] **Step 5:** Commit `feat: freio contra robo no checkout contado no banco`.

### Task 8: Fotos em Storage persistente e transporte reproduzível

**Files:** Modify `config/settings.py`, `requirements-prod.txt`, `.env.exemplo`, `cardapio/management/commands/importar_cardapio.py`; create `cardapio/management/commands/transferir_fotos.py`, `cardapio/tests/test_transferir_fotos.py`, `docs/publicacao.md`; test `cardapio/tests/test_importacao.py`.

**Interfaces:** Em produção, `STORAGES["default"]` usa S3Storage com bucket, endpoint, região e credenciais fornecidos pelo serviço contratado. Arquivos públicos de produtos têm URL HTTPS estável de mídia. Em DEBUG, FileSystemStorage continua usando MEDIA_ROOT. WhiteNoise permanece responsável por estáticos.

- [x] **Step 1:** Criar testes de importação com Storage falso, sem dependência de Path(MEDIA_ROOT), verificando nome gravado em `Produto.imagem` e bytes enviados. Para `transferir_fotos --origem <pasta> --manifesto <json>`, assertar preservação dos nomes, repetição sem duplicar, leitura em blocos e saída não zero em arquivo ausente/conflito. Manifesto lista nome, tamanho e SHA-256, sem credenciais.
- [x] **Step 2:** Rodar `python -m pytest cardapio/tests/test_transferir_fotos.py cardapio/tests/test_importacao.py -q`. Esperado, falha dos novos casos.
- [x] **Step 3:** Adaptar o download do importador a `default_storage` e implementar o comando de transferência com verificação de hash dos objetos antes de considerá-los concluídos. Quando o objeto já existir com bytes diferentes, recusar sem sobrescrever. Preservar chaves `produtos/...` e não alterar URLs de fallback manualmente.
- [ ] **Step 4:** Configurar backend/variáveis de Storage. Documentar permissões mínimas necessárias e política de leitura de fotos públicas conforme o provedor real, mantendo listagem e escrita sem acesso público. Não registrar segredos em logs.
- [ ] **Step 5:** Em `docs/publicacao.md`, registrar preparação do conjunto de transporte. Conferir DB versus `media/produtos` (68 arquivos encontrados na revisão inicial, recontar na execução), baixar fotos ainda exclusivamente externas antes de 17/12, verificar bytes e guardar cópia. Incluir `../dados/cardapio-2026-11-05.json` no pacote operacional porque está fora deste Git. Para ambiente novo, passar o caminho explícito ao importador.
- [x] **Step 6:** Documentar transporte do banco existente com `dumpdata --natural-foreign --natural-primary --exclude contenttypes --exclude auth.permission --exclude sessions.session --output <arquivo-fora-do-git>`, snapshot anterior, migrate no PostgreSQL vazio e loaddata controlado. Preservar usuários/grupos e todos os modelos de negócio; verificar se os dados locais são reais ou demonstração antes de escolher importar fixture ou criar base nova pelo JSON. Não rodar reimportação por cima de edições já migradas. Fazer reset das sequences PostgreSQL dos apps importados e testar o próximo pedido.
- [ ] **Step 7:** Rodar os testes da Step 2 e testes de foto da tarefa 4. Esperado, passam com Storage substituído por backend de teste. Conferir que URLs produzidas em produção apontam ao armazenamento persistente.
- [x] **Step 8:** Commit `feat: persistir fotos e documentar transporte de dados` com os arquivos desta tarefa.

Implementação parcial verificada. Comandos e documentação de transporte foram preparados e 91 testes de Storage, importação e fotos passaram. O backend persistente, as URLs remotas, a transferência dos dados reais e o ensaio no provedor permanecem pendentes. A Step 7 cobre somente Storage de teste até integrar o serviço.

## Publicação e dependências externas

### Task 9: Ensaio de restauração e primeiro deploy

**Files:** Modify `docs/publicacao.md`, `README.md` com procedimento e evidências sem segredos.

**Interfaces:** Consome tarefas 1–8 concluídas, projeto Railway, PostgreSQL e bucket disponíveis. Acesso aos serviços e contratação são dependências explícitas do Matheus. Se faltarem, concluir o código e registrar exatamente qual recurso impede cada verificação remota.

- [ ] **Step 1:** Confirmar os acessos ao Git remoto e serviços, titularidade/contratação do domínio e custo real de app, banco, armazenamento e backups dentro do orçamento da PRD. Consultar limites e documentação dos planos efetivamente contratados. Registrar a escolha sem valores presumidos e sem provisionar recursos fora da autorização vigente.
- [ ] **Step 2:** Criar configuração de ambiente a partir do exemplo, com DEBUG=0, LOAD_DOTENV=0, segredo próprio, DATABASE_URL PostgreSQL, REDIS_URL, parâmetros do Storage, hosts explícitos e CSRF_TRUSTED_ORIGINS HTTPS. Configurar IP do proxy somente depois de confirmar cabeçalhos e comportamento do Railway. Validar versão Python, build, migrate e processo usando os arquivos da tarefa 5.
- [ ] **Step 3:** Em ambiente de ensaio, restaurar o pacote da tarefa 8 em banco novo e bucket designado. Comparar contagens e valores relevantes de produtos/grupos/opções/bairros/configuração/clientes/pedidos, usuários/grupos e contador diário. Conferir todos os nomes de imagens referenciados e seu hash. O próximo pedido deve receber numeração válida sem colisão.
- [ ] **Step 4:** Configurar cópia diária automática do PostgreSQL e restaurar uma cópia em banco descartável, verificando pedidos, clientes e numeração. Registrar periodicidade, retenção realmente disponível, responsável e instruções de recuperação. Guardar cópia das fotos e manifesto em local independente do processo de deploy.
- [ ] **Step 5:** Rodar suíte Python e os três smokes JS; instalar dependências em Linux limpo, `pip check`, migrate, collectstatic e `check --deploy --fail-level WARNING`. Esperado, todos passam. Realizar deploy e conferir logs sem dados sensíveis, migrations concluídas e `/saude/` 200.
- [ ] **Step 6:** Enviar foto pela área Dono, confirmar URL HTTPS e bytes, fazer redeploy e confirmar novamente a mesma foto e os dados. Testar CSS/fontes/imagens estáticas com DEBUG=0 e os dois workers. Repetir conferência de contador compartilhado e login bloqueado depois do reinício.
- [ ] **Step 7:** Documentar recuperação do deploy anterior preservando banco/mídia, incluindo limite de reversão quando houver migração de esquema. Registrar evidências e pendências verificáveis em `docs/publicacao.md`.
- [ ] **Step 8:** Commit `docs: registrar ensaio de publicação e restauração` somente com documentação revisada.

### Task 10: Domínio e aceite do fluxo real

**Files:** Modify `docs/publicacao.md`, `README.md` com URL final e evidências.

**Interfaces:** Consome domínio `brasaburguer.com.br` registrado e acesso ao DNS pelo Matheus, deploy saudável e aceite operacional da loja. Registros DNS e emissão de certificado seguem os valores fornecidos pela plataforma em uso.

- [ ] **Step 1:** Configurar domínio na plataforma e DNS usando os valores reais, aguardar propagação e certificado válido. Ajustar hosts e origens confiáveis do aplicativo, mantendo acesso necessário ao healthcheck. Conferir redirect HTTP→HTTPS, ausência de loop, cabeçalhos HSTS e cookies Secure.
- [ ] **Step 2:** Pelo domínio final, testar login/logout do Dono e Admin, POST com CSRF, edição de horário, produto e foto, sacola antiga, produto indisponível, checkout delivery/retirada, Pix/cartão/dinheiro conforme configuração, agendamento fechado, reenvio da mesma chave e acompanhamento. Confirmar WhatsApp com número da loja e texto correto, sem criar pedidos operacionais de teste sem identificação/acordo da equipe.
- [ ] **Step 3:** Confirmar no celular em 360 px e conexão móvel que estáticos e fotos carregam e o timeout de checkout oferece reenvio sem duplicar. Conferir dados no PostgreSQL após cada fluxo e limpar pedidos de teste pelo procedimento acordado com a loja.
- [ ] **Step 4:** Registrar o que está publicado e os recursos operacionais que aguardam Plano 4 antes do período paralelo de 10–17/12. A troca dos links de Instagram, Google, QR e WhatsApp depende de acesso e autorização da loja. O encerramento do OlaClick em 17/12 depende do aceite da operação completa prevista na PRD.
- [ ] **Step 5:** Commit `docs: registrar domínio e aceite da publicação` com URL, data, verificações e pendências externas resolvidas ou explicitamente abertas.

## Dependências externas verificáveis

| Dependência | Responsável/entrada necessária | Tarefas afetadas |
| --- | --- | --- |
| Git remoto e autorização para publicação | Matheus com acesso ao repositório e ambiente | 9 |
| App Railway e PostgreSQL | Matheus, contratação e credenciais do ambiente | 9 |
| Bucket S3 compatível e leitura HTTPS das fotos | Matheus, serviço contratado, endpoint, região e credenciais | 8 integração remota, 9 |
| Backup diário com restauração possível | Serviço contratado e Matheus responsável pela recuperação | 9 |
| Domínio e DNS `brasaburguer.com.br` | Matheus, registro e acesso ao DNS | 10 |
| Dados reais, imagens e configuração comercial | Matheus/Ana, decisão sobre base inicial e conferência de Pix/WhatsApp/pagamentos | 8 transporte, 9–10 |
| Aceite operacional e canais públicos da loja | Ana/Matheus, equipe e acessos aos canais | 10 e transição de dezembro |

## Critério de conclusão

- [ ] Tarefas 1–8 implementadas e verificadas, commits incrementais revisados.
- [ ] Deploy Linux usando dependências fixas e PostgreSQL real, sem avisos de `check --deploy`.
- [ ] Restauração de backup ensaiada e fotos preservadas após redeploy.
- [ ] HTTPS, DNS e fluxo completo de pedido aceitos pelo domínio final.
- [ ] Evidências e pendências externas registradas em `docs/publicacao.md`. Recurso externo pendente mantém a etapa remota correspondente aberta.

## Verificação em 10/11/2026

407 testes Python e três smokes JavaScript passaram após as tarefas 2–4. O check do Django passou. Cardápio, checkout e páginas de login responderam HTTP 200 em localhost:8000. A conferência visual em 360 px permanece pendente. Os pushes foram tentados e falharam na conexão com github.com:443.

## Preparação de produção e fotos

A suíte completa passou com 434 testes. Após a proteção adicional contra backend com sobrescrita ativa, os 91 testes de Storage, importação e fotos passaram. Login persistente e Redis aguardam dependências e verificações reais. Na tarefa 7, testar reenvio de pedido já gravado após expiração do marcador e durante indisponibilidade do cache. Os testes atuais de checkout limpam o cache inteiro, portanto a integração Redis precisa de alias/namespace isolados e limpeza apenas das chaves de teste.
