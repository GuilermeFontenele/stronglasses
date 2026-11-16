// Cartão pelo Brick do Mercado Pago: os dados do cartão viram um token no navegador e só o token vem para cá.
const caixa = document.querySelector("[data-cartao]");
const erro = document.querySelector("[data-erro-cartao]");

const mostrarErro = (texto) => {
  erro.textContent = texto;
  erro.hidden = !texto;
  if (texto) erro.scrollIntoView({ behavior: "smooth", block: "center" });
};

if (caixa && window.MercadoPago) {
  const csrf = caixa.dataset.csrf || "";
  const mp = new window.MercadoPago(caixa.dataset.chave, { locale: "pt-BR" });
  mp.bricks().create("cardPayment", caixa.id, {
    initialization: { amount: Number(caixa.dataset.valor), payer: { email: caixa.dataset.email || undefined } },
    customization: {
      paymentMethods: { maxInstallments: Number(caixa.dataset.parcelas || 1) },
      visual: { style: { theme: "default" } },
    },
    callbacks: {
      onReady: () => caixa.querySelector("[data-carregando]")?.remove(),
      onSubmit: (dados) =>
        new Promise((resolve, reject) => {
          mostrarErro("");
          fetch(caixa.dataset.url, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
            body: JSON.stringify(dados),
          })
            .then(async (resposta) => {
              const json = await resposta.json().catch(() => ({}));
              if (resposta.ok) {
                resolve();
                window.location.href = json.url || caixa.dataset.voltar;
              } else {
                mostrarErro(json.mensagem || "Não foi possível pagar. Tente de novo.");
                reject();
              }
            })
            .catch(() => {
              mostrarErro("Sem conexão. Confira a internet e tente de novo.");
              reject();
            });
        }),
      onError: () => mostrarErro("Confira os dados do cartão."),
    },
  });
} else if (caixa) {
  mostrarErro("Não foi possível carregar o pagamento seguro. Desative bloqueadores e recarregue a página.");
}
