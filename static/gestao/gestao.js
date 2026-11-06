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
