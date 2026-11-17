/* Página do cardápio: busca, categoria ativa ao rolar e taxa de entrega por bairro. */
(function () {
  // busca (filtra no navegador, sem recarregar)
  const btnBusca = document.getElementById("btn-busca");
  const caixa = document.getElementById("busca-box");
  const busca = document.getElementById("busca");
  btnBusca.onclick = () => { caixa.classList.toggle("hidden"); if (!caixa.classList.contains("hidden")) busca.focus(); };
  busca.oninput = () => {
    const t = busca.value.trim().toLowerCase();
    let achou = 0;
    document.querySelectorAll(".prod").forEach(el => {
      const ok = !t || el.dataset.busca.includes(t);
      el.classList.toggle("hidden", !ok);
      if (ok) achou++;
    });
    document.querySelectorAll(".secao").forEach(s => {
      if (s.id === "sec-destaques") { s.classList.toggle("hidden", !!t); return; }
      s.classList.toggle("hidden", !s.querySelector(".prod:not(.hidden)"));
    });
    document.getElementById("vazio-busca").classList.toggle("hidden", achou > 0);
  };

  // categoria ativa conforme a rolagem
  const chips = [...document.querySelectorAll(".chip")];
  const secoes = chips.map(c => document.querySelector(c.getAttribute("href")));
  function marcar() {
    let atual = 0;
    secoes.forEach((s, i) => { if (s && s.getBoundingClientRect().top < 120) atual = i; });
    chips.forEach((c, i) => c.classList.toggle("ativo", i === atual));
    const ativo = chips[atual];
    if (ativo) {
      const bar = document.getElementById("cat-chips");
      const alvo = ativo.offsetLeft - bar.clientWidth / 2 + ativo.clientWidth / 2;
      if (Math.abs(bar.scrollLeft - alvo) > 40) bar.scrollLeft = alvo;
    }
  }
  window.addEventListener("scroll", marcar, { passive: true });
  marcar();

  // calcular taxa: abre a lista de bairros (já vem na página) sem navegar
  const tpl = document.getElementById("tpl-taxa");
  document.getElementById("abrir-taxa").onclick = () => {
    const raiz = document.getElementById("sheet-raiz");
    raiz.innerHTML = tpl.innerHTML;
    const sel = raiz.querySelector("#sel-bairro");
    let salvo = null;
    try { salvo = localStorage.getItem("lb_bairro"); } catch (e) { /* sem armazenamento */ }
    if (salvo) sel.value = salvo;
    const mostrar = () => {
      const op = sel.selectedOptions[0];
      const res = raiz.querySelector("#taxa-res");
      if (!sel.value) { res.classList.add("hidden"); return; }
      res.classList.remove("hidden");
      res.textContent = `Entrega em ${op.textContent.split(" — ")[0]}: ${brl(op.dataset.taxa)}`;
      document.getElementById("taxa-escolhida").textContent = res.textContent;
      try { localStorage.setItem("lb_bairro", sel.value); } catch (e) { /* sem armazenamento */ }
    };
    sel.onchange = mostrar;
    mostrar();
  };
})();
