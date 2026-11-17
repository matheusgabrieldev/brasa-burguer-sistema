/* Checkout: itens da sacola, endereço, pagamento, resumo e envio do pedido.
   Os dados fixos (taxas, formas, endereços deste aparelho) vêm do servidor em #dados-checkout.
   O total mostrado aqui é só para o cliente ver; o servidor recalcula tudo ao receber. */
(function () {
  const D = JSON.parse(document.getElementById("dados-checkout").textContent);
  const $ = s => document.querySelector(s);
  const $$ = s => [...document.querySelectorAll(s)];
  const btn = $("#enviar");
  const travado = btn.disabled; // loja fechada sem horário: o servidor já mandou o botão desligado
  const TEXTO_BOTAO = btn.textContent;
  const RASCUNHO = "checkout-rascunho"; // formulário guardado antes de recarregar a página

  /* ---------- ajudantes ---------- */

  // WhatsApp: formata enquanto digita -> (81) 9 8888-7777
  function mascaraTel(v) {
    let d = String(v || "").replace(/\D/g, "");
    if (d.length > 11 && d.startsWith("55")) d = d.slice(2);
    d = d.slice(0, 11);
    if (d.length <= 2) return d.length ? `(${d}` : "";
    if (d.length <= 6) return `(${d.slice(0, 2)}) ${d.slice(2)}`;
    if (d.length <= 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
    return `(${d.slice(0, 2)}) ${d.slice(2, 3)} ${d.slice(3, 7)}-${d.slice(7)}`;
  }
  const soValor = v => v.replace(/[^\d,.]/g, ""); // troco: só números, vírgula e ponto
  const centavos = v => Math.round(Number(v || 0) * 100);

  // Chave do pedido: criada uma vez e reaproveitada nos reenvios (evita pedido em dobro).
  function novaChave() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    // reserva para navegador antigo: UUID versão 4 montado na mão
    const b = new Uint8Array(16);
    if (window.crypto && crypto.getRandomValues) crypto.getRandomValues(b);
    else for (let i = 0; i < 16; i++) b[i] = Math.floor(Math.random() * 256);
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    const h = [...b].map(x => x.toString(16).padStart(2, "0")).join("");
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
  }
  let chave = null;

  /* ---------- itens ---------- */
  const itens = () => Sacola.ler().itens;
  const subtotalCent = () => itens().reduce((s, i) => s + centavos(i.preco_unit) * i.quantidade, 0);

  function linhaOpcoes(i) {
    const ops = (i.opcoes_nomes || []).map(o => (o.qtd > 1 ? `${o.qtd}x ` : "") + o.nome).join(", ");
    return ops + (i.observacao ? (ops ? " · " : "") + "Obs.: " + i.observacao : "");
  }

  function desenharItens() {
    const lista = itens();
    $("#vazia").classList.toggle("hidden", lista.length > 0);
    $("#tem-itens").classList.toggle("hidden", lista.length === 0);
    // todo texto do produto/cliente passa por esc() (evita injetar HTML)
    $("#lista-itens").innerHTML = lista.map((i, idx) => `
      <div class="item-sacola">
        ${i.foto ? `<img src="${esc(i.foto)}" alt="">` : ""}
        <div class="txt"><b>${esc(i.nome)}</b><div class="ops">${esc(linhaOpcoes(i))}</div>
          <span class="stepper"><button type="button" data-ck-menos="${idx}" aria-label="Menos">−</button><span>${i.quantidade}</span><button type="button" data-ck-mais="${idx}" aria-label="Mais">+</button></span>
        </div>
        <div class="lado"><b class="money">${brl(centavos(i.preco_unit) * i.quantidade / 100)}</b></div>
      </div>`).join("");
    total();
  }

  /* ---------- tipo, pagamento e total ---------- */
  const tipo = () => ($("input[name=tipo]:checked") || {}).value;
  const pag = () => ($("input[name=pag]:checked") || {}).value;

  function total() {
    const sub = subtotalCent();
    const entrega = tipo() === "delivery";
    const bairro = $("#bairro").value;
    const taxa = entrega && bairro ? centavos(D.bairros[bairro]) : 0;
    const f = D.formas[pag()];
    const acr = f ? Math.round((sub + taxa) * Number(f.pct) / 100) : 0;
    $("#r-sub").textContent = brl(sub / 100);
    $("#linha-taxa").classList.toggle("hidden", !entrega);
    $("#r-taxa").textContent = bairro ? brl(taxa / 100) : "escolha o bairro";
    $("#linha-acr").classList.toggle("hidden", !acr);
    $("#r-acr").textContent = brl(acr / 100);
    $("#r-total").textContent = brl((sub + taxa + acr) / 100);
    const minimo = centavos(D.pedido_minimo);
    const abaixo = entrega && sub > 0 && sub < minimo;
    $("#aviso-minimo").classList.toggle("hidden", !abaixo);
    $("#aviso-minimo").textContent = abaixo ? `Pedido mínimo para entrega: ${brl(minimo / 100)}.` : "";
  }

  function ajustarTipo() {
    const t = tipo();
    $("#campos-entrega").classList.toggle("hidden", t !== "delivery");
    const info = $("#info-retirada");
    if (info) info.classList.toggle("hidden", t === "delivery");
    // só as formas que aceitam este tipo de pedido
    let visiveis = 0;
    $$(".pag").forEach(l => {
      const aceita = (l.dataset.tipos || "").split(" ").includes(t);
      l.classList.toggle("hidden", !aceita);
      if (!aceita) l.querySelector("input").checked = false;
      else visiveis++;
    });
    $("#sem-forma").classList.toggle("hidden", visiveis > 0);
    ajustarPag();
  }

  function ajustarPag() {
    $("#campo-troco").classList.toggle("hidden", pag() !== "dinheiro");
    total();
  }

  /* ---------- "Usar cadastro anterior" (endereços salvos neste aparelho) ---------- */
  function usarEndereco(e) {
    $("input[name=tipo][value=delivery]").checked = true;
    $("#bairro").value = e ? String(e.bairro_id) : "";
    $("#rua").value = e ? e.rua : "";
    $("#numero").value = e ? e.numero : "";
    $("#ref").value = e ? e.referencia : "";
    ajustarTipo();
  }

  /* ---------- erros ---------- */
  function limparErro() {
    $("#erro").textContent = "";
    $$(".com-erro").forEach(el => el.classList.remove("com-erro"));
  }
  function mostrarErro(texto, campo) {
    $("#erro").textContent = texto;
    const alvo = campo && $(`[data-campo="${campo}"]`);
    if (alvo) {
      alvo.classList.add("com-erro");
      alvo.scrollIntoView({ behavior: "smooth", block: "center" });
      if (alvo.focus) alvo.focus({ preventScroll: true });
    }
  }

  /* ---------- rascunho (para recarregar a página sem perder o que foi digitado) ---------- */
  const CAMPOS = ["nome", "tel", "bairro", "rua", "numero", "ref", "obs", "troco"];
  function guardarRascunho(aviso) {
    const r = { aviso, tipo: tipo(), pag: pag(), lembrar: $("#lembrar").checked };
    CAMPOS.forEach(id => (r[id] = $("#" + id).value));
    r.horario = ($("#horario") || {}).value || "";
    try { sessionStorage.setItem(RASCUNHO, JSON.stringify(r)); } catch (e) { /* sem armazenamento */ }
  }
  function lerRascunho() {
    let r = null;
    try { r = JSON.parse(sessionStorage.getItem(RASCUNHO) || "null"); sessionStorage.removeItem(RASCUNHO); } catch (e) { /* nada */ }
    return r && typeof r === "object" ? r : null;
  }

  /* ---------- envio ---------- */
  function corpo() {
    const h = $("#horario");
    return {
      chave, tipo: tipo(), nome: $("#nome").value, telefone: $("#tel").value,
      bairro_id: $("#bairro").value, rua: $("#rua").value, numero: $("#numero").value, referencia: $("#ref").value,
      pagamento: pag() || "", troco_para: pag() === "dinheiro" ? $("#troco").value : "",
      observacao: $("#obs").value, agendar_para: h ? h.value : "", lembrar: $("#lembrar").checked,
      itens: itens().map(i => ({ produto_id: i.produto_id, quantidade: i.quantidade, opcoes: i.opcoes, observacao: i.observacao })),
    };
  }

  let enviando = false;
  async function enviar(e) {
    e.preventDefault();
    if (enviando || travado) return;
    limparErro();
    if (!itens().length) { mostrarErro("Sua sacola está vazia."); return; }
    const horario = $("#horario");
    if (horario && !horario.value) { mostrarErro("Escolha o horário do pedido.", "horario"); return; }
    chave = chave || novaChave();
    enviando = true;
    btn.disabled = true;
    btn.textContent = "Enviando…";
    const ctrl = new AbortController();
    const relogio = setTimeout(() => ctrl.abort(), 20000); // 20 s sem resposta: desiste e deixa tentar de novo
    try {
      const r = await fetch("/checkout/enviar/", {
        method: "POST", signal: ctrl.signal,
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
        body: JSON.stringify(corpo()),
      });
      const j = await r.json().catch(() => ({}));
      if (r.status === 201 && j.url) {
        Sacola.limpar();
        location.href = j.url;
        return; // botão segue desligado até a outra página abrir
      }
      if (j.campo === "horario") {
        // a loja abriu ou fechou (ou o horário saiu da lista) enquanto o cliente preenchia:
        // recarrega para ver o modo e os horários atuais. A sacola fica no localStorage.
        guardarRascunho(j.erro);
        location.reload();
        return;
      }
      mostrarErro(j.erro || "Não foi possível enviar. Tente de novo.", j.campo);
    } catch (err) {
      mostrarErro(err && err.name === "AbortError" ? "A internet está lenta. Tente de novo." : "Sem conexão. Confira a internet e tente de novo.");
    } finally {
      clearTimeout(relogio);
    }
    enviando = false;
    btn.disabled = false;
    btn.textContent = TEXTO_BOTAO;
  }

  /* ---------- eventos ---------- */
  document.addEventListener("click", e => {
    const mais = e.target.closest("[data-ck-mais]"), menos = e.target.closest("[data-ck-menos]");
    if (mais || menos) Sacola.mudarQtd(Number((mais || menos).dataset[mais ? "ckMais" : "ckMenos"]), mais ? 1 : -1);
    const usar = e.target.closest("[data-usar]");
    if (usar) usarEndereco(D.enderecos[Number(usar.dataset.usar)]);
    if (e.target.closest("#outro-endereco")) { usarEndereco(null); $("#bairro").focus(); }
  });
  document.addEventListener("sacola:mudou", desenharItens);
  $$("input[name=tipo]").forEach(r => (r.onchange = ajustarTipo));
  $$("input[name=pag]").forEach(r => (r.onchange = ajustarPag));
  $("#bairro").onchange = total;
  $("#tel").oninput = e => (e.target.value = mascaraTel(e.target.value));
  $("#troco").oninput = e => (e.target.value = soValor(e.target.value));
  $("#form-pedido").onsubmit = enviar;

  /* ---------- início ---------- */
  if (D.aparelho) { // este aparelho escolheu "Lembrar de mim" antes
    $("#nome").value = D.aparelho.nome;
    $("#tel").value = mascaraTel(D.aparelho.telefone);
  }
  const rascunho = lerRascunho();
  if (rascunho) {
    CAMPOS.forEach(id => { if (typeof rascunho[id] === "string") $("#" + id).value = rascunho[id]; });
    const t = $$("input[name=tipo]").find(r => r.value === rascunho.tipo);
    if (t) t.checked = true;
    $("#lembrar").checked = rascunho.lembrar !== false;
    // horário que ainda está na lista volta escolhido (se saiu da lista, o navegador deixa vazio)
    if ($("#horario") && typeof rascunho.horario === "string") $("#horario").value = rascunho.horario;
    if (rascunho.aviso) avisar(rascunho.aviso, 6000);
  }
  ajustarTipo();
  if (rascunho && rascunho.pag) {
    const p = $$("input[name=pag]").find(r => r.value === rascunho.pag);
    if (p && !p.closest(".pag").classList.contains("hidden")) { p.checked = true; ajustarPag(); }
  }
  desenharItens();

  // confere preços e disponibilidade no servidor; itens que saíram aparecem como aviso
  Sacola.conferir().then(avisos => {
    $("#avisos-sacola").innerHTML = avisos.map(a => `<div class="sacola-aviso" role="alert">${esc(a)}</div>`).join("");
    desenharItens();
  });
})();
