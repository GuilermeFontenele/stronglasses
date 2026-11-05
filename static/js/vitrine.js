// Comportamentos da vitrine. Tudo funciona sem JS; aqui só fica mais agradável.
const reduzirMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const ehCelular = () => window.matchMedia("(max-width: 719px)").matches;

// Topo transparente da home: vira branco e fixo depois que a pessoa rola a página.
(() => {
  const cabecalho = document.querySelector("[data-cabecalho].transparente");
  if (!cabecalho) return;
  const limite = () => cabecalho.offsetHeight + 40;
  let fixo = false;
  const atualizar = () => {
    const passou = window.scrollY > limite();
    if (passou !== fixo) {
      fixo = passou;
      cabecalho.classList.toggle("solido", passou);
      cabecalho.classList.toggle("fixo", passou);
    }
  };
  window.addEventListener("scroll", atualizar, { passive: true });
  atualizar();
})();

// Menu lateral: botão fechar, tecla Esc e fechar ao escolher um link.
(() => {
  const menu = document.querySelector("[data-menu]");
  if (!menu) return;
  const resumo = menu.querySelector("summary");
  const fechar = () => {
    menu.open = false;
    resumo.focus();
  };
  const botao = menu.querySelector("[data-fechar-menu]");
  if (botao) {
    botao.hidden = false;
    botao.addEventListener("click", fechar);
  }
  menu.addEventListener("toggle", () => {
    document.documentElement.classList.toggle("sem-rolagem", menu.open);
    if (menu.open) menu.querySelector(".menu-categorias a, .menu-extra a")?.focus();
  });
  document.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape" && menu.open) fechar();
  });
  menu.querySelectorAll(".menu-painel a").forEach((link) => link.addEventListener("click", () => (menu.open = false)));
})();

// Contador da home: sobe de 0 até o número quando aparece na tela.
(() => {
  const contadores = document.querySelectorAll("[data-contador]");
  if (!contadores.length || reduzirMovimento || !("IntersectionObserver" in window)) return;
  const formatar = (n) => "+" + n.toLocaleString("pt-BR");
  const animar = (el) => {
    const alvo = parseInt(el.dataset.contador, 10) || 0;
    const duracao = 2200;
    let inicio = null;
    const passo = (agora) => {
      if (inicio === null) inicio = agora;
      const progresso = Math.min((agora - inicio) / duracao, 1);
      el.textContent = formatar(Math.round(alvo * (1 - Math.pow(1 - progresso, 3))));
      if (progresso < 1) requestAnimationFrame(passo);
    };
    requestAnimationFrame(passo);
  };
  const observador = new IntersectionObserver(
    (entradas) => {
      for (const entrada of entradas) {
        if (entrada.isIntersecting) {
          observador.unobserve(entrada.target);
          animar(entrada.target);
        }
      }
    },
    { threshold: 0.4 },
  );
  for (const el of contadores) {
    el.textContent = formatar(0);
    observador.observe(el);
  }
})();

// Vídeo do banner: escolhe a versão (celular/computador) e só toca se a pessoa não
// pediu menos movimento nem economia de dados. Até carregar, a imagem aparece.
(() => {
  const economia = navigator.connection && navigator.connection.saveData;
  if (reduzirMovimento || economia) return;
  for (const video of document.querySelectorAll("video[data-video]")) {
    const fonte = (ehCelular() && video.dataset.videoCelular) || video.dataset.video;
    video.src = fonte;
    video.addEventListener("playing", () => video.classList.add("tocando"), { once: true });
    video.play().catch(() => {});
  }
})();

