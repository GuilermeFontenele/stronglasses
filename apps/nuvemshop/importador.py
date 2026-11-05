"""Importação da Nuvemshop para o sistema próprio.

Idempotente: rodar de novo atualiza o que já existe (chave = ID da Nuvemshop).
LGPD: CPF/CNPJ vão cifrados e o endereço completo vai para `Endereco` (necessários para continuar
enviando pedidos). Titulares anonimizados nunca são reimportados.
"""

import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.text import slugify

from apps.catalogo.models import AcabamentoArmacao, Categoria, CorLente, ImagemProduto, Produto, Variacao
from apps.clientes.models import Cliente, Consentimento, Endereco
from apps.core.crypto import hash_busca
from apps.core.parametros import get_parametro
from apps.historico.models import ItemPedidoHistorico, PedidoHistorico

from . import mapeamento as m
from .imagens import ImagemInvalida, baixar_imagem

logger = logging.getLogger(__name__)

ETAPAS = ("categorias", "produtos", "clientes", "pedidos", "cupons")


@dataclass
class Relatorio:
    contagem: Counter = field(default_factory=Counter)
    pendencias: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    def conta(self, chave: str, n: int = 1):
        self.contagem[chave] += n

    def pendencia(self, grupo: str, texto: str):
        if texto not in self.pendencias[grupo]:
            self.pendencias[grupo].append(texto)

    def em_markdown(self) -> str:
        linhas = ["# Relatório da importação da Nuvemshop", "", "## Números", ""]
        linhas += [f"- {chave}: {valor}" for chave, valor in sorted(self.contagem.items())]
        if self.pendencias:
            linhas += ["", "## Para revisar no painel", ""]
            for grupo, itens in self.pendencias.items():
                linhas += [f"### {grupo} ({len(itens)})", ""] + [f"- {item}" for item in itens] + [""]
        return "\n".join(linhas)


