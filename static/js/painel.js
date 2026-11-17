// Painel de pedidos (/gerenciar/): tudo o que o HTMX sozinho não faz.
//   - alarme (bipe por WebAudio, sem arquivo) + título da aba piscando enquanto houver pedido novo;
//   - faixa "Toque para ativar o som": o navegador só deixa tocar som depois de um toque na página;
//   - detalhe do pedido: fechar (Esc/voltar), devolver o foco ao cartão e recarregar quando o painel muda;
//   - celular: uma etapa por vez (aba guardada no aparelho) e o olho do total do dia;
//   - atalho verde "Avisar no WhatsApp" por 8 s depois de Pronto/Saiu/Cancelar.
// De onde vêm os dados: #colunas traz data-novos (quantos pedidos ninguém abriu) e é trocado
// pelo HTMX a cada 5 s; o servidor manda os eventos "painel-mudou" e "avisar-whatsapp" no HX-Trigger.
// Quem pede a consulta na hora (painel-mudou / aba voltou a aparecer) é o próprio hx-trigger de
// #colunas (_colunas.html); aqui só reagimos depois que as colunas novas chegam.
(function () {
  "use strict";

  // ---------- regras puras (testadas em tests/painel.smoke.js) ----------

  // Toca só com pedido novo E som liberado; sem som, quem avisa é o título piscando.
  function deveTocar(novos, somLiberado) {
    return novos > 0 && somLiberado === true;
  }

  // Alterna a cada tick entre o aviso e o título normal; sem pedido novo, fica o normal.
  function tituloPiscando(base, novos, tick) {
    if (!(novos > 0)) return base;
    return tick % 2 === 0 ? "(" + novos + ") 🔔 Pedido novo!" : base;
  }

  // Aba do celular: a guardada, se ainda existe; senão "Em preparo" (onde a cozinha trabalha).
  function abaAtiva(guardada, colunas) {
    if (guardada && colunas.indexOf(guardada) >= 0) return guardada;
    if (colunas.indexOf("preparo") >= 0) return "preparo";
    return colunas[0] || "preparo";
  }

  window.Painel = { deveTocar: deveTocar, tituloPiscando: tituloPiscando, abaAtiva: abaAtiva };

  // Sem o painel na tela (outra página, ou o teste só dos ajudantes): não liga nada.
  if (!document.getElementById("colunas")) return;

  var CHAVE_ABA = "painel-aba";
  var CHAVE_OLHO = "painel-olho";
  var cada = function (lista, fn) { Array.prototype.forEach.call(lista, fn); };

  // localStorage pode explodir (aba anônima, site bloqueado): nesse caso só não lembra.
  function ler(chave) {
    try { return window.localStorage.getItem(chave); } catch (e) { return null; }
  }
  function guardar(chave, valor) {
    try { window.localStorage.setItem(chave, valor); } catch (e) { /* sem memória, segue */ }
  }

  // ---------- som ----------
  // Um AudioContext só, criado DENTRO de um toque (regra do navegador). Se o Android suspender
  // o som (aba em segundo plano), a faixa volta a aparecer até o próximo toque.
  var audio = null;

  function somLiberado() {
    return !!audio && audio.state === "running";
  }

  function atualizarFaixa() {
    var faixa = document.getElementById("faixa-som");
    if (faixa) faixa.hidden = somLiberado();
  }

  function liberarSom(confirmar) {
    var Contexto = window.AudioContext || window.webkitAudioContext;
    if (!Contexto) return;  // navegador sem WebAudio: fica só o título piscando
    try {
      if (!audio) {
        audio = new Contexto();
        audio.onstatechange = atualizarFaixa;
      }
      if (audio.state !== "running") {
        var p = audio.resume();
        if (p && p.then) {
          p.then(function () {
            atualizarFaixa();
            if (confirmar) bipe();  // toque na faixa: um bipe para provar que o som está ligado
          }, function () {});
        }
      } else if (confirmar) {
        bipe();
      }
    } catch (e) { /* sem som; o título continua avisando */ }
    atualizarFaixa();
  }

  // "Bi-bip" agudo e curto: corta o barulho da cozinha sem precisar de arquivo de áudio.
  function bipe() {
    if (!somLiberado()) return;
    try {
      var t = audio.currentTime;
      [[0, 880], [0.22, 1175]].forEach(function (nota) {
        var osc = audio.createOscillator();
        var volume = audio.createGain();
        osc.type = "square";
        osc.frequency.value = nota[1];
        volume.gain.setValueAtTime(0.0001, t + nota[0]);
        volume.gain.exponentialRampToValueAtTime(0.3, t + nota[0] + 0.01);
        volume.gain.exponentialRampToValueAtTime(0.0001, t + nota[0] + 0.18);
        osc.connect(volume);
        volume.connect(audio.destination);
        osc.start(t + nota[0]);
        osc.stop(t + nota[0] + 0.2);
      });
    } catch (e) { /* um bipe perdido não pode derrubar o painel */ }
  }

  // ---------- alarme + título (relógio de 1 s) ----------
  var tituloBase = document.title;
  var tick = 0;

  function novos() {
    var colunas = document.getElementById("colunas");
    var n = colunas ? parseInt(colunas.dataset.novos, 10) : 0;
    return n > 0 ? n : 0;
  }

  // Lê data-novos a cada segundo: quando a consulta de 5 s troca as colunas, o alarme
  // começa ou para sozinho. Bipe a cada 2 s; título troca a cada 1 s.
  setInterval(function () {
    tick++;
    var n = novos();
    document.title = tituloPiscando(tituloBase, n, tick);
    if (tick % 2 === 0 && deveTocar(n, somLiberado())) bipe();
  }, 1000);

  // ---------- celular: uma etapa por vez ----------
  // As colunas chegam do servidor com a primeira etapa "ativa"; depois de cada troca
  // reaplicamos a aba escolhida. A aba com pedido novo ganha borda amarela, para não
  // passar despercebido quem está olhando outra etapa.
  function aplicarAbas() {
    var colunas = document.getElementById("colunas");
    if (!colunas) return;
    var abas = colunas.querySelectorAll(".painel-etapas a[data-etapa]");
    // Filtro "Agendados" ou uma coluna só: sem abas, mostra tudo (sem "com-abas").
    document.body.classList.toggle("com-abas", abas.length > 0);
    if (!abas.length) return;
    var nomes = Array.prototype.map.call(abas, function (a) { return a.dataset.etapa; });
    var ativa = abaAtiva(ler(CHAVE_ABA), nomes);
    var comNovo = {};
    cada(colunas.querySelectorAll(".coluna[data-etapa]"), function (secao) {
      secao.classList.toggle("ativa", secao.dataset.etapa === ativa);
      comNovo[secao.dataset.etapa] = !!secao.querySelector(".cartao.novo");
    });
    cada(abas, function (a) {
      var eh = a.dataset.etapa === ativa;
      a.classList.toggle("ativa", eh);
      a.classList.toggle("tem-novo", !!comNovo[a.dataset.etapa]);
      if (eh) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current");
    });
  }

  // ---------- olho do total do dia (só Dono) ----------
  // A classe fica no <body>: o bloco do total é trocado a cada consulta e a escolha não se perde.
  function aplicarOlho() {
    var escondido = ler(CHAVE_OLHO) === "1";
    document.body.classList.toggle("total-escondido", escondido);
    var botao = document.querySelector("[data-olho]");
    if (botao) botao.setAttribute("aria-pressed", escondido ? "true" : "false");
  }

  // ---------- detalhe do pedido ----------
  // O detalhe aberto não pode ficar velho: quando o painel muda (outro aparelho, botão do
  // cartão, chegada de pedido), buscamos de novo o mesmo detalhe pela URL dele (data-url).
  // Não recarrega: logo depois de uma resposta do próprio detalhe (já veio atualizado),
  // com pedido do detalhe em andamento, ou com motivo digitado (perderia o texto).
  var aberto = null;        // pk do pedido aberto (para devolver o foco ao cartão)
  var detalheEmVoo = false;
  var ultimoDetalhe = 0;    // quando chegou a última resposta para #detalhe (ms)

  function caixaDetalhe() { return document.getElementById("detalhe"); }
  function raizDetalhe() {
    var caixa = caixaDetalhe();
    return caixa ? caixa.querySelector(".detalhe[data-url]") : null;
  }

  function digitando(caixa) {
    var ativo = document.activeElement;
    if (ativo && caixa.contains(ativo) && (ativo.tagName === "INPUT" || ativo.tagName === "TEXTAREA")) return true;
    return Array.prototype.some.call(caixa.querySelectorAll("input[name=motivo]"), function (i) {
      return i.value.trim() !== "";
    });
  }

  function recarregarDetalhe() {
    var raiz = raizDetalhe();
    if (!raiz || !window.htmx || detalheEmVoo) return;
    if (Date.now() - ultimoDetalhe < 3000 || digitando(caixaDetalhe())) return;
    window.htmx.ajax("GET", raiz.dataset.url, {
      target: "#detalhe", swap: "innerHTML", headers: { "X-Painel-Recarga": "1" },
    });
  }

  // Enter no "Fechar": o botão faz o click já no keydown, o foco volta para o cartão e o
  // keyup do MESMO Enter cai no cartão, que abriria o detalhe de novo. `engolirKeyup` faz o
  // cartão ignorar só esse keyup (é zerado em todo keydown, então nunca sobra para depois).
  var engolirKeyup = false;

  function fecharDetalhe(peloTeclado) {
    var caixa = caixaDetalhe();
    if (!caixa || !raizDetalhe()) return;
    var pk = aberto;
    caixa.innerHTML = "";  // vazio = escondido (CSS :empty)
    detalheFechado();
    if (peloTeclado) engolirKeyup = true;
    var cartao = pk && document.getElementById("pedido-" + pk);
    if (cartao) cartao.focus();  // teclado volta para onde estava
  }

  // Todo caminho que esvazia #detalhe passa por aqui: a página de trás volta a rolar.
  function detalheFechado() {
    aberto = null;
    document.body.classList.remove("detalhe-aberto");
  }

  function eCartao(alvo) {
    return !!(alvo && alvo.classList && alvo.classList.contains("cartao"));
  }

  function eDetalhe(e) {
    var alvo = e.detail && e.detail.target;
    return !!alvo && alvo.id === "detalhe";
  }

  document.body.addEventListener("htmx:beforeRequest", function (e) {
    if (eDetalhe(e)) detalheEmVoo = true;
  });
  document.body.addEventListener("htmx:afterRequest", function (e) {
    if (!eDetalhe(e)) return;
    detalheEmVoo = false;
    ultimoDetalhe = Date.now();
  });

  // Recarga que chega depois de a pessoa fechar o detalhe não pode reabrir o painel.
  document.body.addEventListener("htmx:beforeSwap", function (e) {
    if (!eDetalhe(e) || raizDetalhe()) return;
    var cfg = e.detail.requestConfig;
    if (cfg && cfg.headers && cfg.headers["X-Painel-Recarga"]) e.detail.shouldSwap = false;
  });

  document.body.addEventListener("htmx:afterSwap", function (e) {
    var alvo = e.detail && e.detail.target;
    var id = alvo && alvo.id;
    if (id === "colunas" || (e.target && e.target.id === "colunas")) {
      aplicarAbas();
      aplicarOlho();  // o botão do olho veio novo (troca fora da faixa, hx-swap-oob)
      recarregarDetalhe();
    } else if (id === "detalhe") {
      var raiz = raizDetalhe();
      if (!raiz) { detalheFechado(); return; }  // veio vazio: nada aberto
      var primeiraVez = aberto !== raiz.dataset.pk;
      aberto = raiz.dataset.pk;
      document.body.classList.add("detalhe-aberto");
      // Só ao abrir: leva o foco para o "Fechar" (teclado/leitor de tela). Na recarga, não mexe.
      if (primeiraVez) {
        var fechar = raiz.querySelector("[data-fechar]");
        if (fechar) fechar.focus();
      }
    }
  });

  // Botão do cartão (hx-swap none) ou ação vinda de outro lugar: o detalhe aberto pode ser
  // de um pedido que acabou de mudar. (As colunas recarregam pelo hx-trigger de #colunas.)
  document.body.addEventListener("painel-mudou", function () { recarregarDetalhe(); });

  // ---------- atalho "Avisar no WhatsApp" ----------
  // É um link de verdade (target _blank): o toque é da pessoa, então o navegador não bloqueia.
  var zapTimer = null;

  function esconderZap() {
    var zap = document.getElementById("zap-atalho");
    if (zap) zap.hidden = true;
  }

  function mostrarZap(url, rotulo) {
    if (typeof url !== "string" || url.indexOf("https://wa.me/") !== 0) return;  // só link do WhatsApp
    var zap = document.getElementById("zap-atalho");
    if (!zap) {
      zap = document.createElement("a");
      zap.id = "zap-atalho";
      zap.className = "zap-atalho";
      zap.target = "_blank";
      zap.rel = "noopener";
      zap.setAttribute("role", "status");
      zap.addEventListener("click", function () { setTimeout(esconderZap, 0); });
      document.body.appendChild(zap);
    }
    zap.href = url;
    zap.textContent = "💬 Avisar no WhatsApp";  // textContent: nada do servidor vira HTML
    if (rotulo) {
      var linha = document.createElement("small");
      linha.textContent = rotulo;
      zap.appendChild(linha);
    }
    zap.hidden = false;
    clearTimeout(zapTimer);
    zapTimer = setTimeout(esconderZap, 8000);
  }

  document.body.addEventListener("avisar-whatsapp", function (e) {
    var d = e.detail || {};
    mostrarZap(d.url, d.rotulo);
  });

  // ---------- cliques e teclado (delegação: o HTML é trocado o tempo todo) ----------
  document.addEventListener("click", function (e) {
    // qualquer toque na página serve para liberar o som; o da faixa ainda dá um bipe de teste
    var naFaixa = e.target.closest && e.target.closest("#faixa-som");
    if (naFaixa || !somLiberado()) liberarSom(!!naFaixa);
    if (!e.target.closest) return;

    // detail === 0: o "click" veio do teclado (Enter/Espaço), não do mouse/dedo
    if (e.target.closest("[data-fechar]")) { fecharDetalhe(e.detail === 0); return; }

    var aba = e.target.closest(".painel-etapas a[data-etapa]");
    if (aba) {
      e.preventDefault();  // sem JS a aba é uma âncora; com JS ela só troca a etapa visível
      guardar(CHAVE_ABA, aba.dataset.etapa);
      aplicarAbas();
      return;
    }

    if (e.target.closest("[data-olho]")) {
      guardar(CHAVE_OLHO, ler(CHAVE_OLHO) === "1" ? "0" : "1");
      aplicarOlho();
    }
  });

  // Fase de captura: roda antes do hx-trigger do cartão, então dá para barrar o keyup.
  document.addEventListener("keydown", function () { engolirKeyup = false; }, true);
  document.addEventListener("keyup", function (e) {
    if (!engolirKeyup) return;
    engolirKeyup = false;
    if (eCartao(e.target)) e.stopPropagation();
  }, true);

  document.addEventListener("keydown", function (e) {
    if (!somLiberado()) liberarSom(false);
    if (e.key === "Escape") {
      // Digitando o motivo: o Esc só sai do campo; fechar perderia o texto.
      var ativo = document.activeElement;
      var caixa = caixaDetalhe();
      if (ativo && caixa && caixa.contains(ativo) && /^(INPUT|TEXTAREA|SELECT)$/.test(ativo.tagName)) {
        ativo.blur();
        return;
      }
      fecharDetalhe(true);
      return;
    }
    // Espaço no cartão focado abre o detalhe (o hx-trigger escuta o keyup); aqui só
    // impedimos a página de rolar. No botão de dentro do cartão o Espaço segue normal.
    if (e.key === " " && eCartao(e.target)) e.preventDefault();
  });

  // Aba voltou a aparecer: tenta religar o som (o navegador deixa se já houve toque antes)
  // e mostra a faixa de novo se não der. A consulta das colunas o hx-trigger já faz.
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState !== "visible") return;
    if (audio && audio.state !== "running") {
      try { audio.resume().then(atualizarFaixa, atualizarFaixa); } catch (e) { /* segue */ }
    }
    atualizarFaixa();
  });

  // ---------- começo ----------
  aplicarAbas();
  aplicarOlho();
  atualizarFaixa();
})();
