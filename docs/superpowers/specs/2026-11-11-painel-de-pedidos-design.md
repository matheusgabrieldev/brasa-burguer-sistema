# Painel de pedidos — design

11/11/2026 · conversa com o Matheus · base: `../../PRD-sistema.md` seção 6 (fica fora deste git, em `projeto-cliente/docs/`) e `projeto-cliente/docs/olaclick-telas-referencia.md`.
Mockups aprovados (fora do git): `projeto-cliente/.superpowers/brainstorm/1084-1794425446/content/painel-pedidos.html` e `detalhe-pedido.html`.

## 1. Para que serve e por quê

É a tela onde a loja acompanha os pedidos durante a noite. Hoje os pedidos do site já entram no banco e o cliente acompanha o status. Só que a loja **não tem onde ver nem mover esses pedidos**. Sem este painel, o sistema não substitui o OlaClick, que vence em 17/12.

**O momento que importa:** sábado à noite, até ~85 pedidos, com pico entre 18h e 20h. Sucesso é:
- nenhum pedido passa despercebido;
- todo pedido é achado rápido quando o cliente liga;
- o cliente é avisado com 1–2 toques quando o pedido fica pronto ou sai para entrega;
- no fim da noite tudo é fechado de uma vez.

**Quem usa:**
- **Caio**, papel **Equipe**, no **notebook da cozinha**: é o usuário principal, vê o pedido primeiro e move de etapa.
- **Ana e Bia**, papel **Dono**, no **celular Android** e às vezes no notebook.

**Regra do Matheus:** toda tela do `/gerenciar` precisa funcionar bem **no PC e no celular**. Conferir em 360 px e em ~1366 px.

## 2. Objetivos, fora deste trabalho e o que seria fracasso

**Objetivos (esta entrega):**
1. Painel com colunas por etapa, filtro por tipo, busca e atualização sozinha.
2. Aviso de pedido novo: alarme que repete, título da aba piscando e cartão destacado até alguém abrir.
3. Detalhe do pedido com: mudar etapa, voltar etapa, 4 mensagens de WhatsApp prontas, marcar como pago e cancelar com motivo.
4. Entrada **Manual**: coluna "Aguardando aceite" com Aceitar / Recusar.
5. Papel **Equipe** (login do Caio) com as restrições da PRD.
6. "Finalizar todos" no fim da noite.
7. Total do dia, só para o Dono.

**Fora deste trabalho** (outras entregas, nessa ordem no cronograma):
- **PDV:** "+ Novo pedido", desconto e editar itens. Usam o modal de opções do cardápio. No painel, o botão "+ Novo pedido" **não aparece** até o PDV existir.
- **Impressão:** reimprimir e status da impressora (agente local ESC/POS). O indicador "Impressora ok" do mockup **não entra agora**.
- **Entregadores:** atribuir entregador e acerto.
- **Tela da cozinha, esgotado na hora, clientes e PWA.**
- **WhatsApp automático pela API da Meta.** A Ana ainda não decidiu entre botão e API. Esta entrega faz só os botões, que servem nos dois casos. Ver seção 6.

**Seria fracasso, mesmo funcionando:**
- Pedido novo chegar e ninguém perceber, por exemplo porque o som estava bloqueado pelo navegador e nada avisou.
- O Caio (Equipe) ver o faturamento do dia ou conseguir cancelar pedido.
- No celular, ter que rolar para o lado ou errar o toque em botões pequenos.
- O painel ficar lento ou "piscando" a cada atualização no pico.

## 3. Restrições

