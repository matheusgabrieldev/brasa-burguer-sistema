// Roda com: node static/js/tests/acompanhar.smoke.js
const fs = require("fs");
const vm = require("vm");
const path = require("path");
const assert = require("assert");

const codigo = fs.readFileSync(path.join(__dirname, "..", "acompanhar.js"), "utf8");

function abrir(codigoPedido, sessao = new Map(), armazenamentoNegado = false) {
  const navegacoes = [];
  let cliques = 0;
  const link = codigoPedido === null ? null : {
    dataset: { codigo: codigoPedido },
    href: "https://wa.me/5581999999999?text=" + codigoPedido,
    target: "_blank",
    click() { cliques++; },
  };
  const contexto = vm.createContext({
    document: {
      querySelector(seletor) {
        assert.strictEqual(seletor, "#confirmar-whatsapp[data-codigo]");
        return link;
      },
    },
    sessionStorage: {
      getItem(chave) {
        if (armazenamentoNegado === "ler") throw new Error("Storage denied");
        return sessao.get(chave) || null;
      },
      setItem(chave, valor) {
        if (armazenamentoNegado === "gravar") throw new Error("Storage denied");
        sessao.set(chave, valor);
      },
    },
    location: { assign(url) { navegacoes.push(url); } },
  });
  contexto.window = contexto;
  vm.runInContext(codigo, contexto);
  return { link, navegacoes, cliques: () => cliques };
}

// A abertura automatica deve navegar na mesma aba, sem popup dependente de gesto.
const sessao = new Map();
const primeira = abrir("pedido-a", sessao);
assert.deepStrictEqual(primeira.navegacoes, ["https://wa.me/5581999999999?text=pedido-a"]);
assert.strictEqual(primeira.cliques(), 0);
assert.deepStrictEqual(abrir("pedido-a", sessao).navegacoes, [], "recarregar nao deve abrir de novo");
assert.deepStrictEqual(abrir("pedido-b", sessao).navegacoes, ["https://wa.me/5581999999999?text=pedido-b"], "outro pedido deve abrir uma vez");

assert.deepStrictEqual(abrir(null).navegacoes, [], "pagina sem link nao deve navegar");
for (const negado of ["ler", "gravar"]) {
  const pagina = abrir("pedido-c", new Map(), negado);
  assert.deepStrictEqual(pagina.navegacoes, [], "sem armazenamento deve preservar a abertura manual");
  assert.strictEqual(pagina.link.href, "https://wa.me/5581999999999?text=pedido-c");
  assert.strictEqual(pagina.link.target, "_blank");
  pagina.link.click();
  assert.strictEqual(pagina.cliques(), 1, "link manual deve continuar disponivel");
}

console.log("acompanhar.js OK");
