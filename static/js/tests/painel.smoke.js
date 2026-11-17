// Teste de fumaça do painel.js, sem navegador. Roda com:  node static/js/tests/painel.smoke.js [caminho-do-painel.js]
// 1) carrega com um "document" falso sem o painel e confere os ajudantes puros (window.Painel);
// 2) carrega de novo com um #colunas falso e confere a fiação: título pisca, faixa do som, aba guardada.
const fs = require("fs");
const vm = require("vm");
const path = require("path");
const assert = require("assert");

const alvo = process.argv[2] || path.join(__dirname, "..", "painel.js");
const codigo = fs.readFileSync(alvo, "utf8");

// elemento falso: classes de verdade (Set) para dar para conferir "ativa", "escondida" etc.
function el(extra = {}) {
  const classes = new Set();
  return Object.assign({
    classList: {
      add: c => classes.add(c), remove: c => classes.delete(c), contains: c => classes.has(c),
      toggle: (c, ligar) => { const v = ligar === undefined ? !classes.has(c) : ligar; v ? classes.add(c) : classes.delete(c); return v; },
    },
    dataset: {}, style: {}, hidden: false, textContent: "", innerHTML: "",
    addEventListener() {}, setAttribute() {}, removeAttribute() {}, appendChild() {}, focus() {},
    querySelector: () => null, querySelectorAll: () => [], closest: () => null, contains: () => false,
  }, extra);
}

function carregar(doc, extras = {}) {
  const ctx = vm.createContext(Object.assign({ document: doc, console, setTimeout, clearTimeout, setInterval: () => 0 }, extras));
  ctx.window = ctx;
  vm.runInContext(codigo, ctx);
  return ctx;
}

// ---------- 1) ajudantes puros, página sem painel ----------
const vazio = { body: el(), title: "Pedidos", getElementById: () => null, querySelector: () => null,
  querySelectorAll: () => [], addEventListener() {}, createElement: () => el() };
const P = carregar(vazio).Painel;
assert.ok(P, "window.Painel não foi definido");

assert.strictEqual(P.deveTocar(1, true), true, "pedido novo + som liberado = toca");
assert.strictEqual(P.deveTocar(0, true), false, "sem pedido novo não toca");
assert.strictEqual(P.deveTocar(1, false), false, "som bloqueado não toca (o título pisca no lugar)");
assert.strictEqual(P.deveTocar(NaN, true), false, "data-novos estranho não toca");

const base = "Pedidos · Área da loja";
assert.strictEqual(P.tituloPiscando(base, 0, 0), base, "sem novo, título normal");
assert.strictEqual(P.tituloPiscando(base, 0, 1), base);
const t0 = P.tituloPiscando(base, 2, 0), t1 = P.tituloPiscando(base, 2, 1);
assert.notStrictEqual(t0, t1, "com novo, o título alterna a cada tick");
assert.deepStrictEqual([t0, t1].sort(), [base, "(2) 🔔 Pedido novo!"].sort());
assert.strictEqual(P.tituloPiscando(base, 2, 2), t0, "volta ao mesmo depois de 2 ticks");

const etapas = ["aguardando", "preparo", "pronto", "saiu", "concluido"];
assert.strictEqual(P.abaAtiva("pronto", etapas), "pronto");
assert.strictEqual(P.abaAtiva(null, etapas), "preparo", "sem nada guardado cai em preparo");
assert.strictEqual(P.abaAtiva("sumiu", etapas), "preparo", "guardada que não existe cai em preparo");
assert.strictEqual(P.abaAtiva(null, ["pronto", "saiu"]), "pronto", "sem preparo, a primeira que existe");

// ---------- 2) fiação com um painel falso ----------
const guardado = { "painel-aba": "saiu" };
const storage = { getItem: k => (k in guardado ? guardado[k] : null), setItem: (k, v) => { guardado[k] = v; } };
const abas = etapas.map(e => el({ dataset: { etapa: e } }));
const cols = etapas.map(e => el({ dataset: { etapa: e } }));
const colunas = el({
  dataset: { novos: "1", versao: "x" },
  querySelectorAll: s => (s.includes("painel-etapas") ? abas : s.includes("coluna") ? cols : []),
});
const faixa = el();
const ids = { colunas, "faixa-som": faixa, detalhe: el() };
let tique = null;
const doc = Object.assign({}, vazio, {
  title: base, visibilityState: "visible",
  getElementById: id => ids[id] || null,
});
carregar(doc, { localStorage: storage, setInterval: fn => { tique = fn; return 1; }, htmx: { ajax() {}, trigger() {} } });

assert.ok(abas[3].classList.contains("ativa") && cols[3].classList.contains("ativa"), "aba guardada (saiu) devia ficar ativa");
assert.ok(!cols[1].classList.contains("ativa"), "as outras colunas saem de ativa");
assert.ok(doc.body.classList.contains("com-abas"), "com JS, o celular mostra uma etapa por vez");
assert.strictEqual(typeof tique, "function", "o relógio do alarme devia estar rodando");
const titulos = new Set();
tique(); titulos.add(doc.title); tique(); titulos.add(doc.title);
assert.ok(titulos.has("(1) 🔔 Pedido novo!") && titulos.has(base), "título devia piscar sem som liberado");
assert.ok(!faixa.hidden, "sem som liberado, a faixa continua visível");

colunas.dataset.novos = "0";
tique(); tique();
assert.strictEqual(doc.title, base, "sem pedido novo, o título volta ao normal");

