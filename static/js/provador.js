// Provador virtual 2D: acha o rosto na câmera (MediaPipe, rodando no próprio aparelho) e desenha
// a foto de frente do óculos, sem fundo, alinhada aos olhos. Nenhuma imagem sai do aparelho.

const dialogo = document.querySelector("[data-provador]");
const botaoAbrir = document.querySelector("[data-abrir-provador]");

if (dialogo && botaoAbrir) {
  const ativos = dialogo.dataset.ativos;
  const video = dialogo.querySelector("[data-provador-video]");
  const tela = dialogo.querySelector("[data-provador-tela]");
  const ctx = tela.getContext("2d");
  const status = dialogo.querySelector("[data-provador-status]");
  const botaoFoto = dialogo.querySelector("[data-provador-foto]");
  const tamanho = dialogo.querySelector("[data-provador-tamanho]");
  const cores = [...dialogo.querySelectorAll("[data-provador-cor]")];

  // Pontos do rosto (malha de 478 pontos do MediaPipe).
  const OLHO_DIR_EXT = 33; // canto externo do olho direito da pessoa
  const OLHO_DIR_INT = 133;
  const OLHO_ESQ_EXT = 263;
  const OLHO_ESQ_INT = 362;
  const LADO_DIR = 127; // lateral do rosto na altura dos olhos
  const LADO_ESQ = 356;
  const ALTURA_DOS_OLHOS = 0.45; // onde fica a linha dos olhos na imagem do óculos (0 = topo)

  let detector = null;
  let fluxo = null;
  let animacao = null;
  let ultimoTempo = -1;
  let oculos = new Image();
  let suave = null; // posição suavizada (evita tremer)

  const avisar = (texto) => {
    status.textContent = texto;
    status.hidden = !texto;
  };

  const escolherCor = (alvo) => {
    cores.forEach((c) => c.setAttribute("aria-pressed", String(c === alvo)));
    const nova = new Image();
    nova.decoding = "async";
    nova.src = alvo.dataset.src;
    nova.onload = () => (oculos = nova);
  };
  cores.forEach((c) => c.addEventListener("click", () => escolherCor(c)));

  async function carregarDetector() {
    if (detector) return detector;
    const { FaceLandmarker } = await import(`${ativos}vision_bundle.mjs`);
    const arquivos = {
      wasmLoaderPath: `${ativos}wasm/vision_wasm_internal.js`,
      wasmBinaryPath: `${ativos}wasm/vision_wasm_internal.wasm`,
    };
    const opcoes = (delegate) => ({
      baseOptions: { modelAssetPath: `${ativos}face_landmarker.task`, delegate },
      runningMode: "VIDEO",
      numFaces: 1,
    });
    try {
      detector = await FaceLandmarker.createFromOptions(arquivos, opcoes("GPU"));
    } catch {
      detector = await FaceLandmarker.createFromOptions(arquivos, opcoes("CPU"));
    }
    return detector;
  }

  async function abrir() {
    dialogo.showModal();
    suave = null;
    botaoFoto.disabled = true;
    const inicial = cores.find((c) => c.getAttribute("aria-pressed") === "true") || cores[0];
    if (inicial) escolherCor(inicial);
    if (!navigator.mediaDevices?.getUserMedia) {
      avisar("Este navegador não libera a câmera. Tente pelo Chrome ou Safari atualizado.");
      return;
    }
    try {
      avisar("Abrindo a câmera…");
      fluxo = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 960 }, height: { ideal: 1280 } },
        audio: false,
      });
      video.srcObject = fluxo;
      await video.play();
      avisar("Carregando o provador (só na primeira vez demora um pouco)…");
      await carregarDetector();
      if (!dialogo.open) return fechar();
      avisar("Olhe para a câmera");
      desenhar();
    } catch (erro) {
      const negou = erro?.name === "NotAllowedError" || erro?.name === "SecurityError";
      avisar(
        negou
          ? "Precisamos da sua permissão para usar a câmera. Libere no ícone do cadeado, ao lado do endereço do site."
          : "Não foi possível abrir o provador neste aparelho.",
      );
    }
  }

  function fechar() {
    cancelAnimationFrame(animacao);
    animacao = null;
    fluxo?.getTracks().forEach((t) => t.stop());
    fluxo = null;
    video.srcObject = null;
    if (dialogo.open) dialogo.close();
  }

  function desenhar() {
    animacao = requestAnimationFrame(desenhar);
    if (video.readyState < 2) return;
    const largura = video.videoWidth;
    const altura = video.videoHeight;
    if (tela.width !== largura || tela.height !== altura) {
      tela.width = largura;
      tela.height = altura;
    }
    // Espelhado, como um espelho de verdade.
    ctx.save();
    ctx.translate(largura, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(video, 0, 0, largura, altura);
    ctx.restore();

    if (video.currentTime !== ultimoTempo) {
      ultimoTempo = video.currentTime;
      const resultado = detector.detectForVideo(video, performance.now());
      const pontos = resultado.faceLandmarks?.[0];
      if (pontos) {
        // x espelhado para casar com a imagem desenhada
        const p = (i) => ({ x: (1 - pontos[i].x) * largura, y: pontos[i].y * altura });
        const meio = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
        const olhoA = meio(p(OLHO_DIR_EXT), p(OLHO_DIR_INT));
        const olhoB = meio(p(OLHO_ESQ_EXT), p(OLHO_ESQ_INT));
        const ladoA = p(LADO_DIR);
        const ladoB = p(LADO_ESQ);
        const alvo = {
          x: (olhoA.x + olhoB.x) / 2,
          y: (olhoA.y + olhoB.y) / 2,
          angulo: Math.atan2(olhoB.y - olhoA.y, olhoB.x - olhoA.x),
          largura: Math.hypot(ladoB.x - ladoA.x, ladoB.y - ladoA.y),
        };
        // Normaliza o ângulo (o espelho pode inverter a ordem dos olhos).
        if (alvo.angulo > Math.PI / 2) alvo.angulo -= Math.PI;
        if (alvo.angulo < -Math.PI / 2) alvo.angulo += Math.PI;
        const k = 0.45;
        suave = suave
          ? Object.fromEntries(Object.keys(alvo).map((c) => [c, suave[c] + (alvo[c] - suave[c]) * k]))
          : alvo;
        avisar("");
        botaoFoto.disabled = false;
      } else {
        suave = null;
        avisar("Centralize o rosto na câmera");
        botaoFoto.disabled = true;
      }
    }

    if (suave && oculos.complete && oculos.naturalWidth) {
      const w = suave.largura * Number(tamanho.value || 1);
      const h = (w * oculos.naturalHeight) / oculos.naturalWidth;
      ctx.save();
      ctx.translate(suave.x, suave.y);
      ctx.rotate(suave.angulo);
      ctx.drawImage(oculos, -w / 2, -h * ALTURA_DOS_OLHOS, w, h);
      ctx.restore();
    }
  }

  async function tirarFoto() {
    const blob = await new Promise((ok) => tela.toBlob(ok, "image/jpeg", 0.9));
    if (!blob) return;
    const arquivo = new File([blob], "provador-strong-glasses.jpg", { type: "image/jpeg" });
    if (navigator.canShare?.({ files: [arquivo] })) {
      try {
        await navigator.share({ files: [arquivo], title: document.title });
        return;
      } catch (erro) {
        if (erro?.name === "AbortError") return;
      }
    }
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = arquivo.name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 2000);
  }

  botaoAbrir.addEventListener("click", abrir);
  dialogo.querySelector("[data-fechar-provador]").addEventListener("click", fechar);
  dialogo.addEventListener("close", fechar);
  dialogo.addEventListener("cancel", fechar);
  botaoFoto.addEventListener("click", tirarFoto);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && dialogo.open) fechar();
  });
}
