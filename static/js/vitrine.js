// Comportamentos da vitrine. Tudo funciona sem JS; aqui só fica mais agradável.
const reduzirMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Contador da home: sobe de 0 até o número quando aparece na tela.
// Sem JS (ou com "reduzir movimento" ligado) o número final já vem no HTML.
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
      const suave = 1 - Math.pow(1 - progresso, 3);
      el.textContent = formatar(Math.round(alvo * suave));
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

// Galeria do produto: clicar na miniatura troca a foto grande sem pular a página,
// e arrastar a foto grande atualiza a miniatura marcada.
(() => {
  for (const galeria of document.querySelectorAll("[data-galeria]")) {
    const trilho = galeria.querySelector(".galeria-principal");
    const fotos = trilho ? [...trilho.querySelectorAll("img")] : [];
    const links = [...galeria.querySelectorAll(".galeria-miniaturas a")];
    if (fotos.length < 2 || !links.length) continue;

    const marcar = (indice) => {
      links.forEach((link, i) => link.setAttribute("aria-current", i === indice ? "true" : "false"));
    };

    links.forEach((link, indice) => {
      link.addEventListener("click", (evento) => {
        evento.preventDefault();
        trilho.scrollTo({ left: indice * trilho.clientWidth, behavior: reduzirMovimento ? "auto" : "smooth" });
        marcar(indice);
      });
    });

    if ("IntersectionObserver" in window) {
      const observador = new IntersectionObserver(
        (entradas) => {
          for (const entrada of entradas) {
            if (entrada.isIntersecting) marcar(fotos.indexOf(entrada.target));
          }
        },
        { root: trilho, threshold: 0.6 },
      );
      fotos.forEach((foto) => observador.observe(foto));
    }
  }
})();
