"""Densidades pelo servidor de verdade (HTTP, banco temporário): ciclo completo, resposta repetida, reinício,
catálogo insuficiente e separação entre contas. Requisitos da nota "Alterações do PU - densidades e perfil"
(09/11/2026), item 4 de "Execução e conferência". Dominique-Oliveira-Claude🤖🧡, 18/11/2026.
Nunca toca no banco real: cada teste sobe o servidor com uma pasta temporária própria."""
import http.cookiejar
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from questoes_sinteticas import QUESTOES  # 4 questões, uma por área: 1 Matemática, 2 Linguagens, 3 Natureza, 4 Humanas

RAIZ = Path(__file__).resolve().parents[1]
CERTA = {q['id']: q['correta'] for q in QUESTOES}
ERRADA = {q['id']: (q['correta'] + 1) % len(q['alternativas']) for q in QUESTOES}
SENHA = 'Senha longa de teste 123!'


class Densidades(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.catalogo = Path(self.pasta.name) / 'catalogo.json'
        self.gravar_catalogo(QUESTOES)
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0)); self.porta = s.getsockname()[1]
        self.origem = f'http://127.0.0.1:{self.porta}'
        self.processo = None
        self.subir()

    def tearDown(self):
        self.descer(); self.pasta.cleanup()

    def gravar_catalogo(self, questoes):
        self.catalogo.write_text(json.dumps({'formato': 1, 'questoes': questoes, 'anuladas': 0, 'revisar': 0, 'versao': 'densidades'}))

    def subir(self):
        self.processo = subprocess.Popen(['python3', str(RAIZ / 'app/servidor.py')], stdout=subprocess.DEVNULL,
                                         env={**os.environ, 'DADOS': self.pasta.name, 'CATALOGO': str(self.catalogo), 'PORTA': str(self.porta), 'ORIGEM': self.origem, 'PERFIL_TESTE': '0'})
        for _ in range(200):
            try:
                urllib.request.urlopen(self.origem + '/api/saude', timeout=1).close(); return
            except OSError:
                time.sleep(.05)
        raise RuntimeError('Servidor não iniciou')

    def descer(self):
        if self.processo:
            self.processo.terminate(); self.processo.wait(); self.processo = None

    def reiniciar(self):
        self.descer(); self.subir()

    def cliente(self):
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def pedido(self, cliente, caminho, dados=None):
        req = urllib.request.Request(self.origem + caminho, data=None if dados is None else json.dumps(dados).encode(),
                                     headers={'Origin': self.origem, 'Content-Type': 'application/json'})
        try:
            resposta = cliente.open(req)
        except urllib.error.HTTPError as e:
            resposta = e
        with resposta:
            return resposta.status, json.loads(resposta.read())

    def cadastrar(self, nome):
        c = self.cliente()
        status, dados = self.pedido(c, '/api/cadastro', {'nome': nome, 'email': nome.lower() + '@example.com', 'senha': SENHA})
        self.assertEqual(status, 200, dados)
        return c

    def responder(self, c, questao, alternativa, envio=None):
        corpo = {'alternativa': alternativa}
        if envio: corpo['envio'] = envio
        status, r = self.pedido(c, f'/api/questoes/{questao}', corpo)
        self.assertEqual(status, 200, r)
        return r

    def densidade(self, c):
        status, painel = self.pedido(c, '/api/painel')
        self.assertEqual(status, 200, painel)
        return painel['densidade']

    def feitas_por_materia(self, d):
        return {m['materia']: (m['feitas'], m['total']) for m in d['materias']}

    def test_1_ciclo_completo_com_erro_e_contas_separadas(self):
        a, b = self.cadastrar('CicloA'), self.cadastrar('CicloB')
        d = self.densidade(a)
        self.assertEqual((d['concluidas'], d['feitas'], d['total']), (0, 0, 4))
        self.assertEqual(sorted(d['pendentes']), [1, 2, 3, 4])
        # Erro também conta como questão feita; o aviso de conclusão só vem na última.
        for n, (questao, alternativa) in enumerate([(2, ERRADA[2]), (1, CERTA[1]), (4, ERRADA[4])], 1):
            r = self.responder(a, questao, alternativa)
            self.assertFalse(r['densidadeConcluida'])
            self.assertEqual(r['acompanhamento']['densidade']['feitas'], n)
        self.assertEqual(self.feitas_por_materia(self.densidade(a)),
                         {'Matemática': (1, 1), 'Linguagens': (1, 1), 'Ciências da Natureza': (0, 1), 'Ciências Humanas': (1, 1)})
        r = self.responder(a, 3, ERRADA[3])
        self.assertTrue(r['densidadeConcluida'])
        d = r['acompanhamento']['densidade']
        self.assertEqual((d['concluidas'], d['feitas'], d['total']), (1, 0, 4))
        self.assertEqual(sorted(d['pendentes']), [1, 2, 3, 4], 'a volta seguinte começa com todas')
        self.assertEqual(self.densidade(a)['concluidas'], 1)
        # A outra conta não andou.
        d = self.densidade(b)
        self.assertEqual((d['concluidas'], d['feitas']), (0, 0))
        self.assertEqual(self.pedido(b, '/api/painel')[1]['progresso'], {'total': 0, 'acertos': 0})
        # Responder de novo uma questão da volta anterior conta na volta nova, uma vez.
        self.assertEqual(self.responder(a, 2, CERTA[2])['acompanhamento']['densidade']['feitas'], 1)

    def test_2_resposta_repetida_nao_conta_duas_vezes(self):
        a = self.cadastrar('Repetida')
        envio = 'repetida-envio-0000000001'
        primeira = self.responder(a, 1, ERRADA[1], envio)
        # Mesmo envio de novo (a volta se perdeu e o aparelho reenviou): mesmo resultado, nada contado de novo.
        repetida = self.responder(a, 1, ERRADA[1], envio)
        self.assertEqual(repetida['progresso'], {'total': 1, 'acertos': 0})
        self.assertEqual(repetida['acompanhamento']['densidade']['feitas'], 1)
        self.assertEqual(repetida['acerto'], primeira['acerto'])
        # O mesmo identificador com outra alternativa é recusado e não grava.
        self.assertEqual(self.pedido(a, '/api/questoes/1', {'alternativa': CERTA[1], 'envio': envio})[0], 409)
        # Envios simultâneos com o mesmo identificador: uma resposta só no banco.
        envio2 = 'repetida-envio-0000000002'; resultados = []
        def enviar():
            resultados.append(self.pedido(a, '/api/questoes/2', {'alternativa': CERTA[2], 'envio': envio2})[0])
        fios = [threading.Thread(target=enviar) for _ in range(5)]
        for f in fios: f.start()
        for f in fios: f.join()
        self.assertEqual(resultados, [200] * 5)
        status, painel = self.pedido(a, '/api/painel')
        self.assertEqual(painel['progresso'], {'total': 2, 'acertos': 1})
        self.assertEqual(painel['densidade']['feitas'], 2)
        # Fazer a questão de novo depois de ver a correção é outra tentativa: entra no histórico, mas a densidade não anda.
        r = self.responder(a, 1, CERTA[1], 'repetida-envio-0000000003')
        self.assertEqual(r['progresso'], {'total': 3, 'acertos': 2})
        self.assertEqual(r['acompanhamento']['densidade']['feitas'], 2)
        self.assertFalse(r['densidadeConcluida'])

    def test_3_reinicio_e_saida_preservam_a_volta(self):
        a = self.cadastrar('Reinicio')
        for questao in [1, 2, 3, 4]:
            self.responder(a, questao, CERTA[questao])
        self.responder(a, 2, ERRADA[2], 'reinicio-envio-0000000001')
        antes = self.densidade(a)
        self.assertEqual((antes['concluidas'], antes['feitas']), (1, 1))
        self.reiniciar()
        # A sessão continua valendo depois do reinício, e a volta está igual.
        depois = self.densidade(a)
        for campo in ['concluidas', 'feitas', 'total', 'pendentes', 'materias']:
            self.assertEqual(depois[campo], antes[campo], campo)
        # O envio já gravado antes do reinício não conta de novo.
        r = self.responder(a, 2, ERRADA[2], 'reinicio-envio-0000000001')
        self.assertEqual(r['progresso'], {'total': 5, 'acertos': 4})
        # Sair e entrar de novo (outro aparelho, sem cookie) mantém tudo.
        self.assertEqual(self.pedido(a, '/api/sair', {})[0], 200)
        novo = self.cliente()
        self.assertEqual(self.pedido(novo, '/api/entrar', {'email': 'reinicio@example.com', 'senha': SENHA})[0], 200)
        d = self.densidade(novo)
        self.assertEqual((d['concluidas'], d['feitas']), (1, 1))

    def test_4_catalogo_insuficiente_mostra_pendencia_sem_declarar_volta_completa(self):
        a = self.cadastrar('Insuficiente')
        self.responder(a, 1, CERTA[1])
        # A questão 4 sai do catálogo no meio da volta (sincronização com o cofre, por exemplo).
        self.gravar_catalogo([q for q in QUESTOES if q['id'] != 4]); self.reiniciar()
        d = self.densidade(a)
        self.assertEqual((d['feitas'], d['total'], d['removidas'], d['bloqueada']), (1, 4, 1, False))
        self.assertNotIn(4, d['pendentes'])
        self.assertEqual(self.feitas_por_materia(d)['Questão removida do catálogo'], (0, 1))
        self.assertEqual(self.pedido(a, '/api/questoes/4', {'alternativa': 0})[0], 404)
        for questao in [2, 3]:
            r = self.responder(a, questao, CERTA[questao])
            self.assertFalse(r['densidadeConcluida'], 'sem a questão 4 a volta não fecha')
        d = self.densidade(a)
        self.assertEqual((d['concluidas'], d['feitas'], d['bloqueada'], d['proxima'], d['pendentes']), (0, 3, True, None, []))
        # Com a questão de volta, ela fecha a volta.
        self.gravar_catalogo(QUESTOES); self.reiniciar()
        self.assertFalse(self.densidade(a)['bloqueada'])
        self.assertTrue(self.responder(a, 4, ERRADA[4])['densidadeConcluida'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
