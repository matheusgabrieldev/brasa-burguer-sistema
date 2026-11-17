# Sistema Brasa Burguer

Sistema de pedidos para hamburgueria, feito em Django para substituir uma plataforma de delivery terceirizada (OlaClick). Tem cardápio online, sacola e checkout com Pix/cartão/dinheiro, acompanhamento do pedido pelo cliente, mensagens de WhatsApp e uma Área do Dono com painel de pedidos em colunas, cadastro de produtos, bairros, horários e permissões Dono/Equipe.

> Projeto de portfólio. É a cópia de um sistema real feito para cliente, com nome da loja, endereço, telefones, Pix e nomes da equipe trocados por dados fictícios.

**Stack:** Python 3.13 · Django 5.2 · SQLite (dev) / PostgreSQL (produção) · JavaScript puro · django-axes · WhiteNoise · Gunicorn · Railway · pytest (620+ testes)

## Como rodar (Windows)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.exemplo .env
python manage.py migrate
python manage.py importar_cardapio --baixar-fotos
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

Cardápio: http://localhost:8000 · Área do Dono: http://localhost:8000/gerenciar/ · Admin: /admin

## Testes

```
python -m pytest
```

Teste de fumaça do JavaScript da sacola (precisa do Node):

```
node static/js/tests/sacola.smoke.js
node static/js/tests/checkout.smoke.js
```

## Bloqueio de login

`/gerenciar/entrar/` e `/admin/login/` bloqueiam o IP por 15 minutos depois de 5 senhas erradas (django-axes, gravado no banco; reiniciar o servidor não libera). Para liberar antes, no terminal do servidor (Railway → serviço → Shell), que já exige acesso à conta:

```
python manage.py axes_list_attempts      # ver quem está bloqueado
python manage.py axes_reset_ip <ip>      # liberar um IP
python manage.py axes_reset              # liberar todos
```

As tabelas do axes entram pelo `migrate` normal do deploy. O IP usado é o mesmo do freio de pedidos do checkout (30 pedidos por rede em 10 minutos): o `X-Forwarded-For` só é considerado com `CONFIAR_X_FORWARDED_FOR=1`. Sem isso, atrás do proxy do Railway todos aparecem com o mesmo IP e um bloqueio vale para todos. Ligue somente depois de confirmar que o proxy substitui o cabeçalho.

## Configuração de produção

O `railway.json` prepara coleta de estáticos no build, migrações antes do deploy e Gunicorn com dois workers na porta `$PORT`. Configure a raiz do serviço para o diretório que contém esse arquivo. O Python escolhido em `.python-version` é 3.13.18. As dependências diretas de produção têm versões fixas em `requirements-prod.txt`.

Defina no ambiente do servidor `DEBUG=0`, `LOAD_DOTENV=0`, `SECRET_KEY` longo e aleatório, `DATABASE_URL` PostgreSQL, `ALLOWED_HOSTS` com hosts explícitos e `CSRF_TRUSTED_ORIGINS` com as origens HTTPS. O `.env.exemplo` mantém os valores de desenvolvimento e os exemplos comentados de produção. A aplicação recusa configuração de produção sem banco, hosts e origens válidos.

Inclua `healthcheck.railway.app` em `ALLOWED_HOSTS` e o domínio público efetivamente configurado. O healthcheck `/saude/` responde também por HTTP para permitir a verificação interna do Railway. Os demais caminhos redirecionam para HTTPS. A lista CSRF contém os domínios públicos com `https://`, sem caminho ou barra final. O domínio e o certificado precisam estar ativos para conferir os POSTs pelo endereço final. [Healthchecks do Railway](https://docs.railway.com/deployments/healthchecks)

Em produção, o proxy deve substituir `X-Forwarded-Proto` por um valor confiável e restringir acesso direto ao aplicativo. O Django confia nesse cabeçalho para reconhecer HTTPS. Cookies de sessão e CSRF usam Secure, e HSTS vale por um ano, inclui subdomínios e anuncia preload. Todos os subdomínios utilizados precisam suportar HTTPS antes de ativar essa configuração. `CONFIAR_X_FORWARDED_FOR` continua desativado até verificar como o proxy fornece o IP do cliente.

WhiteNoise serve os estáticos comprimidos com manifesto após `collectstatic`. As fotos continuam no Storage de arquivos existente até a tarefa de persistência de mídia. A configuração atual exige PostgreSQL e mantém a integração de objetos (fotos) para a tarefa própria. Não usa Redis. [WhiteNoise com Django](https://whitenoise.readthedocs.io/en/stable/django.html)

Os testes em `config/tests/test_producao.py` importam settings em subprocessos com um `.env` temporário controlado. Verificam as escolhas de configuração e as recusas de ambiente inválido. A verificação do runtime de produção precisa de Linux, pacotes instalados e PostgreSQL do ambiente.

```sh
pip install -r requirements-prod.txt
pip check
python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py check --deploy --fail-level WARNING
gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2
```

Confira `/saude/` com 200 pelo healthcheck e pelo domínio HTTPS, CSS/fontes/imagens estáticas, login e um POST com CSRF. Nesta preparação local, o check --deploy --fail-level WARNING passou sem avisos em processo isolado, usando as bibliotecas PostgreSQL já instaladas no computador. A instalação das versões fixadas, collectstatic e a execução Linux com PostgreSQL/Gunicorn continuam pendentes pelo bloqueio de acesso do shell ao índice de pacotes. O lock transitivo completo também depende dessa instalação limpa.

As versões diretas foram conferidas nas publicações oficiais do [WhiteNoise](https://pypi.org/project/whitenoise/6.12.0/), [psycopg](https://pypi.org/project/psycopg/3.3.8/) e [Gunicorn](https://pypi.org/project/gunicorn/27.0.0/). O arquivo de deploy segue a [referência de configuração do Railway](https://docs.railway.com/config-as-code/reference), e o runtime escolhido consta na [publicação do Python 3.13.18](https://www.python.org/downloads/release/python-31318/).
