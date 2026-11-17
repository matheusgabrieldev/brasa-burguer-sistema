/* Modal do produto. O HTML vem pronto do servidor (HTMX); aqui só tem o comportamento:
   contadores dos grupos, limites, preço ao vivo, quantidade e o botão "Adicionar". */
(function () {
  const raiz = () => document.getElementById("sheet-raiz");

  function fechar() {
    raiz().innerHTML = "";
    document.body.style.overflow = "";
  }
  window.fecharSheet = fechar;

  function iniciar(form) {
    document.body.style.overflow = "hidden";
    const precoBase = Number(form.dataset.preco);
    const grupos = [...form.querySelectorAll("[data-grupo]")];
    // estado: { idDaOpcao: quantidade }  (só opções marcadas)
    const estado = {};
    let qtd = 1;

    const doGrupo = g => [...g.querySelectorAll("[data-opcao]")].filter(el => estado[el.dataset.opcao]);
    const contagem = g => doGrupo(g).reduce((s, el) => s + estado[el.dataset.opcao], 0);
    const faltando = () => grupos.filter(g => contagem(g) < Number(g.dataset.minimo));
    const unitario = () => precoBase + [...form.querySelectorAll("[data-opcao]")].reduce((s, el) => s + (estado[el.dataset.opcao] || 0) * Number(el.dataset.preco), 0);

    function atualizar() {
      grupos.forEach(g => {
        const n = contagem(g);
        const limite = Number(g.dataset.limite);
        const obrig = g.dataset.obrigatorio === "1";
        g.querySelector("[data-cont]").textContent = `${n}/${limite}` + (obrig ? " OBRIGATÓRIO" : "");
        g.querySelector(".grupo-h").classList.toggle("ok", obrig && n >= Number(g.dataset.minimo));
        if (g.dataset.tipo === "varias") {
          // limite do grupo atingido: trava o que ainda não foi marcado
          g.querySelectorAll("input[data-opcao]").forEach(inp => { inp.disabled = !inp.checked && n >= limite; });
          g.querySelectorAll("div[data-opcao]").forEach(div => {
            const q = estado[div.dataset.opcao] || 0;
            div.querySelector("[data-mais]").disabled = n >= limite || q >= Number(div.dataset.qmax);
            div.querySelector("[data-menos]").disabled = q <= 0;
          });
        }
      });
      form.querySelector("#q-val").textContent = qtd;
      form.querySelector("#q-menos").disabled = qtd <= 1;
      const add = form.querySelector("#btn-add");
      if (add) {
        const falta = faltando().length > 0;
        form.querySelector("#btn-add-txt").textContent = falta ? "Escolha as obrigatórias" : "Adicionar";
        form.querySelector("#btn-add-preco").textContent = brl(unitario() * qtd);
        add.classList.toggle("btn-ghost", falta);
      }
    }

    form.addEventListener("change", e => {
      const el = e.target;
      if (!el.dataset.opcao) return;
      const g = el.closest("[data-grupo]");
      if (g.dataset.tipo === "unica") {
        g.querySelectorAll("[data-opcao]").forEach(x => delete estado[x.dataset.opcao]);
        if (el.checked) estado[el.dataset.opcao] = 1;
      } else if (el.checked) estado[el.dataset.opcao] = 1;
      else delete estado[el.dataset.opcao];
      atualizar();
    });

    form.addEventListener("click", e => {
      // escolha única opcional: tocar de novo na opção marcada desmarca
      const radio = e.target.matches && e.target.matches('input[type="radio"]') ? e.target : null;
      if (radio) {
        const g = radio.closest("[data-grupo]");
        if (g.dataset.obrigatorio !== "1" && radio.dataset.marcado === "1") {
          radio.checked = false;
          radio.dataset.marcado = "0";
          delete estado[radio.dataset.opcao];
          atualizar();
          return;
        }
        g.querySelectorAll('input[type="radio"]').forEach(r => (r.dataset.marcado = "0"));
        radio.dataset.marcado = "1";
      }
      // botões + e − das opções com quantidade (ex.: bacon x3)
      const mais = e.target.closest("[data-mais]"), menos = e.target.closest("[data-menos]");
      if (mais || menos) {
        const div = e.target.closest("[data-opcao]");
        const v = (estado[div.dataset.opcao] || 0) + (mais ? 1 : -1);
        if (v <= 0) delete estado[div.dataset.opcao]; else estado[div.dataset.opcao] = v;
        div.querySelector("[data-q]").textContent = Math.max(v, 0);
        atualizar();
      }
    });

    form.querySelector("#q-menos").onclick = () => { qtd = Math.max(1, qtd - 1); atualizar(); };
    form.querySelector("#q-mais").onclick = () => { qtd = Math.min(50, qtd + 1); atualizar(); };
    const obs = form.querySelector("#obs-item");
    obs.oninput = () => (form.querySelector("#obs-cont").textContent = `${obs.value.length}/140`);

    const add = form.querySelector("#btn-add");
    if (add) add.onclick = () => {
      const falta = faltando();
      if (falta.length) {
        const h = falta[0].querySelector(".grupo-h");
        h.classList.add("faltando");
        h.scrollIntoView({ behavior: "smooth", block: "center" });
        setTimeout(() => h.classList.remove("faltando"), 1600);
        return;
      }
      const opcoes = {}, detalhe = [];
      form.querySelectorAll("[data-opcao]").forEach(el => {
        const q = estado[el.dataset.opcao];
        if (!q) return;
        opcoes[el.dataset.opcao] = q;
        const nome = el.dataset.nome || el.querySelector(".opt-nome").firstChild.textContent.trim();
        detalhe.push({ opcao_id: Number(el.dataset.opcao), nome, qtd: q });
      });
      // o preço aqui é só para mostrar; o servidor recalcula tudo em /sacola/validar/
      document.dispatchEvent(new CustomEvent("sacola:adicionar", {
        detail: {
          produto_id: Number(form.dataset.produtoId), nome: form.dataset.nome, foto: form.dataset.foto,
          quantidade: qtd, opcoes, opcoes_nomes: detalhe, observacao: obs.value.trim(), preco_unit: unitario(),
        },
      }));
      fechar();
    };
    atualizar();
  }

  // o HTMX acabou de colocar o modal na página
  document.body.addEventListener("htmx:afterSwap", e => {
    const form = e.detail.target.querySelector && e.detail.target.querySelector("[data-modal-produto]");
    if (form) iniciar(form);
  });

  // fechar: botão ×, clique no fundo escuro ou tecla Esc
  document.addEventListener("click", e => {
    if (e.target.closest("[data-fechar]") && (e.target.classList.contains("sheet-fundo") || e.target.closest("button[data-fechar]"))) fechar();
  });
  document.addEventListener("keydown", e => { if (e.key === "Escape") fechar(); });
})();