// localStorage que explode (aba anônima/bloqueada) não pode quebrar o painel
carregar(Object.assign({}, doc, { body: el() }), {
  localStorage: { getItem() { throw new Error("negado"); }, setItem() { throw new Error("negado"); } },
  htmx: { ajax() {}, trigger() {} },
});

// ---------- 3) fechar o detalhe pelo teclado ----------
// Enter no "Fechar": o click sai no keydown, o foco volta ao cartão e o keyup do mesmo Enter
// não pode reabrir o detalhe (o cartão escuta keyup). Com mouse, nada é barrado.
function montarDetalhe() {
  const ouvintes = [];
  const ouvir = alvo => (tipo, fn, captura) => ouvintes.push({ alvo, tipo, fn, captura: !!captura });
  const focos = [];
  const cartao = el({ focus() { focos.push("cartao"); } });
  cartao.classList.add("cartao");
  const fechar = el({ focus() { focos.push("fechar"); } });
  let aberto = true;
  const raiz = el({ dataset: { pk: "7", url: "/gerenciar/pedido/7/" }, querySelector: s => (s === "[data-fechar]" ? fechar : null) });
  const campo = el({ tagName: "INPUT", blur() { campo.saiu = true; } });
  const caixa = el({
    id: "detalhe",
    querySelector: s => (aberto && s === ".detalhe[data-url]" ? raiz : null),
    contains: x => aberto && (x === fechar || x === campo),
  });
  Object.defineProperty(caixa, "innerHTML", { set(v) { if (v === "") aberto = false; }, get: () => "" });
  const corpo = el({ addEventListener: ouvir("body") });
  const d = Object.assign({}, vazio, {
    body: corpo, title: base, visibilityState: "visible", activeElement: null,
    getElementById: id => ({ colunas: el({ dataset: { novos: "0" } }), detalhe: caixa, "pedido-7": cartao })[id] || null,
    addEventListener: ouvir("doc"),
  });
  carregar(d, { htmx: { ajax() {}, trigger() {} } });
  // cada evento passa primeiro pelos ouvintes de captura, como no navegador
  const disparar = (tipo, ev) => {
    ev.parou = false;
    ev.stopPropagation = () => { ev.parou = true; };
    ev.preventDefault = () => {};
    for (const fase of [true, false]) for (const o of ouvintes) if (o.alvo === "doc" && o.tipo === tipo && o.captura === fase) o.fn(ev);
    return ev;
  };
  const trocou = () => { for (const o of ouvintes) if (o.alvo === "body" && o.tipo === "htmx:afterSwap") o.fn({ detail: { target: caixa }, target: caixa }); };
  const abrir = () => { aberto = true; trocou(); };
  const esvaziarPorSwap = () => { aberto = false; trocou(); };
  const clicarFechar = detalhe => disparar("click", { detail: detalhe, target: { closest: s => (s === "[data-fechar]" ? fechar : null) } });
  return { d, disparar, abrir, esvaziarPorSwap, clicarFechar, cartao, campo, focos, estaAberto: () => aberto };
}

{
  const t = montarDetalhe();
  t.abrir();
  assert.ok(t.d.body.classList.contains("detalhe-aberto"), "abrir marca o body");
  assert.deepStrictEqual(t.focos, ["fechar"], "ao abrir, o foco vai para o Fechar");
  // Enter no Fechar: keydown → click (detail 0) → keyup no cartão
  t.disparar("keydown", { key: "Enter", target: {} });
  t.clicarFechar(0);
  assert.ok(!t.estaAberto(), "Enter no Fechar fecha");
  assert.ok(!t.d.body.classList.contains("detalhe-aberto"), "fechar tira a trava de rolagem");
  assert.strictEqual(t.focos[t.focos.length - 1], "cartao", "foco volta ao cartão");
  assert.ok(t.disparar("keyup", { key: "Enter", target: t.cartao }).parou, "o keyup do mesmo Enter não pode reabrir o cartão");
  // depois disso, Enter no cartão abre normalmente
  t.disparar("keydown", { key: "Enter", target: t.cartao });
  assert.ok(!t.disparar("keyup", { key: "Enter", target: t.cartao }).parou, "Enter seguinte no cartão segue normal");

  // fechar com o mouse não barra nada depois
  t.abrir();
  t.clicarFechar(1);
  assert.ok(!t.estaAberto());
  assert.ok(!t.disparar("keyup", { key: "Enter", target: t.cartao }).parou, "fechar com mouse não engole teclas");

  // Esc digitando o motivo só sai do campo; Esc fora do campo fecha
  t.abrir();
  t.d.activeElement = t.campo;
  t.disparar("keydown", { key: "Escape", target: t.campo });
  assert.ok(t.estaAberto() && t.campo.saiu, "Esc no campo só tira o foco, não fecha");
  t.d.activeElement = null;
  t.disparar("keydown", { key: "Escape", target: {} });
  assert.ok(!t.estaAberto(), "Esc fora do campo fecha");

  // #detalhe esvaziado por outro caminho (swap vazio) também destrava a rolagem
  t.abrir();
  assert.ok(t.d.body.classList.contains("detalhe-aberto"));
  t.esvaziarPorSwap();
  assert.ok(!t.d.body.classList.contains("detalhe-aberto"), "swap que deixa #detalhe vazio tira a trava de rolagem");
}

console.log("painel.smoke OK");
