import os
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest import mock

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from apps.core import crypto
from apps.core.auditoria import diferenca, foto, registrar
from apps.core.logging import mascarar
from apps.core.middleware import UsuarioAtualMiddleware, get_usuario_atual
from apps.core.models import Parametro, RegistroAuditoria
from apps.core.parametros import get_parametro
from apps.core.validators import validar_cnpj, validar_cpf
from config.env import env_bool, env_int, env_list, env_str, load_dotenv


class EnvTests(SimpleTestCase):
    def test_leitura_tipada(self):
        with mock.patch.dict(os.environ, {"X_BOOL": "sim", "X_INT": "7", "X_LIST": "a, b,,c"}):
            self.assertTrue(env_bool("X_BOOL"))
            self.assertEqual(env_int("X_INT", 0), 7)
            self.assertEqual(env_list("X_LIST"), ["a", "b", "c"])

    def test_obrigatoria_ausente_falha(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(ImproperlyConfigured):
            env_str("NAO_EXISTE", required=True)

    def test_booleano_invalido_falha(self):
        with mock.patch.dict(os.environ, {"X_BOOL": "talvez"}), self.assertRaises(ImproperlyConfigured):
            env_bool("X_BOOL")

    def test_dotenv(self):
        conteudo = "# comentario\nX_VAZIA=\nX_VALOR=abc\nexport X_ASPAS='com espaco'\nX_EXISTENTE=novo\n"
        with tempfile.TemporaryDirectory() as pasta, mock.patch.dict(os.environ, {"X_EXISTENTE": "antigo"}):
            caminho = Path(pasta) / ".env"
            caminho.write_text(conteudo, encoding="utf-8")
            load_dotenv(caminho)
            self.assertNotIn("X_VAZIA", os.environ)  # vazio no .env não apaga padrões
            self.assertEqual(os.environ["X_VALOR"], "abc")
            self.assertEqual(os.environ["X_ASPAS"], "com espaco")
            self.assertEqual(os.environ["X_EXISTENTE"], "antigo")  # ambiente real tem prioridade


class CryptoTests(SimpleTestCase):
    def setUp(self):
        crypto._cifrador.cache_clear()

    def tearDown(self):
        crypto._cifrador.cache_clear()

    def test_ida_e_volta(self):
        token = crypto.cifrar("52998224725")
        self.assertNotIn("52998224725", token)
        self.assertEqual(crypto.decifrar(token), "52998224725")

    def test_rotacao_de_chave(self):
        antiga = Fernet.generate_key().decode()
        nova = Fernet.generate_key().decode()
        with self.settings(FIELD_ENCRYPTION_KEYS=[antiga]):
            token = crypto.cifrar("segredo")
        crypto._cifrador.cache_clear()
        with self.settings(FIELD_ENCRYPTION_KEYS=[nova, antiga]):
            self.assertEqual(crypto.decifrar(token), "segredo")

    def test_hash_normaliza(self):
        self.assertEqual(crypto.hash_busca("529.982.247-25"), crypto.hash_busca("52998224725"))
        self.assertNotEqual(crypto.hash_busca("52998224725"), "52998224725")


class ValidadoresTests(SimpleTestCase):
    def test_cpf(self):
        validar_cpf("529.982.247-25")
        for invalido in ("111.111.111-11", "529.982.247-24", "123"):
            with self.assertRaises(ValidationError):
                validar_cpf(invalido)

    def test_cnpj(self):
        validar_cnpj("11.222.333/0001-81")
        for invalido in ("11.222.333/0001-80", "00000000000000"):
            with self.assertRaises(ValidationError):
                validar_cnpj(invalido)


class LogTests(SimpleTestCase):
    def test_mascara_dados_pessoais(self):
        texto = mascarar("cliente fulano@x.com cpf 529.982.247-25 cnpj 11.222.333/0001-81")
        self.assertNotIn("fulano@x.com", texto)
        self.assertNotIn("529.982.247-25", texto)
        self.assertNotIn("11.222.333/0001-81", texto)


class ParametroTests(TestCase):
    def test_parametros_iniciais_e_tipos(self):
        self.assertEqual(get_parametro("PIX_DESCONTO_PERCENTUAL"), Decimal("5"))
        self.assertEqual(get_parametro("PARCELAS_SEM_JUROS"), 3)
        self.assertIsNone(get_parametro("INEXISTENTE"))

    def test_cache_invalida_ao_salvar(self):
        self.assertEqual(get_parametro("PIX_DESCONTO_PERCENTUAL"), Decimal("5"))
        p = Parametro.objects.get(pk="PIX_DESCONTO_PERCENTUAL")
        p.valor = "7"
        p.save()
        self.assertEqual(get_parametro("PIX_DESCONTO_PERCENTUAL"), Decimal("7"))

    def test_valor_incompativel(self):
        p = Parametro(chave="TESTE", valor="abc", tipo=Parametro.Tipo.INTEIRO, descricao="x")
        with self.assertRaises(ValidationError):
            p.full_clean()


class AuditoriaTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user("admin", password="x" * 16)

    def _com_usuario(self, func):
        request = RequestFactory().get("/")
        request.user = self.usuario
        return UsuarioAtualMiddleware(lambda r: func())(request)

    def test_preenche_criado_por(self):
        def cria():
            self.assertEqual(get_usuario_atual(), self.usuario)
            return Parametro.objects.create(chave="NOVO", valor="1", tipo="inteiro", descricao="x")

        p = self._com_usuario(cria)
        self.assertEqual(p.criado_por, self.usuario)
        self.assertEqual(p.atualizado_por, self.usuario)
        self.assertIsNone(get_usuario_atual())  # contexto limpo após a requisição

    def test_registro_imutavel(self):
        p = Parametro.objects.get(pk="PARCELAS_SEM_JUROS")
        registro = registrar(RegistroAuditoria.Acao.ALTERACAO, p, {"valor": "3"}, {"valor": "6"}, self.usuario)
        with self.assertRaises(ValidationError):
            registro.save()
        with self.assertRaises(ValidationError):
            registro.delete()

    def test_diferenca(self):
        antes, depois = diferenca({"a": 1, "b": 2}, {"a": 1, "b": 3})
        self.assertEqual((antes, depois), ({"b": 2}, {"b": 3}))

    def test_foto_ignora_campos_de_controle(self):
        p = Parametro.objects.get(pk="PARCELAS_SEM_JUROS")
        self.assertNotIn("criado_em", foto(p))


class SegurancaHttpTests(TestCase):
    def test_cabecalhos_de_seguranca(self):
        resposta = self.client.get("/")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("default-src 'self'", resposta["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", resposta["Content-Security-Policy"])
        self.assertEqual(resposta["X-Frame-Options"], "DENY")
        self.assertEqual(resposta["X-Content-Type-Options"], "nosniff")
        self.assertEqual(resposta["Referrer-Policy"], "strict-origin-when-cross-origin")

    def test_saude(self):
        resposta = self.client.get("/saude/")
        self.assertEqual(resposta.json(), {"status": "ok"})
        self.assertIn("no-cache", resposta["Cache-Control"])

    def test_security_txt(self):
        resposta = self.client.get("/.well-known/security.txt")
        self.assertContains(resposta, "Contact: mailto:")

    def test_admin_fora_do_endereco_padrao(self):
        self.assertEqual(self.client.get("/admin/").status_code, 404)

    def test_metodo_nao_permitido(self):
        self.assertEqual(self.client.post("/").status_code, 405)


@override_settings(DEBUG=False)
class SenhaTests(SimpleTestCase):
    def test_senha_curta_rejeitada(self):
        from django.contrib.auth.password_validation import validate_password

        with self.assertRaises(ValidationError):
            validate_password("curta123")
