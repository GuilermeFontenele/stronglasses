// Contador da home: sobe de 0 até o número quando aparece na tela.
// Sem JS (ou com "reduzir movimento" ligado) o número final já vem no HTML.
(() => {
  const contadores = document.querySelectorAll("[data-contador]");
  const reduzir = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!contadores.length || reduzir || !("IntersectionObserver" in window)) return;

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
