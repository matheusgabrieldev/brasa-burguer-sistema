// Teste de fumaça do sacola.js, sem navegador. Roda com:  node static/js/tests/sacola.smoke.js [caminho-do-sacola.js]
// Monta um "document" falso mínimo e confere que o script carrega sem erro e expõe os ajudantes.
const fs = require("fs");
const vm = require("vm");
const path = require("path");
const assert = require("assert");

const alvo = process.argv[2] || path.join(__dirname, "..", "sacola.js");

function el() {
  return { classList: { toggle() {}, add() {}, remove() {}, contains: () => false }, dataset: {}, style: {}, textContent: "", innerHTML: "", addEventListener() {}, setAttribute() {}, remove() {}, appendChild() {} };
}
const guardado = {};
const body = el();
body.dataset = { turno: "2026-11-10", aberta: "1" };
const ids = { "sacola-bar": el(), "sacola-qtd": el(), "sacola-sub": el(), "sacola-raiz": el() };
const win = {};
const doc = {
  body,
  getElementById: id => ids[id] || null,
  querySelector: () => ({ content: "token-falso" }),
  createElement: () => el(),
  addEventListener() {},
};
const storage = {
  getItem: k => (k in guardado ? guardado[k] : null),
  setItem: (k, v) => { guardado[k] = v; },
};
// um item salvo malformado e um válido: o malformado deve ser descartado sem quebrar
// SO_VALIDOS=1 deixa só o item válido (usado para comparar com versões antigas do script)
const lixo = process.env.SO_VALIDOS ? [] : [null, { produto_id: "x" }];
guardado.sacola = JSON.stringify({ turno: "2026-11-10", itens: [...lixo, { produto_id: 1, quantidade: 2, opcoes: {}, observacao: "", preco_unit: 10, nome: "A" }] });

// Monta o ambiente e carrega o sacola.js; devolve a sacola lida. `corpo` troca os data-* do body.
function carregarCom(corpo, salva) {
  guardado.sacola = JSON.stringify(salva);
  const b = el();
  b.dataset = corpo;
  const c = vm.createContext({ document: { ...doc, body: b }, localStorage: storage, CustomEvent: function () {}, fetch: async () => ({}), setTimeout, console });
  c.window = c;
  vm.runInContext(fs.readFileSync(alvo, "utf8"), c);
  return c.Sacola.ler();
}

// contexto onde "window" é o próprio escopo global, como no navegador
const ctx = vm.createContext({ document: doc, localStorage: storage, CustomEvent: function () {}, fetch: async () => ({}), setTimeout, console });
ctx.window = ctx;
vm.runInContext(fs.readFileSync(alvo, "utf8"), ctx);
Object.assign(win, { brl: ctx.brl, esc: ctx.esc, csrf: ctx.csrf, avisar: ctx.avisar, Sacola: ctx.Sacola });

for (const nome of ["brl", "esc", "csrf", "avisar", "Sacola"]) assert.ok(win[nome], `window.${nome} não foi definido`);
assert.strictEqual(win.brl(1234.5), "R$ 1.234,50");
assert.strictEqual(win.esc("<b>&\"'"), "&lt;b&gt;&amp;&quot;&#39;");
assert.strictEqual(win.csrf(), "token-falso");
assert.strictEqual(win.Sacola.ler().itens.length, 1, "item malformado devia ser descartado");

// Regra do turno: loja fechada (agendável) mantém a sacola do mesmo turno; turno diferente ou vazio esvazia.
const item = { produto_id: 1, quantidade: 1, opcoes: {}, observacao: "", preco_unit: 10, nome: "A" };
const salva = { turno: "2026-11-18", itens: [item] };
assert.strictEqual(carregarCom({ turno: "2026-11-18", aberta: "0", agendavel: "1" }, salva).itens.length, 1, "mesmo turno com loja fechada devia manter os itens");
assert.strictEqual(carregarCom({ turno: "2026-11-19", aberta: "0", agendavel: "1" }, salva).itens.length, 0, "turno diferente devia esvaziar");
assert.strictEqual(carregarCom({ turno: "", aberta: "0", agendavel: "0" }, salva).itens.length, 0, "turno vazio devia esvaziar");

