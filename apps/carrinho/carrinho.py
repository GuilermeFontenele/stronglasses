"""Carrinho guardado na sessão: só IDs de variação e quantidades (nenhum dado pessoal).

Preços e totais são sempre recalculados no servidor a partir do banco.
Ordem do cálculo (CLAUDE.md): preço → promoção → cupom → Pix → frete. Promoção e cupom
entram quando o motor de promoções existir.
"""

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Prefetch

from apps.catalogo.models import ImagemProduto, Variacao
from apps.catalogo.vitrine import parcela, preco_pix

CHAVE_SESSAO = "carrinho"
MAXIMO_POR_ITEM = 10


@dataclass
class Linha:
    variacao: Variacao
    quantidade: int
    foto: ImagemProduto | None

    @property
    def preco_unitario(self) -> Decimal:
        return self.variacao.preco_final

    @property
    def subtotal(self) -> Decimal:
        return self.preco_unitario * self.quantidade


class Carrinho:
    def __init__(self, request):
        self.sessao = request.session
        bruto = self.sessao.get(CHAVE_SESSAO)
        self.itens: dict[str, int] = {}
        if isinstance(bruto, dict):  # a sessão é assinada, mas não custa desconfiar
            for chave, quantidade in bruto.items():
                if str(chave).isdigit() and isinstance(quantidade, int) and 0 < quantidade <= MAXIMO_POR_ITEM:
                    self.itens[str(chave)] = quantidade

    def __len__(self) -> int:
        return sum(self.itens.values())

    def _salvar(self) -> None:
        self.sessao[CHAVE_SESSAO] = self.itens
        self.sessao.modified = True

    def adicionar(self, variacao: Variacao, quantidade: int = 1) -> int:
        """Soma ao que já existe, respeitando estoque e limite. Devolve quanto entrou de fato."""
        atual = self.itens.get(str(variacao.pk), 0)
        nova = max(min(atual + max(quantidade, 0), MAXIMO_POR_ITEM, variacao.estoque), 0)
        if nova:
            self.itens[str(variacao.pk)] = nova
            self._salvar()
        return max(nova - atual, 0)

    def definir(self, variacao: Variacao, quantidade: int) -> None:
        quantidade = max(min(quantidade, MAXIMO_POR_ITEM, variacao.estoque), 0)
        if quantidade:
            self.itens[str(variacao.pk)] = quantidade
        else:
            self.itens.pop(str(variacao.pk), None)
        self._salvar()

    def remover(self, variacao_id) -> None:
        if self.itens.pop(str(variacao_id), None) is not None:
            self._salvar()

    def limpar(self) -> None:
        self.itens = {}
        self._salvar()

    def linhas(self) -> list[Linha]:
        """Itens válidos com dados atuais do banco. Some do carrinho o que saiu de linha ou de estoque."""
        if not self.itens:
            return []
        variacoes = (
            Variacao.objects.filter(pk__in=self.itens, ativa=True, produto__ativo=True)
            .select_related("produto", "armacao", "lente")
            .prefetch_related(
                Prefetch("produto__imagens", queryset=ImagemProduto.objects.order_by("ordem", "id"), to_attr="fotos")
            )
        )
        linhas, validos = [], {}
        for variacao in sorted(variacoes, key=lambda v: list(self.itens).index(str(v.pk))):
            quantidade = min(self.itens[str(variacao.pk)], variacao.estoque)
            if quantidade <= 0:
                continue
            fotos = variacao.produto.fotos
            foto = next((f for f in fotos if f.variacao_id == variacao.pk), fotos[0] if fotos else None)
            linhas.append(Linha(variacao, quantidade, foto))
            validos[str(variacao.pk)] = quantidade
        if validos != self.itens:
            self.itens = validos
            self._salvar()
        return linhas

    @staticmethod
    def resumo(linhas: list[Linha]) -> dict:
        subtotal = sum((linha.subtotal for linha in linhas), Decimal("0.00"))
        vezes, valor_parcela = parcela(subtotal) if subtotal else (1, Decimal("0.00"))
        return {
            "quantidade": sum(linha.quantidade for linha in linhas),
            "subtotal": subtotal,
            "total_pix": preco_pix(subtotal) if subtotal else subtotal,  # Pix não incide sobre o frete
            "vezes": vezes,
            "parcela": valor_parcela,
        }