- Stack existente: **Django 5 + HTMX + PostgreSQL** (SQLite local). Sem WebSocket e sem Redis. A atualização é por consulta periódica (polling).
- Nenhum arquivo passa de **1000 linhas**. O painel fica em arquivos próprios, por exemplo `gerenciar/views_pedidos.py`, templates `gerenciar/pedidos/*.html`, `static/js/painel.js` e `static/css/painel.css`.
- Visual igual ao resto do sistema (tokens de `static/css/base.css`: preto, amarelo de apoio só com texto preto, vermelho só para alertas).
- Fuso de Recife. "Hoje" é o campo `Pedido.dia`.
- Testes com pytest. Toda rota nova entra no teste que enumera as permissões do namespace `gerenciar` (`gerenciar/tests/test_permissoes.py`).
- Commit + push para o GitHub privado a cada tarefa.

## 4. Como funciona (decidido com o Matheus)

### 4.1 Painel — layout (mockup `painel-pedidos.html`, aprovado)
- **Colunas por etapa**, como na PRD: **Em preparo → Pronto → Saiu p/ entrega → Concluído**. Com a entrada Manual ligada, aparece à esquerda a coluna **Aguardando aceite**. Na Automática ela não aparece.
- **Filtro por tipo** em "pílulas" no topo, com contador, do jeito do OlaClick: **Tudo · Delivery · Retirada · No local · Agendados**.
- **Topo:** título, busca (nº, nome ou telefone), total do dia com olho para esconder (só Dono) e menu ⋯ com "Finalizar todos".
- **PC:** as colunas lado a lado. **Celular:** uma etapa por vez, trocando pelas abas de cima com contador, e os filtros logo abaixo.
- **Cartão:** nº, ícone do tipo + origem (Site/PDV), tempo desde a chegada (vermelho depois de 40 min), cliente, bairro ou mesa, total, situação do pagamento e o botão da próxima etapa:
  - Em preparo → **"✓ Pronto"**
  - Pronto + delivery → **"🛵 Saiu para entrega"**
  - Pronto + retirada / no local → **"✓ Entregue"**
  - Saiu → **"✓ Entregue"**
  - Concluído: cartão apagado, sem botão
- **"✓ Entregue" é sugestão do Claude, aprovada pelo Matheus.** Não está na PRD. Ele leva o pedido para Concluído na hora, sem esperar o "Finalizar todos".
- **Pedido novo não aberto:** borda amarela no cartão.
- Tocar no cartão abre o detalhe.

### 4.2 Detalhe do pedido (mockup `detalhe-pedido.html`, aprovado)
- **PC:** painel lateral por cima das colunas. **Celular:** tela cheia com "← voltar".
- Mostra:
  - nº, tipo, origem e etapa com o tempo;
  - cliente e telefone;
  - endereço com referência (delivery);
  - agendado para (se tiver);
  - itens com opções, e as observações do item e do pedido **em destaque amarelo**;
  - subtotal, taxa, acréscimo, desconto e total;
  - forma de pagamento com o troco, e Pago / Não pago;
  - histórico de etapas com horário.
- Botões desta entrega:
  - próxima etapa;
  - 4 WhatsApps: pedido aceito, saiu p/ entrega, pronto p/ retirada, falar com o cliente;
  - marcar como pago / não pago;
  - cancelar com motivo (só Dono).
- Reimprimir, entregador, desconto e editar ficam para as entregas seguintes. Não aparecem nesta entrega.

### 4.3 Papéis
- **Dono** (grupo "Dono" ou superusuário): tudo.
- **Equipe** (grupo novo "Equipe"):
  - vê e move pedidos, marca pago, usa o WhatsApp e "Finalizar todos";
  - **não vê o total do dia nem a quantidade de pedidos do dia** (não aparecem no HTML, nem escondidos). Isso segue a PRD: "não vê faturamento", e o topo com total e quantidade é só do Dono. O **valor de cada pedido continua visível** em todas as colunas, inclusive Concluído, porque o Caio cuida do caixa e do fechamento do dia (PRD seção 3);
  - **não cancela**;
  - **não acessa** produtos, categorias, opções nem loja, que continuam só para o Dono.
- Depois de entrar, os dois papéis caem direto no **painel de pedidos**, que vira a primeira aba do `/gerenciar`.

## 5. Decisões do Claude (o Matheus disse "faça o que achar melhor")

