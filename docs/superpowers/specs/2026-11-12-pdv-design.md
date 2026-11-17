# PDV (lançar pedido) — design

12/11/2026 · conversa com o Matheus · base: `../../PRD-sistema.md` seção 6, "PDV" (fica fora deste git, em `projeto-cliente/docs/`), e o design do painel (`2026-11-11-painel-de-pedidos-design.md`).

## 1. Para que serve e por quê

Boa parte dos pedidos da loja **não vem do site**: chega pelo WhatsApp, pelo telefone, no balcão e nas mesas. No OlaClick isso é lançado pelo PDV. Sem um PDV, esses pedidos ficam fora do painel (e, depois, fora da impressão e do resumo do dia), e o sistema não substitui o OlaClick em 17/12.

**Quem usa:** Caio (Equipe) no notebook da cozinha, que também cuida do caixa; Ana e Bia (Dono) no celular ou no notebook.

**Sucesso:** lançar um pedido de balcão em menos de 30 s e um delivery por telefone em menos de 1 min, sem digitar o que o sistema já sabe (preço, taxa do bairro, nome e endereço do cliente que já pediu).

## 2. Objetivos, fora deste trabalho e fracasso

**Objetivos:**
1. Tela `/gerenciar/pdv/` aberta pelo botão **"+ Novo pedido"** do painel.
2. Três tipos: **Retirada (balcão)**, **No local** (nome ou nº da mesa) e **Delivery por telefone**.
3. Grade de produtos com **busca** e **categorias**, usando o **mesmo modal de opções** do cardápio.
4. **Item avulso**: nome + valor digitado (o "Produto diversos" de hoje; a Ana confirmou em 12/11 que serve para vender algo à parte).
5. **Desconto** em R$, na hora de lançar **e** depois, pelo detalhe do pedido no painel (PRD: "Desconto (Equipe e Dono)").
6. Ao lançar: o pedido entra em **"Em preparo"** com origem **PDV** e a tela volta para o painel.

**Fora deste trabalho:**
- **Impressão** ao lançar: entra no plano de impressão (o PDV só deixa o pedido pronto para ser impresso).
- **Editar itens** de um pedido já lançado (tirar/trocar/adicionar): próxima entrega, logo depois desta.
- Agendar pedido pelo PDV.
- Esgotado na hora, entregadores, tela da cozinha: planos próprios.
- Vender produto escondido (o caso real era o "Produto diversos", resolvido pelo item avulso).

**Seria fracasso, mesmo funcionando:**
- Lançar o mesmo pedido duas vezes por toque duplo ou internet lenta.
- Perder o pedido montado porque a página recarregou.
- No celular, ter que rolar para o lado ou não achar o botão de lançar.
- O preço do pedido vir do navegador (precisa ser recalculado no servidor, como no site).

## 3. Restrições

- Mesma stack e regras do painel: Django 5 + HTMX, sem Redis, arquivos com no máximo **1000 linhas**, tokens de `static/css/base.css`, fuso de Recife, pytest, commit + push a cada tarefa.
- Toda rota nova entra no teste de permissões do namespace `gerenciar`.
- Funciona em **360 px e ~1366 px**.

## 4. Como funciona

### 4.1 Abordagem (escolhida pelo Matheus: A)

- **A) Tela própria `/gerenciar/pdv/` — escolhida.** Grade à esquerda e comanda à direita no PC; no celular, grade e comanda empilhadas, com uma barra fixa embaixo ("3 itens · R$ 54,00 → Lançar"). Espaço para a grade e JS separado do painel.
- B) PDV como janela por cima do painel: descartada, fica apertada no celular e juntaria dois JS grandes na mesma página.
- C) Reaproveitar o cardápio do cliente: descartada, a PRD manda o PDV usar o cardápio dentro do painel e as regras do checkout do site não servem para o balcão.

### 4.2 Regras do balcão (diferentes do site)

Decididas pelo Matheus em 12/11 (proposta do Claude, sem objeção):
- **Loja fechada não trava** o PDV.
- **Pedido mínimo não vale** no PDV.
- **Produto esgotado trava**: aparece apagado na grade com "Esgotado" e não entra.
- Só aparecem produtos e categorias **visíveis** (o mesmo que o cliente vê).

Iguais ao site: preço recalculado no servidor (`cardapio.precos.calcular_item`), regras dos grupos de opção, taxa do bairro, acréscimo da forma de pagamento, troco, número do dia (`proximo_numero`), chave UUID contra pedido duplicado.

### 4.3 Dados do cliente por tipo

