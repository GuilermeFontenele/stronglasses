import json
from datetime import timedelta
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.clientes import lgpd
from apps.clientes.models import Cliente, Consentimento
from apps.core.models import RegistroAuditoria


class ClienteTests(TestCase):
    def cria(self, **extra):
        dados = {"nome": "Maria", "email": "Maria@Exemplo.com", "documento": "529.982.247-25"}
        dados.update(extra)
        return Cliente.objects.create(**dados)

    def test_documento_cifrado_no_banco(self):
        cliente = self.cria()
        with connection.cursor() as cursor:
            cursor.execute("SELECT documento FROM clientes_cliente WHERE id = %s", [cliente.pk])
            bruto = cursor.fetchone()[0]
        self.assertNotIn("52998224725", bruto)
        self.assertEqual(Cliente.objects.get(pk=cliente.pk).documento, "52998224725")

    def test_normaliza_email_e_gera_hash(self):
        cliente = self.cria()
        self.assertEqual(cliente.email, "maria@exemplo.com")
        self.assertEqual(len(cliente.documento_hash), 64)
        self.assertEqual(cliente.documento_mascarado, "•" * 9 + "25")

    def test_documento_unico_via_hash(self):
        self.cria()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.cria(email="outra@exemplo.com", documento="52998224725")

    def test_email_vazio_nao_conflita(self):
        Cliente.objects.create(nome="A", whatsapp="+5585999990001")
        Cliente.objects.create(nome="B", whatsapp="+5585999990002")
        self.assertEqual(Cliente.objects.filter(email="").count(), 2)

    def test_validacoes(self):
        with self.assertRaises(ValidationError):
            Cliente(nome="Sem contato").full_clean()
        with self.assertRaises(ValidationError):
            Cliente(nome="X", email="x@x.com", documento="111.111.111-11").full_clean()
        with self.assertRaises(ValidationError):
            Cliente(nome="X", whatsapp="85 99999-0000").full_clean()
        Cliente(nome="Hotel", tipo="PJ", email="h@h.com", documento="11.222.333/0001-81").full_clean()


class LgpdTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(nome="Maria", email="maria@exemplo.com", documento="52998224725")
        request = RequestFactory().post("/", HTTP_USER_AGENT="Teste/1.0", REMOTE_ADDR="203.0.113.5")
        self.consentimento = lgpd.registrar_consentimento(
            self.cliente, Consentimento.Finalidade.MARKETING_WHATSAPP, Consentimento.Origem.POPUP, request
        )

    def test_consentimento_e_revogacao(self):
        self.assertEqual(self.consentimento.ip, "203.0.113.5")
        self.assertTrue(self.cliente.tem_consentimento("marketing_whatsapp"))
        lgpd.revogar_consentimento(self.cliente, "marketing_whatsapp")
        self.assertFalse(self.cliente.tem_consentimento("marketing_whatsapp"))
        self.assertEqual(self.cliente.consentimentos.count(), 1)  # histórico preservado

    def test_exportar(self):
        dados = lgpd.exportar_dados(self.cliente)
        self.assertEqual(dados["cliente"]["documento"], "52998224725")
        self.assertEqual(len(dados["consentimentos"]), 1)
        self.assertTrue(
            RegistroAuditoria.objects.filter(acao=RegistroAuditoria.Acao.EXPORTACAO, objeto_id=str(self.cliente.pk))
        )

    def test_anonimizar(self):
        lgpd.anonimizar(self.cliente)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.email, "")
        self.assertEqual(self.cliente.documento, "")
        self.assertEqual(self.cliente.documento_hash, "")
        self.assertIsNotNone(self.cliente.anonimizado_em)
        consentimento = self.cliente.consentimentos.get()
        self.assertIsNone(consentimento.ip)
        self.assertIsNotNone(consentimento.revogado_em)

    def test_expurgar_dados_tecnicos(self):
        Consentimento.objects.filter(pk=self.consentimento.pk).update(
            registrado_em=timezone.now() - timedelta(days=200)
        )
        self.assertEqual(lgpd.expurgar_dados_tecnicos(180), 1)
        self.consentimento.refresh_from_db()
        self.assertIsNone(self.consentimento.ip)
        self.assertEqual(self.consentimento.user_agent, "")

    def test_comandos(self):
        saida = StringIO()
        call_command("lgpd_exportar", email="MARIA@exemplo.com", stdout=saida)
        self.assertEqual(json.loads(saida.getvalue())["cliente"]["nome"], "Maria")

        with self.assertRaises(CommandError):
            call_command("lgpd_anonimizar", uuid=str(self.cliente.uuid))  # sem --confirmar
        call_command("lgpd_anonimizar", uuid=str(self.cliente.uuid), confirmar=True, stdout=StringIO())
        self.cliente.refresh_from_db()
        self.assertIsNotNone(self.cliente.anonimizado_em)

        call_command("lgpd_expurgar", stdout=StringIO())