1. **Atualização:** o painel consulta o servidor a cada ~5 s. Para não redesenhar à toa, a consulta só traz as colunas de novo quando algo mudou (por exemplo, comparando uma "versão" calculada dos pedidos abertos). Pausa quando a aba está escondida e atualiza na hora quando ela volta.
2. **Alarme:**
   - Navegadores bloqueiam som antes do primeiro toque na página. Por isso, ao abrir o painel aparece uma faixa **"Toque para ativar o som dos pedidos"**, que some depois do toque.
   - Enquanto o som estiver bloqueado, a faixa continua visível e o título pisca do mesmo jeito.
   - O alarme toca em repetição enquanto existir pedido novo não aberto, nas etapas Aguardando aceite e Em preparo. Para quando todos forem abertos.
   - "Aberto" fica registrado **no servidor**: abrir no notebook apaga o aviso no celular também.
3. **Agendados:**
   - Ficam fora das colunas e só aparecem no filtro "Agendados", que mostra o contador.
   - Passam sozinhos para "Em preparo" **30 min antes** do horário marcado. Isso acontece na própria consulta do painel, sem tarefa agendada no servidor, e entra no histórico.
   - Ao passar, contam como pedido novo (alarme).
   - O detalhe tem um botão **"Começar agora"** para adiantar.
4. **Voltar etapa:** no detalhe, um link discreto "↩ voltar para <etapa anterior>" para desfazer toque errado. Entra no histórico.
5. **Finalizar todos:**
   - Leva para Concluído todos os pedidos em Em preparo, Pronto e Saiu, de qualquer dia.
   - Pede confirmação antes ("Finalizar 12 pedidos?").
   - Não mexe em Aguardando aceite nem em Agendados.
6. **Concluído:**
   - A coluna mostra só os de **hoje**, os mais recentes em cima, com "ver todos" quando passar de ~20.
   - Pedidos abertos de dias anteriores continuam nas colunas, para não sumirem.
7. **Cancelados:**
   - Saem das colunas abertas e aparecem na coluna Concluído com a etiqueta vermelha "Cancelado", o **motivo logo abaixo** e o **total riscado**, como no histórico do OlaClick.
   - Não somam no total do dia.
   - Motivo obrigatório.
8. **Recusar** (entrada Manual):
   - Quem pode: Dono e Equipe. É a porta de entrada, e o Caio precisa conseguir operar o modo Manual. Com isso, o "Equipe não cancela" passa a valer só para pedidos já aceitos.
   - Motivo opcional. Vira "Cancelado" no histórico, com a marca "recusado".
9. **Aceitar:** leva para Em preparo, ou para Agendados se o pedido tiver horário marcado mais de 30 min à frente.
10. **Busca:**
    - Procura entre os pedidos abertos e os de hoje: por nº do dia, parte do nome ou dígitos do telefone.
    - Mostra o resultado no lugar das colunas, com um "✕ limpar".
11. **Quem fez:** o histórico guarda o usuário de cada mudança de etapa, de pagamento e de cancelamento. Precisa de um campo novo em `HistoricoStatus`, mais o motivo do cancelamento.
12. **WhatsApp:**
    - Abre `https://wa.me/55<telefone>?text=...` em nova aba, do mesmo jeito sem popup bloqueado já usado no checkout (commit `cea5a41`).
    - Depois de tocar "Pronto" ou "Saiu para entrega", o cartão mostra por alguns segundos um atalho verde **"Avisar no WhatsApp"** com a mensagem certa. É o "2 toques" da PRD.
