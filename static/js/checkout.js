// Finalizar compra: máscaras, cálculo de frete e resumo ao vivo. O servidor recalcula tudo ao enviar.
const form = document.querySelector("form[data-checkout]");

const MASCARAS = {
  cep: (d) => (d.length > 5 ? `${d.slice(0, 5)}-${d.slice(5, 8)}` : d),
  documento: (d) =>
    d
      .slice(0, 11)
      .replace(/^(\d{3})(\d)/, "$1.$2")
      .replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/\.(\d{3})(\d{1,2})$/, ".$1-$2"),
  telefone: (d) => {
    if (d.startsWith("55") && d.length > 11) d = d.slice(2);
    d = d.slice(0, 11);
    if (d.length <= 2) return d ? `(${d}` : "";
    const corte = d.length > 10 ? 7 : 6;
    return d.length > 6 ? `(${d.slice(0, 2)}) ${d.slice(2, corte)}-${d.slice(corte)}` : `(${d.slice(0, 2)}) ${d.slice(2)}`;
  },
};
document.querySelectorAll("input[data-mascara]").forEach((campo) => {
  const mascara = MASCARAS[campo.dataset.mascara];
  if (!mascara) return;
  const aplicar = () => {
    const d = campo.value.replace(/\D/g, "");
    campo.value = d ? mascara(d) : "";
  };
  campo.addEventListener("input", aplicar);
  aplicar();
});

if (form) {
  const real = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  const subtotal = parseFloat(form.dataset.subtotal || "0");
  const pixPercentual = parseFloat(form.dataset.pix || "0");
  const campoFrete = form.querySelector('input[name="frete"]');
  const lista = form.querySelector("[data-frete-opcoes]");
  const status = form.querySelector("[data-frete-status]");
  const botao = form.querySelector("[data-calcular-frete]");
  const cep = form.querySelector('input[name="cep"]');
  let precoFrete = null;

  const resumo = () => {
    const pix = form.querySelector('input[name="forma"]:checked')?.value === "pix";
    const desconto = pix ? Math.round(subtotal * pixPercentual) / 100 : 0;
    form.querySelector("[data-linha-pix]").hidden = !pix || !desconto;
    form.querySelector("[data-resumo-pix]").textContent = `− ${real.format(desconto)}`;
    form.querySelector("[data-resumo-frete]").textContent =
      precoFrete === null ? "a calcular" : precoFrete === 0 ? "Grátis" : real.format(precoFrete);
    form.querySelector("[data-resumo-total]").textContent = real.format(subtotal - desconto + (precoFrete || 0));
  };

  const calcular = async () => {
    const digitos = cep.value.replace(/\D/g, "");
    if (digitos.length !== 8) {
      status.textContent = "Informe o CEP com 8 números.";
      cep.focus();
      return;
    }
    botao.disabled = true;
    status.textContent = "Calculando…";
    lista.replaceChildren();
    campoFrete.value = "";
    precoFrete = null;
    resumo();
    const dados = new FormData();
    dados.append("csrfmiddlewaretoken", form.querySelector("[name=csrfmiddlewaretoken]").value);
    dados.append("cep", digitos);
    try {
      const resposta = await fetch(form.dataset.urlFrete, { method: "POST", body: dados, credentials: "same-origin" });
      const json = await resposta.json();
      if (!resposta.ok) throw new Error(json.erro || "Não foi possível calcular agora.");
      json.opcoes.forEach((opcao, i) => {
        const item = document.createElement("label");
        item.className = "opcao-entrega";
        const radio = document.createElement("input");
        radio.type = "radio";
        radio.name = "_entrega";
        radio.value = opcao.id;
        const texto = document.createElement("span");
        const nome = document.createElement("strong");
        nome.textContent = opcao.nome;
        const prazo = document.createElement("small");
        prazo.textContent = opcao.prazo;
        texto.append(nome, prazo);
        const preco = document.createElement("b");
        preco.textContent = Number(opcao.preco) === 0 ? "Grátis" : real.format(Number(opcao.preco));
        item.append(radio, texto, preco);
        radio.addEventListener("change", () => {
          campoFrete.value = opcao.id;
          precoFrete = Number(opcao.preco);
          resumo();
        });
        lista.append(item);
        if (i === 0) {
          radio.checked = true;
          radio.dispatchEvent(new Event("change"));
        }
      });
      status.textContent = "Escolha como quer receber:";
    } catch (erro) {
      status.textContent = erro.message;
    } finally {
      botao.disabled = false;
    }
  };

  botao.addEventListener("click", calcular);
  cep.addEventListener("input", () => {
    if (cep.value.replace(/\D/g, "").length === 8 && !campoFrete.value) calcular();
  });
  form.querySelectorAll('input[name="forma"]').forEach((r) => r.addEventListener("change", resumo));
  form.addEventListener("submit", (e) => {
    if (!campoFrete.value) {
      e.preventDefault();
      status.textContent = "Calcule o frete e escolha uma opção antes de continuar.";
      cep.focus();
    }
  });
  if (cep.value.replace(/\D/g, "").length === 8) calcular();
  resumo();
}