| Tipo | Obrigatório | Opcional |
| --- | --- | --- |
| Retirada | Nome | Telefone |
| No local | "Nome ou mesa" (um campo só, ex.: "Mesa 4") | Telefone |
| Delivery | Telefone, nome, bairro, rua, número | Referência |

- **Delivery por telefone:** ao digitar o telefone, o PDV busca o cliente. Se ele já pediu, preenche o **nome** e o **endereço do último pedido** (bairro, rua, número, referência), que a equipe confere e pode trocar. A regra de privacidade do site ("endereço nunca é achado pelo telefone") vale para o **cliente anônimo no site**; aqui é a loja logada consultando os próprios pedidos.
- **Cliente bloqueado:** aparece um aviso vermelho com o motivo, mas a equipe **pode lançar** (quem decide é quem está falando com ele).
- Telefone informado em Retirada/No local também liga o pedido ao cliente (histórico) e habilita os botões de WhatsApp no painel. Sem telefone, o pedido fica sem cliente e os botões de WhatsApp não aparecem.

### 4.4 Comanda e lançar

- Itens com opções e observação, quantidade com + e −, remover item.
- **Item avulso:** botão "+ Item avulso" → nome, valor e quantidade.
- **Forma de pagamento:** opcional ("Paga depois" é o padrão, porque no balcão e na mesa se paga no fim). Escolhendo uma forma, aplica o acréscimo dela; em Dinheiro, campo de troco. Caixa **"Já está pago"**.
- **Desconto em R$:** não pode passar do valor do pedido.
- **Observação geral** do pedido.
- Totais ao vivo: subtotal, taxa, acréscimo, desconto e total (o navegador só mostra; o servidor recalcula).
- **"Lançar pedido"**: o servidor confere tudo, grava e devolve para o painel, com o pedido em "Em preparo". Erro aparece em cima do campo com problema e a comanda continua montada.

### 4.5 Desconto no detalhe do pedido

- Botão **"Desconto"** no detalhe (Equipe e Dono), em pedido não cancelado.
- Define o valor do desconto (substitui o anterior; 0 tira). Recalcula o total e entra no histórico com quem fez ("desconto R$ 5,00").

### 4.6 Papéis

- Dono e Equipe podem lançar pelo PDV e dar desconto (briefing: "funcionário pode dar desconto").

## 5. Decisões do Claude (marcar se discordar)

1. **Status ao lançar:** sempre "Em preparo", mesmo com a entrada do site em Manual (quem lança já aceitou).
2. **Sem alarme para o próprio PDV:** o pedido nasce com `visto_em` preenchido, para não apitar no aparelho de quem lançou nem no celular da Ana.
3. **Rascunho da comanda** guardado no `sessionStorage` da aba: recarregar a página não perde o pedido montado; lançar ou "Limpar" apaga.
4. **Pedido sem cliente:** `Pedido.cliente` passa a aceitar vazio e `Pedido.telefone` pode ficar em branco (migração). Busca, link `wa.me` e `tel:` do painel precisam tratar telefone vazio.
5. **Item avulso** grava `ItemPedido` com `produto` vazio. Valor entre R$ 0,01 e R$ 9.999,99, nome até 120 letras.
6. **Freio contra robô** não se aplica (é a loja logada).
7. **Regras no servidor** num arquivo próprio (ex.: `pedidos/servicos_pdv.py`) reaproveitando as funções do checkout, sem mudar o comportamento do site.
8. **Modal de opções:** reaproveita o fragmento e o `produto.js` do cardápio. No PDV, o botão "Adicionar" não pode mostrar "Loja fechada" (ver 4.2).

## 6. O que fica com quem constrói

- Estrutura exata das views, parciais HTMX e JS (`static/js/pdv.js`, `static/css/pdv.css`), dentro de 1000 linhas por arquivo.
- Como o modal do cardápio é chamado no PDV (parâmetro, view própria ou flag), desde que o site continue igual.
- Detalhes visuais, dentro dos tokens.

## 7. Pronto quando

- Lançar os três tipos funcionando, com o pedido no painel em "Em preparo", origem PDV, sem alarme.
- Delivery por telefone preenche nome e último endereço de cliente que já pediu; aviso de bloqueado aparece.
- Item avulso, desconto (no PDV e no detalhe), forma de pagamento opcional, troco e "já está pago".
- Esgotado não entra; loja fechada e mínimo não travam.
- Toque duplo em "Lançar" não cria dois pedidos; recarregar não perde a comanda.
- Pedido sem telefone não quebra o painel (busca, detalhe, WhatsApp).
- Testes passando, incluindo a enumeração de permissões. Conferido no navegador em 360 px e ~1366 px.
