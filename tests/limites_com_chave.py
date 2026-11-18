"""Tabela limites com resumo com chave (achado N8 da revisão de 14/11/2026).

Sobe o servidor com banco temporário (nenhum dado real) e erra a senha de um e-mail sintético. Confere que a tabela
limites não guarda o SHA-256 simples do e-mail nem do endereço de conexão, e sim o HMAC-SHA256 com a chave guardada
fora do banco (arquivo próprio, permissão 600); que a cota de 10 tentativas por conta continua valendo; e que, com
CHAVE_LIMITES apontando para um arquivo, o servidor usa essa chave e não cria outra.
Uso: python3 tests/limites_com_chave.py
Dominique-Oliveira-Claude🤖🧡, 17/11/2026.
"""
import hashlib
import hmac
import json
import os
import secrets
import socket
import sqlite3
import stat
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from questoes_sinteticas import QUESTOES as QUESTOES_TESTE

RAIZ = Path(__file__).resolve().parents[1]
EMAIL = 'limite.sintetico@example.com'


class Servidor:
    def __init__(self, pasta, extra=None):
        catalogo = pasta / 'catalogo.json'
        catalogo.write_text(json.dumps({'formato': 1, 'questoes': QUESTOES_TESTE, 'anuladas': 0, 'revisar': 0, 'versao': 'teste'}))
        self.dados = pasta / 'dados'
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            porta = s.getsockname()[1]
        self.origem = f'http://127.0.0.1:{porta}'
        self.saida = open(pasta / 'registro.txt', 'w+')
        self.processo = subprocess.Popen(['python3', str(RAIZ / 'app/servidor.py')], stdout=self.saida, stderr=subprocess.STDOUT,
            env={**os.environ, 'DADOS': str(self.dados), 'CATALOGO': str(catalogo), 'PORTA': str(porta), 'ESCUTA': '127.0.0.1',
                 'ORIGEM': self.origem, 'PERFIL_TESTE': '0', 'AMBIENTES_INDIVIDUAIS': '0', **(extra or {})})
        for _ in range(100):
            try:
                with urllib.request.urlopen(self.origem + '/api/saude', timeout=1):
                    return
            except OSError:
                time.sleep(.05)
        self.fechar()
        raise RuntimeError('Servidor não iniciou')

    def entrar(self, senha):
        req = urllib.request.Request(self.origem + '/api/entrar', data=json.dumps({'email': EMAIL, 'senha': senha}).encode(),
                                     headers={'Origin': self.origem, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status
        except urllib.error.HTTPError as e:
            e.close()
            return e.code

    def chaves(self):
        with sqlite3.connect(self.dados / 'estudos.sqlite3') as con:
            return [linha[0] for linha in con.execute('SELECT chave FROM limites')]

    def fechar(self):
        self.processo.terminate(); self.processo.wait(); self.saida.close()


class LimitesComChave(unittest.TestCase):
    def test_resumo_com_chave_fora_do_banco_e_cota_mantida(self):
        with tempfile.TemporaryDirectory() as nome:
            servidor = Servidor(Path(nome))
            try:
                respostas = [servidor.entrar(f'senha errada numero {n:02d}') for n in range(11)]
                chaves = servidor.chaves()
            finally:
                servidor.fechar()
            # Cota de 10 por conta e origem: 10 recusas comuns, a 11ª bloqueada.
            self.assertEqual(respostas[:10], [401] * 10, respostas)
            self.assertEqual(respostas[10], 429, respostas)
            simples = {hashlib.sha256(t.encode()).hexdigest() for t in (EMAIL, '127.0.0.1')}
            texto = ' '.join(chaves)
            for valor in simples:
                self.assertNotIn(valor, texto, 'SHA-256 sem chave na tabela limites')
            arquivo = servidor.dados / 'chave-limites'
            self.assertEqual(stat.S_IMODE(arquivo.stat().st_mode), 0o600, 'chave com permissão 600')
            chave = bytes.fromhex(arquivo.read_text().strip())
            com_chave = hmac.new(chave, EMAIL.encode(), hashlib.sha256).hexdigest()
            ip = hmac.new(chave, b'127.0.0.1', hashlib.sha256).hexdigest()
            self.assertIn(f'entrada_conta_origem:{com_chave}:{ip}', chaves)
            self.assertIn(f'entrada_origem:{ip}', chaves)
            bruto = (servidor.dados / 'estudos.sqlite3').read_bytes()
            self.assertNotIn(chave.hex().encode(), bruto, 'chave gravada no banco')

            # Chave indicada por CHAVE_LIMITES (como no compose): usada e nenhuma outra criada ao lado do banco.
            outra = Path(nome) / 'segredo' / 'chave'
            outra.parent.mkdir()
            outra.write_text(secrets.token_hex(32)); outra.chmod(0o600)
            pasta = Path(nome) / 'segunda'; pasta.mkdir()
            servidor = Servidor(pasta, {'CHAVE_LIMITES': str(outra)})
            try:
                self.assertEqual(servidor.entrar('outra senha errada aqui'), 401)
                chaves = servidor.chaves()
            finally:
                servidor.fechar()
            esperado = hmac.new(bytes.fromhex(outra.read_text()), EMAIL.encode(), hashlib.sha256).hexdigest()
            self.assertTrue(any(esperado in c for c in chaves), chaves)
            self.assertFalse((servidor.dados / 'chave-limites').exists(), 'criou chave própria mesmo com CHAVE_LIMITES')


if __name__ == '__main__':
    unittest.main(verbosity=1)
