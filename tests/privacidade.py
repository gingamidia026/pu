"""A tela Dados e segurança contra o que o servidor faz de verdade.

Dominique-Oliveira-Claude🤖🧡, 14/11/2026, a pedido de Dominique Oliveira (revisão de segurança).
Sobe o servidor com banco temporário e contas sintéticas; nenhum dado real é lido.
Se uma regra do servidor mudar (prazo da sessão, guarda da senha, exclusão de conta),
este teste falha até a tela #privacidade ser atualizada junto."""
import hashlib
import http.cookiejar
import json
import os
import re
import socket
import sqlite3
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from questoes_sinteticas import QUESTOES as QUESTOES_TESTE

RAIZ = Path(__file__).resolve().parents[1]
SENHA = 'Senha sintetica do teste 4821!'


def texto_da_tela():
    fonte = (RAIZ / 'app/public/app.js').read_text(encoding='utf-8')
    inicio, fim = fonte.index('function verPrivacidade'), fonte.index('function verNota')
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', fonte[inicio:fim]))


class Privacidade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.TemporaryDirectory()
        catalogo = Path(cls.pasta.name) / 'catalogo.json'
        catalogo.write_text(json.dumps({'formato': 1, 'questoes': QUESTOES_TESTE, 'anuladas': 0, 'revisar': 0, 'versao': 'teste'}))
        cls.dados = Path(cls.pasta.name) / 'dados'
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            porta = s.getsockname()[1]
        cls.origem = f'http://127.0.0.1:{porta}'
        cls.saida = open(Path(cls.pasta.name) / 'registro.txt', 'w+')
        cls.processo = subprocess.Popen(['python3', str(RAIZ / 'app/servidor.py')], stdout=cls.saida, stderr=subprocess.STDOUT,
            env={**os.environ, 'DADOS': str(cls.dados), 'CATALOGO': str(catalogo), 'PORTA': str(porta), 'ESCUTA': '127.0.0.1',
                 'ORIGEM': cls.origem, 'PERFIL_TESTE': '0', 'AMBIENTES_INDIVIDUAIS': '0',
                 'LIMITE_ENTRADAS_ORIGEM': '1200'})  # o mesmo teto do compose.publico.yaml
        for _ in range(100):
            try:
                with urllib.request.urlopen(cls.origem + '/api/saude', timeout=1):
                    break
            except OSError:
                time.sleep(.05)
        else:
            raise RuntimeError('Servidor não iniciou')
        cls.tela = texto_da_tela()

    @classmethod
    def tearDownClass(cls):
        cls.processo.terminate(); cls.processo.wait(); cls.saida.close(); cls.pasta.cleanup()

    def pedido(self, cliente, caminho, dados=None):
        req = urllib.request.Request(self.origem + caminho, data=None if dados is None else json.dumps(dados).encode(),
                                     headers={'Origin': self.origem, 'Content-Type': 'application/json'})
        try:
            resposta = cliente.open(req)
        except urllib.error.HTTPError as e:
            resposta = e
        with resposta:
            return resposta.status, json.loads(resposta.read()), resposta.headers

    def nova_conta(self, nome):
        cliente = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        status, dados, cabecalhos = self.pedido(cliente, '/api/cadastro', {'nome': nome, 'email': nome.lower() + '@example.com', 'senha': SENHA})
        self.assertEqual(status, 200, dados)
        return cliente, dados, cabecalhos

    def banco(self):
        return sqlite3.connect(self.dados / 'estudos.sqlite3')

    def test_senha_so_como_resumo_scrypt_com_sal_proprio(self):
        self.nova_conta('Ana'); self.nova_conta('Bia')
        with self.banco() as con:
            linhas = con.execute("SELECT sal, senha FROM contas WHERE email IN ('ana@example.com','bia@example.com')").fetchall()
        self.assertEqual(len(linhas), 2)
        for sal, resumo in linhas:
            self.assertRegex(resumo, r'^scrypt\$32768\$8\$3\$[0-9a-f]{128}$')
            self.assertRegex(sal, r'^[0-9a-f]{32}$')
        self.assertNotEqual(linhas[0][0], linhas[1][0], 'cada conta tem sal próprio')
        bruto = b''.join(p.read_bytes() for p in self.dados.glob('estudos.sqlite3*'))
        self.assertNotIn(SENHA.encode(), bruto, 'senha escrita no banco')
        self.assertIn('scrypt', self.tela); self.assertIn('sal próprio', self.tela)
        self.assertIn('12 caracteres', self.tela)
        self.assertNotIn('ninguém consegue ler', self.tela)

    def test_sessao_de_30_dias_guardada_como_resumo_e_saida_encerra_no_servidor(self):
        cliente, _, cabecalhos = self.nova_conta('Caio')
        cookie = cabecalhos['Set-Cookie']
        self.assertIn('Max-Age=2592000', cookie); self.assertIn('HttpOnly', cookie)
        token = re.search(r'sessao=([^;]+)', cookie)[1]
        with self.banco() as con:
            expira = con.execute('SELECT expira FROM sessoes WHERE token=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
            self.assertIsNotNone(expira, 'sessão guardada só como resumo SHA-256')
            self.assertIsNone(con.execute('SELECT 1 FROM sessoes WHERE token=?', (token,)).fetchone())
        self.assertAlmostEqual((expira[0] - time.time()) / 86400, 30, delta=0.01)
        fonte = (RAIZ / 'app/public/app.js').read_text(encoding='utf-8')
        self.assertIn('30 * 86400000', fonte, 'a sessão no aparelho vence junto com a do servidor')
        self.assertIn('30 dias', self.tela)
        self.assertEqual(self.pedido(cliente, '/api/sair', {})[0], 200)
        self.assertEqual(self.pedido(cliente, '/api/painel')[0], 401)
        with self.banco() as con:
            self.assertIsNone(con.execute('SELECT 1 FROM sessoes WHERE token=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone())

    def test_painel_sem_gabarito_sem_email_e_sem_dados_de_outras_contas(self):
        _, dados, _ = self.nova_conta('Duda')
        painel = dados['painel']
        self.assertEqual(set(painel['conta']), {'id', 'nome'})
        texto = json.dumps(painel, ensure_ascii=False)
        for proibido in ['"correta"', '"explicacao"', '"sal"', '"senha"', '@example.com', 'scrypt$']:
            self.assertNotIn(proibido, texto)

    def test_registros_sem_nome_email_senha_sessao_ou_endereco(self):
        cliente, _, cabecalhos = self.nova_conta('Edu')
        self.pedido(cliente, '/api/entrar', {'email': 'edu@example.com', 'senha': 'senha errada de proposito'})
        self.pedido(cliente, '/api/painel')
        time.sleep(.2)
        self.saida.seek(0)
        linhas = [l for l in self.saida.read().splitlines() if l.strip()]
        self.assertTrue(linhas, 'o servidor registrou os eventos')
        token = re.search(r'sessao=([^;]+)', cabecalhos['Set-Cookie'])[1]
        for linha in linhas:
            self.assertEqual(set(json.loads(linha)), {'tempo', 'evento', 'status'}, linha)
            for proibido in ['Edu', 'example.com', SENHA, 'senha errada', token, '127.0.0.1']:
                self.assertNotIn(proibido, linha)
        self.assertIn('sem nome, e-mail, senha, sessão ou endereço', self.tela)

    def test_erros_de_terceiro_nao_travam_o_navegador_ja_autorizado(self):
        # Pela fila pública todo pedido chega do mesmo endereço (o conector), como aqui.
        cliente, dados, _ = self.nova_conta('Fabi')
        aparelho = dados['dispositivo']
        estranho = urllib.request.build_opener()
        tentativas = [self.pedido(estranho, '/api/entrar', {'email': 'fabi@example.com', 'senha': 'chute errado %02d!!' % i})[0] for i in range(12)]
        self.assertIn(429, tentativas, 'quem não tem o navegador autorizado continua limitado')
        self.assertEqual(self.pedido(estranho, '/api/entrar', {'email': 'fabi@example.com', 'senha': SENHA})[0], 429)
        self.assertEqual(self.pedido(estranho, '/api/entrar', {'email': 'fabi@example.com', 'senha': SENHA, 'dispositivo': 'x' * 40})[0], 429,
                         'identificador inventado não abre cota nova')
        self.assertEqual(self.pedido(cliente, '/api/entrar', {'email': 'fabi@example.com', 'senha': SENHA, 'dispositivo': aparelho})[0], 200,
                         'a dona entra pelo navegador já autorizado')
        erradas = [self.pedido(estranho, '/api/entrar', {'email': 'fabi@example.com', 'senha': 'outra errada %02d!' % i, 'dispositivo': aparelho})[0] for i in range(11)]
        self.assertEqual(erradas[-1], 429, 'a cota do navegador autorizado também tem limite')

    def test_tela_fala_do_intermediario_e_do_que_ainda_falta(self):
        # O caminho público passa por um intermediário de terceiros (conexao-publica/worker): a tela precisa dizer.
        for trecho in ['serviço de terceiros', 'a senha também', 'senha que você não usa em nenhum outro lugar',
                       'Pedido que ninguém buscou vence em 35 segundos', 'a cada hora']:
            self.assertIn(trecho, self.tela)
        worker = (RAIZ / 'conexao-publica/worker/index.js').read_text(encoding='utf-8')
        self.assertIn('tempo+35', worker.replace(' ', ''))
        # Enquanto o servidor não tiver exclusão de conta nem troca de senha, a tela diz que não existem.
        servidor = (RAIZ / 'app/servidor.py').read_text(encoding='utf-8')
        rotas = set(re.findall(r"'(/api/[a-z/]+)'", servidor))
        if not any(re.search(r'exclu|apagar|senha', r) for r in rotas):
            self.assertIn('Ainda não há botão para apagar a conta, trocar a senha ou recuperar a senha esquecida', self.tela)
        self.assertIn('pelo menos cinco estudantes', self.tela)
        self.assertIn("len(v)>=5", (RAIZ / 'app/acompanhamento.py').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