class Importador:
    def __init__(self, api, baixar_imagens: bool = True, pasta_saida: Path | None = None, baixador=baixar_imagem):
        self.api = api
        self.baixar_imagens = baixar_imagens
        self.pasta_saida = pasta_saida
        self.baixador = baixador
        self.relatorio = Relatorio()
        self._clientes_por_nuvemshop: dict[int, Cliente] = {}

    def executar(self, etapas=ETAPAS) -> Relatorio:
        for etapa in ETAPAS:
            if etapa in etapas:
                logger.info("Importando %s…", etapa)
                getattr(self, etapa)()
        return self.relatorio

    # ------------------------------------------------------------------ categorias
    def categorias(self):
        dados = list(self.api.paginar("categories"))
        for item in dados:  # primeiro sem pai, para poder ligar as subcategorias depois
            nome = m.texto(item.get("name")) or f"Categoria {item['id']}"
            slug = self._slug_livre(Categoria, m.texto(item.get("handle")) or slugify(nome), item["id"])
            Categoria.objects.update_or_create(
                nuvemshop_id=item["id"],
                defaults={
                    "nome": nome[:80],
                    "slug": slug,
                    "descricao": m.html_para_texto(m.texto(item.get("description"))),
                },
            )
            self.relatorio.conta("categorias")
        for item in dados:
            if item.get("parent"):
                pai = Categoria.objects.filter(nuvemshop_id=item["parent"]).first()
                Categoria.objects.filter(nuvemshop_id=item["id"]).update(pai=pai)

    # ------------------------------------------------------------------ produtos
    def produtos(self):
        for item in self.api.paginar("products"):
            try:
                with transaction.atomic():
                    self._produto(item)
            except Exception as exc:
                logger.exception("Falha no produto %s", item.get("id"))
                self.relatorio.pendencia("Produtos não importados", f"{m.texto(item.get('name'))}: {exc}")
                self.relatorio.conta("produtos com erro")

    def _produto(self, item: dict):
        nome = m.texto(item.get("name")) or f"Produto {item['id']}"
        variantes = item.get("variants") or []
        primeira = variantes[0] if variantes else {}
        preco, comparativo = m.precos(primeira.get("price"), primeira.get("promotional_price"))
        categorias = list(Categoria.objects.filter(nuvemshop_id__in=[c["id"] for c in item.get("categories") or []]))
        nomes_categorias = {m.chave_cor(c.nome) for c in categorias}

        produto, criado = Produto.objects.update_or_create(
            nuvemshop_id=item["id"],
            defaults={
                "nome": nome[:120],
                "slug": self._slug_livre(Produto, m.texto(item.get("handle")) or slugify(nome), item["id"]),
                "descricao": m.html_para_texto(m.texto(item.get("description"))),
                "tipo": Produto.Tipo.GRAU if any("grau" in n for n in nomes_categorias) else Produto.Tipo.SOL,
                "publico": self._publico(nomes_categorias),
                "preco": preco,
                "preco_comparativo": comparativo,
                "peso_g": m.peso_gramas(primeira.get("weight")) or get_parametro("PESO_PADRAO_G", 50),
                "largura_cm": m.medida_cm(primeira.get("width")),
                "altura_cm": m.medida_cm(primeira.get("height")),
                "comprimento_cm": m.medida_cm(primeira.get("depth")),
                "ativo": bool(item.get("published")),
                "seo_titulo": m.texto(item.get("seo_title"))[:70],
                "seo_descricao": m.texto(item.get("seo_description"))[:160],
            },
        )
        produto.categorias.set(categorias)
        self.relatorio.conta("produtos criados" if criado else "produtos atualizados")
        if not produto.pronto_para_envio:
            self.relatorio.pendencia("Produtos sem peso/medidas (frete)", nome)
        if not categorias:
            self.relatorio.pendencia("Produtos sem categoria", nome)

        atributos = [m.chave_cor(m.texto(a)) for a in item.get("attributes") or []]
        indice_cor = atributos.index("cor") if "cor" in atributos else 0
        if len(atributos) > 1:
            self.relatorio.pendencia(
                "Produtos com outros atributos além da cor (só a cor foi importada)", f"{nome}: {atributos}"
            )

        variacao_por_imagem = {}
        for posicao, variante in enumerate(variantes):
            variacao = self._variacao(produto, variante, posicao, indice_cor)
            if variacao and variante.get("image_id"):
                variacao_por_imagem[variante["image_id"]] = variacao

        for imagem in item.get("images") or []:
            self._imagem(produto, imagem, variacao_por_imagem.get(imagem.get("id")))

    @staticmethod
    def _publico(nomes_categorias: set[str]) -> str:
        if "infantil" in nomes_categorias:
            return Produto.Publico.INFANTIL
        fem, masc = "feminino" in nomes_categorias, "masculino" in nomes_categorias
        if fem and not masc:
            return Produto.Publico.FEMININO
        if masc and not fem:
            return Produto.Publico.MASCULINO
        return Produto.Publico.UNISSEX

    def _variacao(self, produto: Produto, variante: dict, posicao: int, indice_cor: int):
        valores = [m.texto(v) for v in variante.get("values") or []]
        valor_cor = valores[indice_cor] if indice_cor < len(valores) else ""
        if not valor_cor:
            valor_cor = m.cor_no_nome(produto.nome) or ""
        armacao_nome, lente_nome = m.separar_cor(valor_cor)
        if not armacao_nome:
            armacao_nome = "Padrão"
            self.relatorio.pendencia("Produtos sem cor identificada (armação 'Padrão')", produto.nome)
        if lente_nome and m.chave_cor(lente_nome) in m.TIPICAS_DE_ARMACAO:
            self.relatorio.pendencia(
                "Cores 'armação/lente' que parecem invertidas", f"{produto.nome}: {armacao_nome}/{lente_nome}"
            )

        armacao = self._cor(AcabamentoArmacao, armacao_nome)
        lente = self._cor(CorLente, lente_nome) if lente_nome else None

        conflito = (
            Variacao.objects.filter(produto=produto, armacao=armacao, lente=lente)
            .exclude(nuvemshop_id=variante["id"])
            .first()
        )
        if conflito:
            self.relatorio.pendencia(
                "Variações repetidas (mesma armação e lente) não importadas", f"{produto.nome}: {valor_cor}"
            )
            return conflito

        preco_variacao, _ = m.precos(variante.get("price"), variante.get("promotional_price"))
        estoque = variante.get("stock")
        if estoque is None:
            self.relatorio.conta("variações com estoque infinito na Nuvemshop (importadas com 0)")
        variacao, criada = Variacao.objects.update_or_create(
            nuvemshop_id=variante["id"],
            defaults={
                "produto": produto,
                "armacao": armacao,
                "lente": lente,
                "sku": self._sku_livre(variante),
                "preco": preco_variacao if preco_variacao != produto.preco else None,
                "estoque": max(int(estoque or 0), 0),
                "ordem": posicao,
            },
        )
        self.relatorio.conta("variações criadas" if criada else "variações atualizadas")
        return variacao

    def _cor(self, modelo, nome: str):
        existente = modelo.objects.filter(nome__iexact=nome).first()
        if existente:
            return existente
        tom = m.hex_da_cor(nome)
        if not tom:
            self.relatorio.pendencia(
                "Cores sem tom definido (cinza provisório)", f"{modelo._meta.verbose_name}: {nome}"
            )
        if modelo is AcabamentoArmacao and "tartaruga" in m.chave_cor(nome):
            self.relatorio.pendencia("Acabamentos que pedem imagem de textura", nome)
        self.relatorio.conta(f"cores novas ({modelo._meta.verbose_name_plural})")
        return modelo.objects.create(nome=nome[:60], cor_hex=tom or m.COR_PADRAO_HEX)

    def _imagem(self, produto: Produto, imagem: dict, variacao):
        existente = ImagemProduto.objects.filter(nuvemshop_id=imagem["id"]).first()
        alt = (m.texto(imagem.get("alt")) or f"{produto.nome} - foto {imagem.get('position') or 1}")[:150]
        if existente:
            existente.variacao, existente.texto_alternativo = variacao, alt
            existente.ordem = imagem.get("position") or 0
            existente.save(update_fields=["variacao", "texto_alternativo", "ordem"])
            self.relatorio.conta("fotos já existentes")
            return
        if not self.baixar_imagens:
            self.relatorio.conta("fotos não baixadas (--sem-imagens)")
            return
        try:
            conteudo, extensao = self.baixador(imagem["src"])
        except (ImagemInvalida, OSError, ValueError) as exc:
            self.relatorio.pendencia("Fotos que não puderam ser baixadas", f"{produto.nome}: {exc}")
            self.relatorio.conta("fotos com erro")
            return
        registro = ImagemProduto(
            produto=produto,
            variacao=variacao,
            texto_alternativo=alt,
            ordem=imagem.get("position") or 0,
            nuvemshop_id=imagem["id"],
        )
        registro.imagem.save(f"nuvemshop.{extensao}", ContentFile(conteudo), save=False)
        registro.save()
        self.relatorio.conta("fotos baixadas")

    # ------------------------------------------------------------------ clientes
    def clientes(self):
        for item in self.api.paginar("customers"):
            with transaction.atomic():
                self._cliente(item)

    def _cliente(self, item: dict, contar: bool = True) -> Cliente | None:
        nid = item.get("id")
        email = (item.get("email") or "").strip().lower()
        cliente = Cliente.objects.filter(nuvemshop_id=nid).first() if nid else None
        if cliente is None and email:
            cliente = Cliente.objects.filter(email=email).first()
            if cliente and cliente.nuvemshop_id and cliente.nuvemshop_id != nid:
                # Mesma pessoa com duas contas na Nuvemshop: unifica no mesmo cliente.
                self.relatorio.conta("contas duplicadas unificadas (mesmo e-mail)")
                self._clientes_por_nuvemshop[nid] = cliente
                return cliente
        if cliente and cliente.anonimizado_em:
            # Titular pediu exclusão: nunca reimportar os dados dele.
            self.relatorio.conta("clientes anonimizados ignorados")
            self._clientes_por_nuvemshop[nid] = cliente
            return cliente

        tipo, documento = m.documento(item.get("identification") or "")
        criado = cliente is None
        cliente = cliente or Cliente()
        cliente.nuvemshop_id = cliente.nuvemshop_id or nid
        cliente.nome = (item.get("name") or email or "Cliente Nuvemshop")[:150]
        cliente.email = email
        cliente.whatsapp = m.whatsapp(item.get("phone") or "") or cliente.whatsapp
        repetido = bool(documento) and (
            Cliente.objects.filter(documento_hash=hash_busca(documento)).exclude(pk=cliente.pk).exists()
        )
        if documento and not repetido:
            # CPF/CNPJ vai cifrado: necessário para a etiqueta/declaração do envio e para nota de PJ.
            cliente.tipo, cliente.documento = tipo, documento
        elif repetido:
            self.relatorio.pendencia("Documentos repetidos em mais de um cliente (não importados)", cliente.nome)
        cliente.save()
        if nid:
            self._clientes_por_nuvemshop[nid] = cliente
        self._enderecos(cliente, item)
        if contar:
            self.relatorio.conta("clientes criados" if criado else "clientes atualizados")
            if documento:
                self.relatorio.conta(f"clientes com {'CNPJ' if tipo == Cliente.Tipo.PESSOA_JURIDICA else 'CPF'}")
            elif m.so_digitos(item.get("identification") or ""):
                self.relatorio.conta("CPF/CNPJ inválidos ignorados")

        if item.get("accepts_marketing") and not cliente.tem_consentimento(Consentimento.Finalidade.MARKETING_EMAIL):
            Consentimento.objects.create(
                cliente=cliente,
                finalidade=Consentimento.Finalidade.MARKETING_EMAIL,
                versao_politica="nuvemshop",
                origem=Consentimento.Origem.IMPORTACAO,
            )
            self.relatorio.conta("consentimentos de e-mail marketing importados")
        return cliente

    def _enderecos(self, cliente: Cliente, item: dict, padrao_id=None):
        """Endereços completos de entrega (para continuar enviando pedidos)."""
        padrao_id = padrao_id or (item.get("default_address") or {}).get("id")
        candidatos = list(item.get("addresses") or [])
        if item.get("default_address"):
            candidatos.append(item["default_address"])
        for dados in candidatos:
            self._endereco(cliente, dados, padrao=bool(padrao_id) and dados.get("id") == padrao_id)

    def _endereco(self, cliente: Cliente, dados: dict, padrao: bool = False):
        campos = m.endereco(dados)
        if not campos:
            return
        chave = {k: campos[k] for k in ("cep", "logradouro", "numero", "complemento")}
        endereco, criado = Endereco.objects.update_or_create(cliente=cliente, **chave, defaults=campos)
        if padrao and not endereco.padrao:
            cliente.enderecos.exclude(pk=endereco.pk).update(padrao=False)
            endereco.padrao = True
            endereco.save(update_fields=["padrao"])
        if criado:
            self.relatorio.conta("endereços importados")

    # ------------------------------------------------------------------ pedidos
    def pedidos(self):
        for item in self.api.paginar("orders", {"status": "any"}):
            try:
                with transaction.atomic():
                    self._pedido(item)
            except Exception as exc:
                logger.exception("Falha no pedido %s", item.get("number"))
                self.relatorio.pendencia("Pedidos não importados", f"#{item.get('number')}: {exc}")

    def _pedido(self, item: dict):
        dados_cliente = item.get("customer") or {}
        cliente = self._clientes_por_nuvemshop.get(dados_cliente.get("id"))
        if cliente is None and dados_cliente:
            cliente = Cliente.objects.filter(nuvemshop_id=dados_cliente.get("id")).first()
            if cliente is None and (dados_cliente.get("email") or "").strip():
                cliente = self._cliente(dados_cliente, contar=False)
                self.relatorio.conta("clientes criados a partir de pedidos")
        if cliente and not cliente.anonimizado_em and item.get("shipping_address"):
            self._endereco(cliente, item["shipping_address"])

        cupons = [c.get("code", "") for c in item.get("coupon") or [] if isinstance(c, dict)]
        desconto = sum(
            (m.decimal(item.get(campo)) or 0 for campo in ("discount", "discount_coupon", "discount_gateway")),
            start=m.decimal(0),
        )
        endereco = item.get("shipping_address") or {}
        pedido, criado = PedidoHistorico.objects.update_or_create(
            nuvemshop_id=item["id"],
            defaults={
                "numero": int(item.get("number") or 0),
                "cliente": cliente,
                "realizado_em": m.data_hora(item.get("created_at")),
                "pago_em": m.data_hora(item.get("paid_at")),
                "cancelado_em": m.data_hora(item.get("cancelled_at")),
                "status": (item.get("status") or "")[:20],
                "status_pagamento": (item.get("payment_status") or "")[:30],
                "status_envio": (item.get("shipping_status") or "")[:30],
                "canal": (item.get("storefront") or "")[:30],
                "forma_pagamento": (item.get("gateway_name") or item.get("gateway") or "")[:80],
                "cupom": ", ".join(cupons)[:60],
                "subtotal": m.decimal(item.get("subtotal")) or 0,
                "desconto": desconto,
                "frete": m.decimal(item.get("shipping_cost_customer")),
                "total": m.decimal(item.get("total")) or 0,
                "cidade": (endereco.get("city") or item.get("billing_city") or "")[:80],
                "uf": (endereco.get("province") or item.get("billing_province") or "")[:40],
            },
        )
        pedido.itens.all().delete()
        produtos = {
            p.nuvemshop_id: p
            for p in Produto.objects.filter(nuvemshop_id__in=[i.get("product_id") for i in item.get("products") or []])
        }
        variacoes = {
            v.nuvemshop_id: v
            for v in Variacao.objects.filter(nuvemshop_id__in=[i.get("variant_id") for i in item.get("products") or []])
        }
        for linha in item.get("products") or []:
            valores = linha.get("variant_values") or []
            ItemPedidoHistorico.objects.create(
                pedido=pedido,
                produto=produtos.get(_inteiro(linha.get("product_id"))),
                variacao=variacoes.get(_inteiro(linha.get("variant_id"))),
                nome=(m.texto(linha.get("name")) or "Item")[:200],
                variante=" / ".join(m.texto(v) for v in valores)[:120],
                sku=(linha.get("sku") or "")[:60],
                quantidade=int(linha.get("quantity") or 1),
                preco_unitario=m.decimal(linha.get("price")) or 0,
            )
        self.relatorio.conta("pedidos criados" if criado else "pedidos atualizados")

    # ------------------------------------------------------------------ cupons
    def cupons(self):
        """Ainda não há model de cupom: guarda os dados (sem dados pessoais) para importar depois."""
        cupons = list(self.api.paginar("coupons"))
        self.relatorio.conta("cupons salvos para importar depois", len(cupons))
        if self.pasta_saida is not None:
            self.pasta_saida.mkdir(parents=True, exist_ok=True)
            (self.pasta_saida / "cupons.json").write_text(
                json.dumps(cupons, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    # ------------------------------------------------------------------ utilidades
    def _slug_livre(self, modelo, slug: str, nuvemshop_id: int) -> str:
        slug = slugify(slug)[:100] or f"item-{nuvemshop_id}"
        if modelo.objects.filter(slug=slug).exclude(nuvemshop_id=nuvemshop_id).exists():
            novo = f"{slug[:85]}-{nuvemshop_id}"
            self.relatorio.pendencia("Endereços (slug) alterados por conflito — revise o SEO", f"{slug} → {novo}")
            return novo
        return slug

    def _sku_livre(self, variante: dict) -> str:
        sku = (variante.get("sku") or "").strip() or f"NS-{variante['id']}"
        if Variacao.objects.filter(sku=sku).exclude(nuvemshop_id=variante["id"]).exists():
            sku = f"{sku[:25]}-{variante['id']}"
        return sku[:40]


def _inteiro(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None
