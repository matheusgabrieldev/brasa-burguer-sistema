# Notas para o plano 2 (vindas da revisão final do plano 1)

Requisitos obrigatórios do plano 2 (checkout + deploy):

1. **Fotos em produção:** `media/` não é versionado e o disco do Railway é apagado a cada deploy. Usar Railway Volume ou armazenamento de objetos, e servir os arquivos. `foto_url` do OlaClick some em 17/12, não serve de reserva.
2. **Estáticos:** whitenoise no MIDDLEWARE e STORAGES.
3. **HTTPS:** `SECURE_PROXY_SSL_HEADER`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT`, HSTS; `CSRF_TRUSTED_ORIGINS` com o domínio (senão todo POST falha atrás do proxy). Rodar `manage.py check --deploy` sem avisos.
4. **Login:** limitar tentativas em /gerenciar/entrar/ e /admin/ (django-axes ou throttle por IP) e senha mínima ≥ 10.
5. **Agendamento × sacola:** hoje loja fechada = turno "" = sacola esvaziada e botão "Loja fechada". O agendamento (PRD 5) só existe com a loja fechada: definir turno da janela de agendamento (ex.: data de `proxima_abertura`) e trocar a regra.
6. **Checkout:** timeout (AbortController) no envio do pedido; item sem `preco_unit` não pode ser tratado como "mudou de preço" se outra parte gravar a sacola.
7. **Upload:** limite de tamanho do arquivo e `DecompressionBombError` virando erro de formulário.
8. Fixar versões em `requirements-prod.txt`; comentário no `.env.exemplo` sobre `ALLOWED_HOSTS=*`.

Antes do plano 3: grupo obrigatório com todas as opções esgotadas (explicar/indisponível); mín/máx vs capacidade das opções; teste de permissão enumerando o namespace `gerenciar`; validar `fecha > abre` ao editar horários.

Do plano 2 (checkout), para o deploy:
9. Limite de pedidos por IP: atrás do proxy do Railway todos os clientes têm o mesmo REMOTE_ADDR. Ligar `CONFIAR_X_FORWARDED_FOR=1` só se o proxy sobrescreve o cabeçalho; senão o limite vale para a loja inteira.
10. O limite usa o cache local de cada processo: com N workers vira 5×N. Usar cache compartilhado (banco ou Redis) em produção.
11. Com DatabaseCache/FileBasedCache, `cache.incr` regrava com o timeout padrão (300 s) e a janela de 10 min vira 5 min deslizante — usar Redis ou trocar por `cache.set(chave, n+1, JANELA)` em `pedidos/limite.py`.

**Resolvido em 11/11:** os itens 10 e 11 deixaram de existir. O limite por cache foi trocado pelo freio contado no banco (Tarefa 7). O item 9 continua valendo: sem `CONFIAR_X_FORWARDED_FOR=1`, o freio vale para a loja inteira (30 pedidos em 10 min, acima do pico real).
