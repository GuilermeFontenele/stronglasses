import io
import urllib.error
from decimal import Decimal
from unittest import mock

from django.test import SimpleTestCase
from PIL import Image

from apps.nuvemshop import api as api_mod
from apps.nuvemshop import mapeamento as m
from apps.nuvemshop.imagens import ImagemInvalida, baixar_imagem, validar_imagem


def png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "#111111").save(buffer, "PNG")
    return buffer.getvalue()


class MapeamentoTests(SimpleTestCase):
    def test_separar_cor(self):
        self.assertEqual(m.separar_cor("Preto/Amarelo Escuro"), ("Preto", "Amarelo Escuro"))
        self.assertEqual(m.separar_cor("verde água/tartaruga"), ("Verde Água", "Tartaruga"))
        self.assertEqual(m.separar_cor("Tartaruga"), ("Tartaruga", None))
        self.assertEqual(m.separar_cor(""), ("", None))

    def test_cor_no_nome(self):
        self.assertEqual(m.cor_no_nome("Óculos de Sol Califórnia Laranja"), "Laranja")
        self.assertEqual(m.cor_no_nome("Óculos de Sol X Tartaruga Claro"), "Tartaruga Claro")
        self.assertIsNone(m.cor_no_nome("Óculos de Sol Califórnia Transpararente"))

    def test_precos(self):
        self.assertEqual(m.precos("159.90", "94.90"), (Decimal("94.90"), Decimal("159.90")))
        # Promoção maior que o preço cheio (cadastro inconsistente) é ignorada.
        self.assertEqual(m.precos("129.90", "149.90"), (Decimal("129.90"), None))
        self.assertEqual(m.precos("100", None), (Decimal("100.00"), None))

    def test_contatos(self):
        self.assertEqual(m.whatsapp("85996539142"), "+5585996539142")
        self.assertEqual(m.whatsapp("+55 (85) 99653-9142"), "+5585996539142")
        self.assertEqual(m.whatsapp("123"), "")
        self.assertEqual(m.cnpj("11.222.333/0001-81"), "11222333000181")
        self.assertEqual(m.cnpj("529.982.247-25"), "")  # CPF não é importado

    def test_html_para_texto_remove_scripts(self):
        resultado = m.html_para_texto("<p>Olá&nbsp;mundo</p><ul><li>UV400</li></ul><script>alert(1)</script>")
        self.assertIn("Olá mundo", resultado)
        self.assertIn("• UV400", resultado)
        self.assertNotIn("alert", resultado)
        self.assertNotIn("<", resultado)

    def test_textos_e_medidas(self):
        self.assertEqual(m.texto({"pt": "A", "es": "B"}), "A")
        self.assertEqual(m.texto([{"pt": ""}, {"pt": "X"}]), "X")
        self.assertEqual(m.peso_gramas("0.180"), 180)
        self.assertEqual(m.medida_cm("16"), Decimal("16.0"))
        self.assertEqual(m.hex_da_cor("Verde Água"), "#7FC8B8")
        self.assertIsNotNone(m.data_hora("2025-08-29T05:33:53+0000").tzinfo)


class ImagemTests(SimpleTestCase):
    def test_valida_conteudo(self):
        self.assertEqual(validar_imagem(png()), "png")
        with self.assertRaises(ImagemInvalida):
            validar_imagem(b"<html>nao sou imagem</html>")

    def test_recusa_http(self):
        with self.assertRaises(ImagemInvalida):
            baixar_imagem("http://exemplo.com/a.jpg")


class _Resposta:
    def __init__(self, dados):
        self._dados = dados
        self.headers = {}

    def read(self):
        import json

        return json.dumps(self._dados).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ApiTests(SimpleTestCase):
    def setUp(self):
        self.api = api_mod.NuvemshopAPI("123", "token", "teste", "https://api.exemplo", pausa=0)

    def test_cabecalhos(self):
        self.assertEqual(self.api.cabecalhos["Authorization"], "Bearer token")
        self.assertEqual(self.api.base, "https://api.exemplo/123")

    @mock.patch.object(api_mod, "POR_PAGINA", 2)
    def test_paginacao_ate_pagina_incompleta(self):
        paginas = [[{"id": 1}, {"id": 2}], [{"id": 3}]]
        with mock.patch.object(self.api, "_abrir", side_effect=[_Resposta(p) for p in paginas]):
            self.assertEqual([i["id"] for i in self.api.paginar("products")], [1, 2, 3])

    @mock.patch.object(api_mod, "POR_PAGINA", 2)
    def test_paginacao_para_no_404(self):
        erro = urllib.error.HTTPError("u", 404, "Last page", {}, None)
        with mock.patch.object(self.api, "_abrir", side_effect=[_Resposta([{"id": 1}, {"id": 2}]), erro]):
            self.assertEqual(len(list(self.api.paginar("products"))), 2)

    @mock.patch("apps.nuvemshop.api.time.sleep")
    def test_espera_quando_limite_estoura(self, dormir):
        erro = urllib.error.HTTPError("u", 429, "Too Many", {"x-rate-limit-reset": "1500"}, None)
        with mock.patch.object(self.api, "_abrir", side_effect=[erro, _Resposta([{"id": 1}])]):
            dados, _ = self.api.get("products")
        self.assertEqual(dados, [{"id": 1}])
        dormir.assert_called_once_with(1.5)

    def test_token_invalido(self):
        erro = urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)
        with mock.patch.object(self.api, "_abrir", side_effect=erro), self.assertRaises(api_mod.ErroNuvemshop):
            self.api.get("products")

    def test_exige_credenciais(self):
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured):
            api_mod.NuvemshopAPI("", "", "x", "https://api.exemplo")