// Abre a gaveta e deixa o servidor responder depois das alteracoes do cliente.
function montarValidacao(itens) {
  const elementos = Object.fromEntries(Object.keys(ids).map(id => [id, el()]));
  const dados = { sacola: JSON.stringify({ turno: "2026-11-10", itens }) };
  const pendentes = [];
  const c = vm.createContext({
    document: { ...doc, getElementById: id => elementos[id] || null },
    localStorage: {
      getItem: k => dados[k] || null,
      setItem: (k, v) => { dados[k] = v; },
    },
    CustomEvent: function () {}, setTimeout, console,
    fetch: (url, opcoes) => new Promise(resolve => {
      assert.strictEqual(url, "/sacola/validar/");
      pendentes.push({ itens: JSON.parse(opcoes.body).itens, resolve });
    }),
  });
  c.window = c;
  vm.runInContext(fs.readFileSync(alvo, "utf8"), c);
  return { c, elementos, dados, pendentes };
}

function responder(pendente, preco) {
  pendente.resolve({ ok: true, json: async () => ({
    removidos: [],
    itens: pendente.itens.map((_, indice) => ({ indice, nome: "A", preco_unitario: preco, opcoes: [] })),
  }) });
}

(async () => {
  // Ausencia, null, vazio e texto invalido nao representam o preco visto pelo cliente.
  for (const preco of [undefined, null, "", "invalido"]) {
    const antigo = { ...item };
    if (preco === undefined) delete antigo.preco_unit;
    else antigo.preco_unit = preco;
    const pagina = montarValidacao([antigo]);
    const abertura = pagina.elementos["sacola-bar"].onclick();
    responder(pagina.pendentes[0], "10.00");
    await abertura;
    assert.strictEqual(pagina.c.Sacola.ler().itens.length, 1, `preco desconhecido ${preco} deve permanecer`);
    assert.strictEqual(pagina.c.Sacola.ler().itens[0].preco_unit, 10);
    assert.strictEqual(JSON.parse(pagina.dados.sacola).itens[0].preco_unit, 10, "preco recalculado deve ser salvo");
    assert.ok(!pagina.elementos["sacola-raiz"].innerHTML.includes("mudou de"));
  }

  const mudou = montarValidacao([{ ...item, preco_unit: 9 }]);
  const aberturaMudou = mudou.elementos["sacola-bar"].onclick();
  responder(mudou.pendentes[0], "10.00");
  await aberturaMudou;
  assert.strictEqual(mudou.c.Sacola.ler().itens.length, 0, "preco conhecido diferente deve remover");
  assert.ok(mudou.elementos["sacola-raiz"].innerHTML.includes("mudou de"), "remocao deve explicar a mudanca de preco");

  const gratis = montarValidacao([{ ...item, preco_unit: 0 }]);
  const aberturaGratis = gratis.elementos["sacola-bar"].onclick();
  responder(gratis.pendentes[0], "0.00");
  await aberturaGratis;
  assert.strictEqual(gratis.c.Sacola.ler().itens.length, 1, "zero conhecido igual deve permanecer");

  const concorrente = montarValidacao([{ ...item, preco_unit: null }]);
  const aberturaConcorrente = concorrente.elementos["sacola-bar"].onclick();
  concorrente.c.Sacola.mudarQtd(0, 1);
  responder(concorrente.pendentes[0], "99.00");
  await new Promise(resolve => setImmediate(resolve));
  assert.strictEqual(concorrente.c.Sacola.ler().itens[0].preco_unit, null, "resposta antiga nao deve preencher preco");
  assert.strictEqual(concorrente.pendentes.length, 2, "sacola alterada deve ser conferida de novo");
  assert.strictEqual(concorrente.pendentes[1].itens[0].quantidade, 2);
  responder(concorrente.pendentes[1], "10.00");
  await aberturaConcorrente;
  assert.strictEqual(concorrente.c.Sacola.ler().itens[0].quantidade, 2);
  assert.strictEqual(concorrente.c.Sacola.ler().itens[0].preco_unit, 10);

  console.log("sacola.js OK");
})().catch(err => { console.error(err); process.exit(1); });