// Trilhos com setas: carrossel de banners e fileiras de produtos.
const ligarTrilho = (raiz, { automatico = false } = {}) => {
  const trilho = raiz.querySelector("[data-trilho]");
  const anterior = raiz.querySelector("[data-anterior]");
  const proximo = raiz.querySelector("[data-proximo]");
  const pontos = raiz.querySelector("[data-pontos]");
  if (!trilho) return;
  const passo = () => trilho.clientWidth * (automatico ? 1 : 0.9);
  const mover = (direcao) => {
    const fim = trilho.scrollWidth - trilho.clientWidth - 2;
    let destino = trilho.scrollLeft + direcao * passo();
    if (automatico && direcao > 0 && trilho.scrollLeft >= fim) destino = 0; // banner volta ao início
    if (automatico && direcao < 0 && trilho.scrollLeft <= 2) destino = fim;
    trilho.scrollTo({ left: destino, behavior: reduzirMovimento ? "auto" : "smooth" });
  };
  const atualizar = () => {
    const fim = trilho.scrollWidth - trilho.clientWidth - 2;
    const cabe = fim <= 0;
    if (anterior) {
      anterior.hidden = cabe;
      anterior.disabled = !automatico && trilho.scrollLeft <= 2;
    }
    if (proximo) {
      proximo.hidden = cabe;
      proximo.disabled = !automatico && trilho.scrollLeft >= fim;
    }
    if (pontos) {
      const atual = Math.round(trilho.scrollLeft / trilho.clientWidth);
      pontos.querySelectorAll("button").forEach((b, i) => b.setAttribute("aria-current", i === atual ? "true" : "false"));
    }
  };
  anterior?.addEventListener("click", () => mover(-1));
  proximo?.addEventListener("click", () => mover(1));
  if (pontos) {
    pontos.hidden = false;
    pontos.querySelectorAll("button").forEach((b, i) =>
      b.addEventListener("click", () => trilho.scrollTo({ left: i * trilho.clientWidth, behavior: reduzirMovimento ? "auto" : "smooth" })),
    );
  }
  trilho.addEventListener("scroll", () => requestAnimationFrame(atualizar), { passive: true });
  window.addEventListener("resize", atualizar);
  atualizar();

  if (automatico && !reduzirMovimento && pontos) {
    let pausado = false;
    const pausar = () => (pausado = true);
    const continuar = () => (pausado = false);
    raiz.addEventListener("mouseenter", pausar);
    raiz.addEventListener("mouseleave", continuar);
    raiz.addEventListener("focusin", pausar);
    raiz.addEventListener("focusout", continuar);
    raiz.addEventListener("touchstart", pausar, { passive: true });
    setInterval(() => {
      if (!pausado && !document.hidden) mover(1);
    }, 6000);
  }
};
document.querySelectorAll("[data-carrossel]").forEach((raiz) => ligarTrilho(raiz, { automatico: true }));
document.querySelectorAll("[data-fileira]").forEach((raiz) => ligarTrilho(raiz));

// Galeria do produto: clicar na miniatura troca a foto grande sem pular a página.
(() => {
  for (const galeria of document.querySelectorAll("[data-galeria]")) {
    const trilho = galeria.querySelector(".galeria-principal");
    const fotos = trilho ? [...trilho.querySelectorAll("img")] : [];
    const links = [...galeria.querySelectorAll(".galeria-miniaturas a")];
    if (fotos.length < 2 || !links.length) continue;
    const marcar = (indice) => links.forEach((link, i) => link.setAttribute("aria-current", i === indice ? "true" : "false"));
    links.forEach((link, indice) => {
      link.addEventListener("click", (evento) => {
        evento.preventDefault();
        trilho.scrollTo({ left: indice * trilho.clientWidth, behavior: reduzirMovimento ? "auto" : "smooth" });
        marcar(indice);
      });
    });
    if ("IntersectionObserver" in window) {
      const observador = new IntersectionObserver(
        (entradas) => entradas.forEach((e) => e.isIntersecting && marcar(fotos.indexOf(e.target))),
        { root: trilho, threshold: 0.6 },
      );
      fotos.forEach((foto) => observador.observe(foto));
    }
  }
})();

// Carrinho: trocar a quantidade já envia (o botão "Atualizar" fica só para quem está sem JS).
document.querySelectorAll("form[data-auto-enviar]").forEach((form) => {
  form.querySelectorAll("[data-sem-js]").forEach((b) => (b.hidden = true));
  form.querySelector("select")?.addEventListener("change", () => form.requestSubmit());
});
