// Teste de fumaça do checkout.js (com o sacola.js), sem navegador. Roda com:  node static/js/tests/checkout.smoke.js
// Monta uma página falsa mínima e confere: total mostrado, envio com sucesso, internet lenta
// (reenvio usa a mesma chave) e loja que mudou de modo (recarrega sem perder a sacola).
const fs = require("fs");
const vm = require("vm");
const path = require("path");
const assert = require("assert");

const pasta = path.join(__dirname, "..");
const codigo = ["sacola.js", "checkout.js"].map(f => fs.readFileSync(path.join(pasta, f), "utf8"));

function el(extra = {}) {
  const cls = new Set();
  return Object.assign({
    value: "", checked: false, disabled: false, textContent: "", innerHTML: "", dataset: {}, style: {},
    classList: {
      toggle(c, on) { if (on === undefined) on = !cls.has(c); if (on) cls.add(c); else cls.delete(c); },
      add: c => cls.add(c), remove: c => cls.delete(c), contains: c => cls.has(c),
    },
    closest: () => null, querySelector: () => null, scrollIntoView() {}, focus() {},
    addEventListener() {}, setAttribute() {}, remove() {}, appendChild() {},
  }, extra);
}

const DADOS = {
  bairros: { 1: "5.00" },
  formas: { pix: { pct: "0.00", tipos: ["delivery", "retirada", "local"] }, credito: { pct: "4.00", tipos: ["delivery", "retirada"] }, dinheiro: { pct: "0.00", tipos: ["retirada"] } },
  enderecos: [{ bairro_id: 1, rua: "Rua A", numero: "10", referencia: "" }],
  aparelho: { nome: "Ana", telefone: "(81) 98888-7777" },
  pedido_minimo: "10.00",
};
const ITEM = { produto_id: 1, quantidade: 2, opcoes: { 5: 1 }, observacao: "", preco_unit: 25, nome: "Brasa Premium" };

