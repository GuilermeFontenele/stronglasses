// Painel de gestão: pequenos atalhos. Tudo funciona sem JS (formulários comuns).

// Filtros: mudar um select já filtra (o botão "Filtrar" fica para quem está sem JS).
document.querySelectorAll("form[data-filtros]").forEach((form) => {
  form.querySelectorAll("[data-sem-js]").forEach((botao) => (botao.hidden = true));
  form.querySelectorAll("select, input[type=checkbox]").forEach((campo) =>
    campo.addEventListener("change", () => form.requestSubmit()),
  );
});

// Ações em massa: marcar todos e contar selecionados.
document.querySelectorAll("form[data-acoes-em-massa]").forEach((form) => {
  const todos = form.querySelector("[data-selecionar-todos]");
  const caixas = [...form.querySelectorAll('input[name="selecionados"]')];
  const contagem = form.querySelector("[data-contagem-selecao]");
  const atualizar = () => {
    const n = caixas.filter((c) => c.checked).length;
    if (contagem) contagem.textContent = n ? `${n} selecionado(s)` : "Selecione produtos para agir em lote";
    if (todos) {
      todos.checked = n > 0 && n === caixas.length;
      todos.indeterminate = n > 0 && n < caixas.length;
    }
  };
  todos?.addEventListener("change", () => {
    caixas.forEach((c) => (c.checked = todos.checked));
    atualizar();
  });
  caixas.forEach((c) => c.addEventListener("change", atualizar));
});

// Prévia das fotos escolhidas antes de enviar.
document.querySelectorAll("[data-upload]").forEach((bloco) => {
  const entrada = bloco.querySelector('input[type="file"]');
  const previa = bloco.querySelector("[data-previa]");
  if (!entrada || !previa) return;
  entrada.addEventListener("change", () => {
    previa.replaceChildren();
    [...entrada.files].slice(0, 12).forEach((arquivo) => {
      if (!arquivo.type.startsWith("image/")) return;
      const img = document.createElement("img");
      img.alt = "";
      img.src = URL.createObjectURL(arquivo);
      img.addEventListener("load", () => URL.revokeObjectURL(img.src), { once: true });
      previa.append(img);
    });
  });
});

// Menu do celular: fecha com Esc ou ao escolher um item.
document.querySelectorAll(".menu-movel").forEach((menu) => {
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") menu.open = false;
  });
  menu.querySelectorAll("a").forEach((a) => a.addEventListener("click", () => (menu.open = false)));
});

// Ficha do cliente: razão social só aparece para pessoa jurídica.
document.querySelectorAll("form").forEach((form) => {
  const tipo = form.querySelector('select[name="tipo"]');
  const bloco = form.querySelector("[data-so-pj]");
  if (!tipo || !bloco) return;
  const atualizar = () => (bloco.hidden = tipo.value !== "PJ");
  tipo.addEventListener("change", atualizar);
  atualizar();
});

// Linhas reordenáveis (cores e fotos): setas mudam a posição e o campo "ordem" acompanha.
const renumerar = (lista) => {
  [...lista.querySelectorAll(":scope > [data-linha]")].forEach((linha, i) => {
    const ordem = linha.querySelector("[data-ordem]");
    if (ordem) ordem.value = i;
  });
};
document.addEventListener("click", (evento) => {
  const botao = evento.target.closest("[data-subir], [data-descer]");
  if (!botao) return;
  const linha = botao.closest("[data-linha]");
  const lista = linha?.parentElement;
  if (!linha || !lista) return;
  if (botao.hasAttribute("data-subir") && linha.previousElementSibling?.matches("[data-linha]")) {
    lista.insertBefore(linha, linha.previousElementSibling);
  } else if (botao.hasAttribute("data-descer") && linha.nextElementSibling?.matches("[data-linha]")) {
    lista.insertBefore(linha.nextElementSibling, linha);
  }
  renumerar(lista);
  botao.focus();
});
document.querySelectorAll("[data-linhas]").forEach(renumerar);

// "Adicionar cor": clona a linha modelo do formset e atualiza o contador do Django.
document.querySelectorAll("[data-adicionar]").forEach((botao) => {
  const prefixo = botao.dataset.adicionar;
  const modelo = document.querySelector(`template[data-modelo="${prefixo}"]`);
  const total = document.querySelector(`input[name="${prefixo}-TOTAL_FORMS"]`);
  const lista = document.querySelector(`[data-formset="${prefixo}"] [data-linhas]`);
  if (!modelo || !total || !lista) return;
  botao.addEventListener("click", () => {
    const indice = parseInt(total.value, 10);
    const html = modelo.innerHTML.replaceAll("__prefix__", indice);
    lista.insertAdjacentHTML("beforeend", html);
    total.value = indice + 1;
    renumerar(lista);
    lista.querySelector(":scope > [data-linha]:last-of-type select")?.focus();
  });
});

// Linha nova que ainda não foi salva: a lixeira só limpa os campos (o Django ignora linha vazia).
document.addEventListener("click", (evento) => {
  const botao = evento.target.closest("[data-descartar]");
  if (!botao) return;
  const linha = botao.closest("[data-linha]");
  linha.querySelectorAll("input:not([type=hidden]), select").forEach((campo) => {
    if (campo.type === "checkbox") campo.checked = campo.defaultChecked;
    else if (campo.tagName === "SELECT") campo.selectedIndex = 0;
    else campo.value = campo.defaultValue;
  });
  // A última linha visível só é limpa (some a linha, some o lugar de escolher).
  const visiveis = [...linha.parentElement.querySelectorAll(":scope > [data-linha]")].filter((l) => !l.hidden);
  if (visiveis.length > 1) linha.hidden = true;
  linha.dispatchEvent(new Event("input", { bubbles: true }));
});

