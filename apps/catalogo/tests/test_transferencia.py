import io
import json
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from PIL import Image

from apps.catalogo.models import AcabamentoArmacao, Banner, Categoria, ImagemProduto, Produto, Variacao
from apps.catalogo.transferencia import TransferenciaInvalida, exportar, importar
from apps.clientes.models import Cliente


class TransferenciaTests(TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        configuracao = override_settings(MEDIA_ROOT=self.pasta.name)
        configuracao.enable()
        self.addCleanup(configuracao.disable)
        (Path(self.pasta.name) / "produtos").mkdir()
        Image.new("RGB", (10, 10), "white").save(Path(self.pasta.name) / "produtos" / "foto.webp", "WEBP")

        self.usuario = get_user_model().objects.create_user("dono", password="x-teste-123-Senha")
        categoria = Categoria.objects.create(nome="Feminino", slug="feminino")
        preta = AcabamentoArmacao.objects.create(nome="Preta", cor_hex="#111111")
        self.produto = Produto.objects.create(
            nome="Zaik", slug="zaik", preco=Decimal("85.90"), ativo=True, criado_por=self.usuario
        )
        self.produto.categorias.add(categoria)
        Variacao.objects.create(produto=self.produto, armacao=preta, sku="ZK-PT", estoque=2)
        ImagemProduto.objects.create(produto=self.produto, imagem="produtos/foto.webp", texto_alternativo="Zaik")
        Banner.objects.create(titulo="Mapa", imagem="banners/nao-existe.webp")

    def test_exporta_sem_dados_pessoais(self):
        Cliente.objects.create(nome="Fulana de Tal", email="fulana@exemplo.com")
        destino = exportar()
        self.assertTrue(destino.name.startswith("catalogo-") and len(destino.stem) > 30)
        with zipfile.ZipFile(destino) as zip_:
            texto = zip_.read("catalogo.json").decode()
            nomes = zip_.namelist()
        self.assertIn("media/produtos/foto.webp", nomes)
        self.assertNotIn("Fulana", texto)
        self.assertNotIn("fulana@", texto)
        self.assertNotIn("clientes.", texto)
        self.assertNotIn("auth.user", texto)
        dados = json.loads(texto)
        produto = next(o for o in dados if o["model"] == "catalogo.produto")
        self.assertIsNone(produto["fields"]["criado_por"])

    def test_ida_e_volta(self):
        destino = exportar(Path(self.pasta.name) / "catalogo.zip")
        Produto.objects.all().delete()
        (Path(self.pasta.name) / "produtos" / "foto.webp").unlink()
        resultado = importar(str(destino))
        self.assertEqual(resultado["arquivos"], 1)
        produto = Produto.objects.get(slug="zaik")
        self.assertEqual(produto.variacoes.get().sku, "ZK-PT")
        self.assertEqual(list(produto.categorias.values_list("slug", flat=True)), ["feminino"])
        self.assertTrue((Path(self.pasta.name) / "produtos" / "foto.webp").is_file())

    def _zip(self, membros: dict) -> str:
        caminho = Path(self.pasta.name) / "malicioso.zip"
        with zipfile.ZipFile(caminho, "w") as zip_:
            for nome, conteudo in membros.items():
                zip_.writestr(nome, conteudo)
        return str(caminho)

    def test_recusa_caminho_para_fora_da_pasta(self):
        for nome in ("media/../../settings.py", "/etc/passwd", "media/produtos/../x.py", "media/outra/x.webp"):
            with self.subTest(nome=nome), self.assertRaises(TransferenciaInvalida):
                importar(self._zip({"catalogo.json": "[]", nome: "x"}))

    def test_recusa_dados_que_nao_sao_do_catalogo(self):
        dados = json.dumps([{"model": "auth.user", "pk": 99, "fields": {"username": "invasor", "password": "x"}}])
        with self.assertRaises(TransferenciaInvalida):
            importar(self._zip({"catalogo.json": dados}))
        self.assertFalse(get_user_model().objects.filter(username="invasor").exists())

    def test_comandos(self):
        saida = io.StringIO()
        call_command("exportar_catalogo", stdout=saida)
        self.assertIn("/media/exportacao/catalogo-", saida.getvalue())
        with self.assertRaises(CommandError):
            call_command("importar_catalogo", "http://inseguro.exemplo.com/a.zip", stdout=io.StringIO())


class AmbienteTestesTests(TestCase):
    @override_settings(AMBIENTE="testes")
    def test_testes_nao_indexa_e_avisa(self):
        resposta = self.client.get("/")
        self.assertEqual(resposta["X-Robots-Tag"], "noindex, nofollow")
        self.assertContains(resposta, "Ambiente de testes")
        self.assertEqual(self.client.get("/robots.txt").content.decode(), "User-agent: *\nDisallow: /\n")

    def test_producao_normal(self):
        resposta = self.client.get("/")
        self.assertFalse(resposta.has_header("X-Robots-Tag"))
        self.assertNotContains(resposta, "Ambiente de testes")
