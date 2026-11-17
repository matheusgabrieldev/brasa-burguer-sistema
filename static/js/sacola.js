/* Sacola do cliente.
   Fica em localStorage["sacola"] = { turno, itens: [{ produto_id, quantidade, opcoes: {id: qtd}, observacao, ...extras de exibição }] }.
   O checkout (plano 2) lê essa mesma chave. O preço que aparece aqui é só de exibição:
   o servidor recalcula tudo em /sacola/validar/ (ao abrir a sacola e, depois, no checkout).
   Aqui ficam também os ajudantes usados pelas outras telas: brl(), esc(), avisar() e csrf(). */
(function () {
  const CHAVE = "sacola";
  const body = document.body;
  const turnoAtual = body.dataset.turno || "";
  const lojaAberta = body.dataset.aberta === "1";
  // Loja fechada mas com abertura prevista: dá para montar um pedido agendado.
  const agendavel = body.dataset.agendavel === "1";

  /* ---------- ajudantes globais ---------- */

  /* Aviso rápido no topo da tela, some sozinho. */
  window.avisar = function (texto, ms = 4000) {
    const el = document.createElement("div");
    el.className = "toast";
    el.setAttribute("role", "status");
    el.textContent = texto;
    el.onclick = () => el.remove();
    document.body.appendChild(el);
    setTimeout(() => el.remove(), ms);
  };

  /* Token de segurança do Django, para os POSTs em JSON (cabeçalho X-CSRFToken). */
  window.csrf = () => document.querySelector('meta[name="csrf-token"]').content;

  window.brl = function (v) {
    return "R$ " + Number(v || 0).toFixed(2).replace(".", ",").replace(/\B(?=(\d{3})+(?!\d),)/g, ".");
  };
  window.esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  };

  /* ---------- estado ---------- */
  /* O estado vive em memória; o localStorage é só uma cópia. Se o navegador bloquear o
     armazenamento (aba privada, etc.), a sacola continua funcionando até recarregar a página. */
  let estado = carregar();

  function carregar() {
    let salvo = null;
    try {
      const s = JSON.parse(localStorage.getItem(CHAVE) || "null");
      if (s && Array.isArray(s.itens)) {
        // descarta itens salvos com formato estranho (para nunca quebrar o resto do código)
        s.itens = s.itens.filter(i => i && typeof i === "object" && Number.isFinite(Number(i.produto_id)) &&
          Number.isInteger(i.quantidade) && i.quantidade >= 1 && i.quantidade <= 50 &&
          i.opcoes && typeof i.opcoes === "object" && !Array.isArray(i.opcoes));
        salvo = s;
      }
    } catch (e) { /* sem armazenamento: começa vazia */ }
    // Sem turno, ou sacola de outro turno (outro dia de funcionamento): começa do zero.
    // Loja fechada NÃO esvazia a sacola por si só (o pedido pode ser agendado).
    if (!salvo || !turnoAtual || salvo.turno !== turnoAtual) return { turno: turnoAtual, itens: [] };
    return salvo;
  }

  function salvar() {
    estado.turno = turnoAtual;
    try { localStorage.setItem(CHAVE, JSON.stringify(estado)); } catch (e) { /* segue só em memória */ }
    desenharBarra();
    // avisa as outras telas (o checkout redesenha os itens)
    if (typeof document.dispatchEvent === "function") document.dispatchEvent(new CustomEvent("sacola:mudou"));
  }

  const mesmoItem = (a, b) =>
    a.produto_id === b.produto_id && (a.observacao || "") === (b.observacao || "") &&
    JSON.stringify(Object.entries(a.opcoes).sort()) === JSON.stringify(Object.entries(b.opcoes).sort());

  let mudancas = 0; // conta as mudanças feitas pelo cliente (adicionar, + e −)

  function adicionar(item) {
    if (!lojaAberta && !agendavel) return;
    mudancas++;
    // item igual a outro que já está na sacola: só soma a quantidade
    const igual = estado.itens.find(i => mesmoItem(i, item));
    if (igual) igual.quantidade = Math.min(50, igual.quantidade + item.quantidade);
    else estado.itens.push(item);
    salvar();
  }

  /* + e − de um item (pela posição na lista). "−" no 1 tira o item. */
  function mudarQtd(idx, delta) {
    const item = estado.itens[idx];
    if (!item) return;
    mudancas++;
    item.quantidade = Math.min(50, item.quantidade + delta);
    if (item.quantidade < 1) estado.itens.splice(idx, 1);
    salvar();
  }

  /* Pedido enviado: esvazia a sacola. */
  function limpar() {
    mudancas++;
    estado.itens = [];
    salvar();
  }

  /* O checkout usa estas funções. conferir() devolve a lista de avisos (itens que saíram). */
  window.Sacola = {
    ler: () => estado, adicionar, mudarQtd, limpar,
    conferir: async () => { avisos = []; await conferir(() => true); return avisos.slice(); },
  };

  /* O produto.js avisa com este evento quando o cliente toca em "Adicionar". */
  document.addEventListener("sacola:adicionar", e => {
    adicionar(e.detail);
    avisar("Adicionado à sacola");
  });

  const totalItem = i => Number(i.preco_unit || 0) * i.quantidade;
  const subtotal = () => estado.itens.reduce((s, i) => s + totalItem(i), 0);
  const qtdTotal = () => estado.itens.reduce((s, i) => s + i.quantidade, 0);

  /* ---------- barra fixa embaixo ---------- */
  const barra = document.getElementById("sacola-bar");
  function desenharBarra() {
    if (!barra) return;
    barra.classList.toggle("hidden", estado.itens.length === 0);
    document.getElementById("sacola-qtd").textContent = qtdTotal();
    document.getElementById("sacola-sub").textContent = brl(subtotal());
    // linha "Pedido agendado para ..." (texto pronto vindo do servidor; textContent não injeta HTML)
    const agenda = document.getElementById("sacola-agenda");
    if (agenda) agenda.textContent = body.dataset.agendamentoTexto || "";
  }
  if (barra) barra.onclick = abrir;
  salvar(); // grava a sacola limpa (quando foi apagada) e desenha a barra

  /* ---------- gaveta da sacola ---------- */
  const raiz = document.getElementById("sacola-raiz");
  let avisos = []; // mensagens de itens que saíram da sacola na última conferência

  let aberta = false; // a gaveta está aberta?
  let versao = 0;     // identifica cada abertura; respostas de aberturas antigas são ignoradas

  function fechar() {
    aberta = false;
    versao++;
    if (raiz) raiz.innerHTML = "";
    body.style.overflow = "";
  }
  document.addEventListener("keydown", e => { if (e.key === "Escape") fechar(); });

  async function abrir() {
    if (!raiz || aberta) return; // toque duplo não abre duas vezes
    aberta = true;
    const meu = ++versao;
    body.style.overflow = "hidden";
    avisos = [];
    desenhar(true);
    await conferir(() => meu === versao);
    if (meu !== versao || !aberta) return; // fechou (ou reabriu) enquanto esperava
    desenhar(false);
  }

  /* Pergunta ao servidor o preço certo de cada item e quais ainda estão disponíveis.
     Se o cliente mexer na sacola durante a espera, descarta a resposta e pergunta de novo (1 vez).
     `ehAtual()` diz se a resposta ainda interessa (a gaveta pode ter sido fechada no meio). */
  async function conferir(ehAtual) {
    for (let tentativa = 0; tentativa < 2; tentativa++) {
      if (!estado.itens.length) return;
      const enviados = estado.itens.slice(); // o "indice" da resposta é a posição nesta lista
      const mudancasAntes = mudancas;
      try {
        const r = await fetch("/sacola/validar/", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
          body: JSON.stringify({
            itens: enviados.map(i => ({ produto_id: i.produto_id, quantidade: i.quantidade, opcoes: i.opcoes, observacao: i.observacao })),
          }),
        });
        if (!r.ok) throw new Error("http " + r.status);
        const dados = await r.json();
        if (!ehAtual()) return;                      // resposta velha: ignora
        if (mudancas !== mudancasAntes) continue;    // sacola mudou no meio: descarta e refaz
        const sairam = new Set();
        dados.removidos.forEach(rem => {
          const it = enviados[rem.indice];
          if (!it) return;
          sairam.add(rem.indice);
          avisos.push(`${it.nome || "Um item"} saiu da sacola: ${rem.motivo}`);
        });
        dados.itens.forEach(sv => {
          const it = enviados[sv.indice];
          if (!it) return;
          const novo = Math.round(Number(sv.preco_unitario) * 100);
          const anterior = it.preco_unit;
          const precoConhecido = (typeof anterior === "number" || typeof anterior === "string") &&
            String(anterior).trim() !== "" && Number.isFinite(Number(anterior));
          // preço diferente do que o cliente viu: o item sai, com aviso (ele adiciona de novo)
          if (precoConhecido && Math.round(Number(anterior) * 100) !== novo) {
            sairam.add(sv.indice);
            avisos.push(`${it.nome || sv.nome} mudou de preço e saiu da sacola. Adicione de novo.`);
            return;
          }
          if (!precoConhecido) it.preco_unit = Number(sv.preco_unitario);
          it.nome = sv.nome;
          it.opcoes_nomes = sv.opcoes.map(o => ({ nome: o.nome, qtd: o.qtd }));
        });
        estado.itens = enviados.filter((_, idx) => !sairam.has(idx));
        salvar();
        return;
      } catch (e) {
        if (ehAtual()) avisos.push("Não consegui conferir os preços agora. O valor final é confirmado ao enviar o pedido.");
        return;
      }
    }
  }

  function linhaOpcoes(i) {
    const ops = (i.opcoes_nomes || []).map(o => (o.qtd > 1 ? `${o.qtd}x ` : "") + o.nome).join(", ");
    return ops + (i.observacao ? (ops ? " · " : "") + "Obs.: " + i.observacao : "");
  }

  /* Desenha a gaveta. Todo texto vindo do produto/cliente passa por esc() (evita injetar HTML). */
  function desenhar(carregando) {
    if (!raiz) return;
    const itens = estado.itens.map((i, idx) => `
      <div class="item-sacola">
        ${i.foto ? `<img src="${esc(i.foto)}" alt="">` : ""}
        <div class="txt"><b>${esc(i.nome)}</b><div class="ops">${esc(linhaOpcoes(i))}</div>
          <span class="stepper"><button type="button" data-menos="${idx}" aria-label="Menos">−</button><span>${i.quantidade}</span><button type="button" data-mais="${idx}" aria-label="Mais">+</button></span>
        </div>
        <div class="lado"><b class="money">${brl(totalItem(i))}</b></div>
      </div>`).join("");
    const lista = estado.itens.length ? itens : `<p class="muted sacola-vazia">Sua sacola está vazia.</p>`;
    raiz.innerHTML = `
      <div class="sheet-fundo" data-sacola-fechar>
        <div class="sheet" role="dialog" aria-label="Sua sacola">
          <div class="sheet-corpo">
            <div class="sacola-topo"><h3>Sua sacola</h3><button class="btn btn-ghost" type="button" data-sacola-fechar>Fechar</button></div>
            ${avisos.map(a => `<div class="sacola-aviso" role="alert">${esc(a)}</div>`).join("")}
            <div class="bloco-lista">${carregando ? `<p class="muted sacola-vazia">Conferindo preços…</p>` : lista}</div>
          </div>
          <div class="sheet-rodape sacola-rodape">
            <span class="sacola-total">Subtotal <b class="money">${brl(subtotal())}</b></span>
            ${estado.itens.length ? `<a class="btn" href="/checkout/">Continuar</a>` : `<button class="btn" type="button" disabled>Continuar</button>`}
          </div>
        </div>
      </div>`;
  }

  if (raiz) {
    raiz.addEventListener("click", e => {
      // fechar: botão "Fechar" ou clique no fundo escuro
      if (e.target.classList.contains("sheet-fundo") || e.target.closest("button[data-sacola-fechar]")) { fechar(); return; }
      // + e − de cada item (aqui não chama o servidor: ele confere ao abrir e no checkout)
      const mais = e.target.closest("[data-mais]"), menos = e.target.closest("[data-menos]");
      if (!mais && !menos) return;
      const idx = Number((mais || menos).dataset[mais ? "mais" : "menos"]);
      mudarQtd(idx, mais ? 1 : -1);
      desenhar(false);
    });
  }
})();