// Envio de arquivos: mostra o nome escolhido e aceita arrastar e soltar.
document.querySelectorAll("[data-arquivo]").forEach((bloco) => {
  const entrada = bloco.querySelector('input[type="file"]');
  const nome = bloco.querySelector("[data-arquivo-nome]");
  entrada?.addEventListener("change", () => {
    if (nome) nome.textContent = entrada.files[0] ? entrada.files[0].name : "";
  });
});
document.querySelectorAll(".soltar-arquivos").forEach((zona) => {
  const entrada = zona.querySelector('input[type="file"]');
  ["dragenter", "dragover"].forEach((tipo) =>
    zona.addEventListener(tipo, (e) => {
      e.preventDefault();
      zona.classList.add("arrastando");
    }),
  );
  ["dragleave", "drop"].forEach((tipo) => zona.addEventListener(tipo, () => zona.classList.remove("arrastando")));
  zona.addEventListener("drop", (e) => {
    e.preventDefault();
    if (!entrada || !e.dataTransfer?.files.length) return;
    entrada.files = e.dataTransfer.files;
    entrada.dispatchEvent(new Event("change"));
  });
});

// Página de impressão (etiqueta e declaração).
document.querySelectorAll("[data-imprimir]").forEach((botao) => botao.addEventListener("click", () => window.print()));

// Lançar venda: mostra só os campos que fazem sentido e calcula o resumo enquanto digita.
// É só uma prévia: o servidor recalcula tudo ao salvar (preço -> desconto -> Pix -> frete).
document.querySelectorAll("form[data-venda]").forEach((form) => {
  const real = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  const numero = (campo) => {
    const valor = parseFloat(String(campo?.value || "").replace(",", "."));
    return Number.isFinite(valor) && valor > 0 ? valor : 0;
  };
  const centavos = (valor) => Math.round(valor * 100) / 100;
  const pixPercentual = parseFloat(form.dataset.pix || "0") || 0;
  const forma = form.querySelector("[data-venda-forma]");
  const pix = form.querySelector("[data-venda-pix]");
  const entrega = form.querySelector("[data-venda-entrega]");
  const endereco = form.querySelector("[data-endereco]");
  const escrever = (chave, texto) => {
    const alvo = form.querySelector(`[data-resumo="${chave}"]`);
    if (alvo) alvo.textContent = texto;
  };

  const atualizar = () => {
    let subtotal = 0;
    form.querySelectorAll("[data-item]").forEach((linha) => {
      const opcao = linha.querySelector("[data-item-variacao]")?.selectedOptions[0];
      const quantidade = parseInt(linha.querySelector("[data-item-quantidade]")?.value || "0", 10) || 0;
      const precoCampo = linha.querySelector("[data-item-preco]");
      const precoLoja = parseFloat(opcao?.dataset.preco || "0") || 0;
      if (precoCampo) precoCampo.placeholder = precoLoja ? precoLoja.toFixed(2).replace(".", ",") : "Da loja";
      const preco = precoCampo && precoCampo.value !== "" ? numero(precoCampo) : precoLoja;
      const valor = linha.hidden || !opcao?.value ? 0 : centavos(preco * quantidade);
      const celula = linha.querySelector("[data-item-subtotal]");
      if (celula) celula.textContent = valor ? real.format(valor) : "—";
      const aviso = linha.querySelector("[data-item-aviso]");
      const estoque = parseInt(opcao?.dataset.estoque ?? "", 10);
      if (aviso) {
        const falta = opcao?.value && Number.isFinite(estoque) && quantidade > estoque;
        aviso.hidden = !falta;
        aviso.textContent = falta ? `Só ${Math.max(estoque, 0)} em estoque` : "";
      }
      subtotal += valor;
    });
    const desconto = Math.min(numero(form.querySelector("[data-venda-desconto]")), subtotal);
    const base = subtotal - desconto;
    const usaPix = forma?.value === "pix" && pix?.checked && pixPercentual > 0;
    const descontoPix = usaPix ? centavos((base * pixPercentual) / 100) : 0;
    const frete = numero(form.querySelector("[data-venda-frete]"));
    escrever("subtotal", real.format(subtotal));
    escrever("desconto", `− ${real.format(desconto)}`);
    escrever("pix", `− ${real.format(descontoPix)}`);
    escrever("frete", real.format(frete));
    escrever("total", real.format(centavos(base - descontoPix + frete)));
    const linhaPix = form.querySelector('[data-resumo-linha="pix"]');
    if (linhaPix) linhaPix.hidden = !usaPix;
    form.querySelectorAll("[data-so-pix]").forEach((bloco) => (bloco.hidden = forma?.value !== "pix" || !pixPercentual));
    form.querySelectorAll("[data-so-credito]").forEach((bloco) => (bloco.hidden = forma?.value !== "credito"));
    if (endereco && entrega) endereco.hidden = entrega.value === "maos";
  };

  form.addEventListener("input", atualizar);
  form.addEventListener("change", atualizar);
  form.querySelector("[data-adicionar]")?.addEventListener("click", () => requestAnimationFrame(atualizar));
  atualizar();
});

// CEP: 60000000 vira 60000-000 enquanto digita.
document.querySelectorAll('input[name="cep"]').forEach((campo) =>
  campo.addEventListener("input", () => {
    const d = campo.value.replace(/\D/g, "").slice(0, 8);
    campo.value = d.length > 5 ? `${d.slice(0, 5)}-${d.slice(5)}` : d;
  }),
);