/* Monta a página e roda os dois scripts. `responder(url, corpo)` faz o papel do servidor. */
function montar(responder, guardadoSessao = {}) {
  const ids = {};
  ["vazia", "tem-itens", "lista-itens", "avisos-sacola", "bairro", "rua", "numero", "ref", "nome", "tel", "obs", "troco",
    "r-sub", "r-taxa", "r-acr", "r-total", "linha-taxa", "linha-acr", "aviso-minimo", "sem-forma", "campo-troco",
    "campos-entrega", "form-pedido", "erro", "info-retirada", "outro-endereco"].forEach(id => (ids[id] = el()));
  ids["dados-checkout"] = el({ textContent: JSON.stringify(DADOS) });
  ids.enviar = el({ textContent: "Enviar pedido" });
  ids.lembrar = el({ checked: true });

  const tipos = ["delivery", "retirada", "local"].map((v, i) => el({ value: v, checked: i === 0 }));
  const pags = Object.keys(DADOS.formas).map(codigo => {
    const radio = el({ value: codigo });
    const label = el({ dataset: { tipos: DADOS.formas[codigo].tipos.join(" ") }, querySelector: () => radio });
    radio.closest = () => label;
    return { radio, label };
  });
  const campos = { nome: ids.nome, telefone: ids.tel, bairro: ids.bairro, rua: ids.rua, numero: ids.numero, troco: ids.troco };

  const ouvintes = {};
  const body = el({ dataset: { turno: "2026-11-11", aberta: "1", agendavel: "0" } });
  const doc = {
    body,
    getElementById: id => ids[id] || null,
    createElement: () => el(),
    addEventListener: (tipo, fn) => (ouvintes[tipo] = ouvintes[tipo] || []).push(fn),
    dispatchEvent: ev => (ouvintes[ev.type] || []).forEach(fn => fn(ev)),
    querySelector(sel) {
      let m;
      if ((m = sel.match(/^#(.+)$/))) return ids[m[1]] || null;
      if (sel === "input[name=tipo]:checked") return tipos.find(t => t.checked) || null;
      if (sel === "input[name=pag]:checked") return (pags.find(p => p.radio.checked) || {}).radio || null;
      if (sel === "input[name=tipo][value=delivery]") return tipos[0];
      if ((m = sel.match(/^\[data-campo="(.+)"\]$/))) return campos[m[1]] || null;
      if (sel === 'meta[name="csrf-token"]') return { content: "token-falso" };
      return null;
    },
    querySelectorAll(sel) {
      if (sel === "input[name=tipo]") return tipos;
      if (sel === "input[name=pag]") return pags.map(p => p.radio);
      if (sel === ".pag") return pags.map(p => p.label);
      return [];
    },
  };
  const local = { sacola: JSON.stringify({ turno: "2026-11-11", itens: [ITEM] }) };
  const sessao = { ...guardadoSessao };
  const envios = [];
  const pagina = { href: "", recarregou: false };
  const ctx = vm.createContext({
    document: doc, console, setTimeout, clearTimeout, AbortController, crypto: globalThis.crypto, Uint8Array,
    CustomEvent: class { constructor(type, o) { this.type = type; this.detail = o && o.detail; } },
    localStorage: { getItem: k => (k in local ? local[k] : null), setItem: (k, v) => (local[k] = v) },
    sessionStorage: { getItem: k => (k in sessao ? sessao[k] : null), setItem: (k, v) => (sessao[k] = v), removeItem: k => delete sessao[k] },
    location: { set href(v) { pagina.href = v; }, get href() { return pagina.href; }, reload() { pagina.recarregou = true; } },
    fetch: async (url, opcoes) => {
      const corpo = JSON.parse(opcoes.body);
      if (url === "/sacola/validar/") {
        return { ok: true, status: 200, json: async () => ({ itens: [{ indice: 0, nome: "Brasa Premium", preco_unitario: "25.00", total: "50.00", opcoes: [] }], removidos: [], subtotal: "50.00" }) };
      }
      envios.push(corpo);
      return responder(url, corpo);
    },
  });
  ctx.window = ctx;
  codigo.forEach(c => vm.runInContext(c, ctx));
  return { ctx, ids, tipos, pags, local, sessao, envios, pagina };
}

const resposta = (status, json) => ({ ok: status < 300, status, json: async () => json });
const espera = () => new Promise(r => setTimeout(r, 0));
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

(async () => {
  // 1) total mostrado e envio com sucesso
  const a = montar(() => resposta(201, { codigo: "abc", url: "/pedido/abc/" }));
  await espera();
  assert.strictEqual(a.ids.nome.value, "Ana", "nome do aparelho devia vir preenchido");
  assert.ok(a.pags.find(p => p.radio.value === "dinheiro").label.classList.contains("hidden"), "dinheiro não aceita delivery: devia sumir");
  a.ids.bairro.value = "1";
  const credito = a.pags.find(p => p.radio.value === "credito").radio;
  credito.checked = true;
  credito.onchange();
  // 2x 25 = 50; taxa 5; crédito 4% de 55 = 2,20
  assert.strictEqual(a.ids["r-total"].textContent, "R$ 57,20");
  a.ids.rua.value = "Rua das Flores";
  a.ids.numero.value = "505";
  await a.ids["form-pedido"].onsubmit({ preventDefault() {} });
  assert.strictEqual(a.envios.length, 1);
  const enviado = a.envios[0];
  assert.ok(UUID.test(enviado.chave), "chave devia ser um UUID");
  assert.strictEqual(enviado.lembrar, true);
  assert.strictEqual(enviado.pagamento, "credito");
  assert.strictEqual(enviado.itens.length, 1);
  assert.strictEqual(a.pagina.href, "/pedido/abc/", "devia ir para a página do pedido");
  assert.strictEqual(JSON.parse(a.local.sacola).itens.length, 0, "sacola devia ser apagada");

  // 2) internet lenta: mostra o aviso, libera o botão e o reenvio usa a mesma chave
  let vez = 0;
  const b = montar(() => {
    vez++;
    if (vez === 1) { const e = new Error("abortado"); e.name = "AbortError"; throw e; }
    return resposta(201, { codigo: "x", url: "/pedido/x/" });
  });
  await espera();
  b.pags[0].radio.checked = true;
  await b.ids["form-pedido"].onsubmit({ preventDefault() {} });
  assert.strictEqual(b.ids.erro.textContent, "A internet está lenta. Tente de novo.");
  assert.strictEqual(b.ids.enviar.disabled, false);
  await b.ids["form-pedido"].onsubmit({ preventDefault() {} });
  assert.strictEqual(b.envios[0].chave, b.envios[1].chave, "reenvio devia usar a mesma chave");

  // 3) loja mudou de modo (campo "horario"): guarda o formulário e recarrega, sem apagar a sacola
  const c = montar(() => resposta(400, { erro: "A loja abriu: o pedido agora é para já. Recarregue a página.", campo: "horario" }));
  await espera();
  c.ids.obs.value = "sem cebola";
  await c.ids["form-pedido"].onsubmit({ preventDefault() {} });
  assert.ok(c.pagina.recarregou, "devia recarregar a página");
  assert.strictEqual(JSON.parse(c.local.sacola).itens.length, 1, "a sacola não pode sumir");
  const rascunho = JSON.parse(c.sessao["checkout-rascunho"]);
  assert.strictEqual(rascunho.obs, "sem cebola");
  // ao recarregar, o rascunho volta para o formulário
  const d = montar(() => resposta(201, {}), { "checkout-rascunho": JSON.stringify(rascunho) });
  await espera();
  assert.strictEqual(d.ids.obs.value, "sem cebola");
  assert.ok(!("checkout-rascunho" in d.sessao), "rascunho devia ser usado uma vez só");

  // 4) erro com campo: mostra a mensagem e libera o botão
  const e = montar(() => resposta(400, { erro: "Escolha o bairro de entrega.", campo: "bairro" }));
  await espera();
  await e.ids["form-pedido"].onsubmit({ preventDefault() {} });
  assert.strictEqual(e.ids.erro.textContent, "Escolha o bairro de entrega.");
  assert.ok(e.ids.bairro.classList.contains("com-erro"));
  assert.strictEqual(e.ids.enviar.textContent, "Enviar pedido");

  console.log("checkout.js OK");
})().catch(err => { console.error(err); process.exit(1); });
