// Página do pedido: copia o Pix e confere sozinha se o pagamento caiu.
document.querySelectorAll("[data-copiar]").forEach((botao) =>
  botao.addEventListener("click", async () => {
    const campo = document.querySelector(botao.dataset.copiar);
    try {
      await navigator.clipboard.writeText(campo.value);
    } catch {
      campo.select();
      document.execCommand("copy");
    }
    const original = botao.textContent;
    botao.textContent = "Código copiado!";
    setTimeout(() => (botao.textContent = original), 2500);
  }),
);

const bloco = document.querySelector("[data-pedido]");
if (bloco && bloco.dataset.situacao === "pendente") {
  let tentativas = 0;
  const conferir = async () => {
    tentativas += 1;
    try {
      const resposta = await fetch(bloco.dataset.urlSituacao, { credentials: "same-origin" });
      const json = await resposta.json();
      if (json.situacao !== "pendente") {
        window.location.reload();
        return;
      }
    } catch {
      /* rede instável: tenta de novo */
    }
    if (tentativas < 360) setTimeout(conferir, tentativas < 60 ? 5000 : 15000);
  };
  setTimeout(conferir, 5000);
}