13. **Pago / Não pago é só informativo.** No OlaClick, metade dos pedidos finalizados do sábado (08/11) ficou "Não pago", porque a loja não registra o pagamento lá. Por isso nada no painel exige marcar como pago: "Entregue" e "Finalizar todos" funcionam com o pedido em "Não pago".
14. **Total do dia (Dono):** soma de `total` e quantidade dos pedidos de hoje, sem os cancelados. O olho que esconde o valor é preferência do aparelho (localStorage).
15. **Dia de um pedido agendado:**
    - O pedido feito com a loja fechada guarda `dia` e `numero` do dia **em que foi feito**. O número já foi para o cliente na mensagem de confirmação, então **não se renumera**.
    - Para o painel, o "dia" dele é o **da entrega** (data local de `agendado_para`). Isso vale para o total do dia, para a coluna Concluído e para a busca "de hoje". Não precisa de migração: é uma regra de consulta, `dia_efetivo = data(agendado_para) se houver, senão dia`.
    - Para não confundir com outro pedido de mesmo número, o cartão e o detalhe do agendado mostram uma etiqueta "📅 feito em dd/mm".
16. **Cancelar:**
    - O Dono pode cancelar de qualquer etapa, menos de um pedido já cancelado. Isso inclui Agendado e Concluído, para estorno no dia seguinte.
    - O total do dia do pedido é recalculado sozinho, porque é uma consulta.
    - Depois de cancelar ou recusar, o detalhe mostra o atalho **"Avisar no WhatsApp"** com a mensagem de cancelamento, que é o botão manual da PRD seção 9.
17. **Corrida entre dois aparelhos:** cada ação envia a etapa que o aparelho viu. Se no servidor o pedido já mudou, a ação não faz nada e o painel atualiza. Nada de erro na cara do usuário.

## 6. Textos do WhatsApp (rascunho, o Matheus pode ajustar)

Base: os exemplos do chatbot do OlaClick, conferidos em 11/11. São curtos e os clientes já estão acostumados com eles. O OlaClick não manda mensagem de status para pedido "No local", e aqui vale o mesmo: os botões de status só aparecem para Delivery e Retirada. "Falar com o cliente" aparece sempre.

- **Pedido aceito:** "✅ Oi {nome}, seu pedido Nº {n} foi aceito. Estamos preparando tudo."
- **Saiu p/ entrega:** "🛵 Seu pedido Nº {n} já está a caminho, {nome}."
- **Pronto p/ retirada:** "🛍️ Seu pedido Nº {n} está pronto, {nome}. Pode vir buscar!"
- **Falar com o cliente:** "Olá, {nome}! Aqui é da Brasa Burguer, sobre o seu pedido Nº {n}: "
- **Cancelado / recusado:** "🚫 Lamentamos informar que o pedido Nº {n} foi cancelado. Motivo: {motivo}." (sem a frase do motivo quando a recusa não tiver motivo)

Se a Ana escolher a API da Meta, o envio automático liga nas mesmas mudanças "Pronto" e "Saiu para entrega" que este painel cria. Os botões continuam como reserva, que é o caso "mês com mais de 980 mensagens" da PRD.

## 7. O que fica com quem constrói

- A estrutura exata das views, dos parciais HTMX e do JS, desde que respeite o limite de 1000 linhas.
- O cálculo da "versão" do painel e o intervalo exato (entre 3 e 8 s).
- O som do alarme: um arquivo curto e livre de direitos em `static/`.
- Como criar o grupo "Equipe" (migração de dados) e a forma de cadastrar o usuário do Caio (por enquanto pelo `/admin`, ou por comando).
- Detalhes visuais, dentro do mockup e dos tokens de cor.

## 8. Pronto quando

- Pedido criado pelo site aparece no painel em ≤ 8 s, com alarme e título piscando, nas duas larguras.
- Todas as transições da seção 4.1 e da seção 5, com histórico e usuário gravados.
- Equipe: sem o bloco de total e quantidade do dia no HTML, cancelar dá 403, abas do cardápio dão 403.
- Pedido agendado entra no total e no Concluído do dia da entrega, com a etiqueta "feito em".
- Entrada Manual: aceitar e recusar funcionando, e o modo Automático sem a coluna.
- Testes passando, incluindo a enumeração de permissões. Conferido no navegador em 360 px e em ~1366 px.
