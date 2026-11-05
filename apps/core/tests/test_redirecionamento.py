from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.catalogo.models import Produto
from apps.core.models import Redirecionamento


class RedirecionamentoTests(TestCase):
    def test_redireciona_url_inexistente(self):
        Redirecionamento.objects.create(origem="/masculino/", destino="/categorias/masculino/")
        resposta = self.client.get("/masculino/?utm_source=instagram")
        self.assertEqual(resposta.status_code, 301)
        self.assertEqual(resposta["Location"], "/categorias/masculino/?utm_source=instagram")
        self.assertEqual(Redirecionamento.objects.get().acessos, 1)

    def test_aceita_com_ou_sem_barra_final(self):
        Redirecionamento.objects.create(origem="/promo", destino="/", permanente=False)
        self.assertEqual(self.client.get("/promo/").status_code, 302)

    def test_inativo_e_paginas_existentes_nao_redirecionam(self):
        Redirecionamento.objects.create(origem="/velho/", destino="/", ativo=False)
        Redirecionamento.objects.create(origem="/", destino="/outro/")
        self.assertEqual(self.client.get("/velho/").status_code, 404)
        self.assertEqual(self.client.get("/").status_code, 200)  # só age em 404

    def test_validacao(self):
        for origem, destino in (("https://x.com/a", "/b/"), ("/a/", "http://inseguro.com"), ("/a/", "/a")):
            with self.subTest(origem=origem, destino=destino), self.assertRaises(ValidationError):
                Redirecionamento(origem=origem, destino=destino).full_clean()

    def test_troca_de_slug_cria_redirecionamento_sem_cadeia(self):
        produto = Produto.objects.create(nome="Roshi", slug="roshi-v1", preco=Decimal("94.90"))
        produto.slug = "roshi-v2"
        produto.save()
        produto.slug = "roshi"
        produto.save()
        destinos = dict(Redirecionamento.objects.values_list("origem", "destino"))
        esperado = {"/produtos/roshi-v1/": "/produtos/roshi/", "/produtos/roshi-v2/": "/produtos/roshi/"}
        self.assertEqual(destinos, esperado)
