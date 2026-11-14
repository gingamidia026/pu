"""Provas ativas por conta e catálogo grande, por HTTP real, com banco e catálogo temporários.

Cobre: todas ativas por padrão (inclusive a conta de teste), gravação pela rota POST /api/dispositivos,
recorte do índice, da densidade, da revisão, do perfil e da questão inicial, isolamento entre contas,
volta completa só com as provas ativas, prova de quatro alternativas, e o painel de um catálogo de
2.480 questões (cinco edições de cada prova) cabendo em 100 KB. Dominique-Oliveira-Claude🤖🧡, 14/11/2026.
"""
import http.cookiejar
import json
import os
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MATERIAS = [('Português', 'Linguagens'), ('Matemática', 'Matemática'), ('Biologia', 'Ciências da Natureza'), ('História', 'Ciências Humanas')]


def questao(i, prova, ano, letras=5, materia=0):
    m, area = MATERIAS[materia % 4]
    return {'id': i, 'chave': f'{prova}:{ano}:1:1:{i}', 'prova': prova, 'edicao': f'{prova} {ano}', 'area': area,
            'titulo': f'{prova} {ano} · Questão {i}', 'ano': ano, 'dia': 1, 'numero': i, 'caderno': 1,
            'materia': m, 'topico': f'Tópico {materia % 3}', 'assunto': 'Assunto', 'conteudo': 'Conteúdo', 'revisar': False,
            'oficial': True, 'enunciado': f'Enunciado sintético {i}. ' + 'Texto de apoio. ' * 20,
            'alternativas': [f'Alternativa {c}' for c in 'ABCDE'[:letras]], 'correta': 1,
            'explicacao': 'Gabarito sintético.', 'imagens': [], 'textoParcial': False, 'textoComum': '', 'grupo': '',
            'extrator': 2, 'fonte': 'https://www.fuvest.br/exemplo.pdf', 'fonteNome': 'Teste'}


class Servidor:
    def __init__(self, questoes, perfil_teste=False):
        self.pasta = tempfile.TemporaryDirectory()
        catalogo = Path(self.pasta.name) / 'atual.json'
        catalogo.write_text(json.dumps({'formato': 1, 'questoes': questoes, 'anuladas': 0, 'revisar': 0, 'versao': 'teste'}))
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0)); porta = s.getsockname()[1]
        self.origem = f'http://127.0.0.1:{porta}'
        self.processo = subprocess.Popen(['python3', str(RAIZ / 'app/servidor.py')], stdout=subprocess.DEVNULL,
                                         env={**os.environ, 'DADOS': self.pasta.name + '/dados', 'CATALOGO': str(catalogo), 'PORTA': str(porta),
                                              'ESCUTA': '127.0.0.1', 'ORIGEM': self.origem, 'PERFIL_TESTE': '1' if perfil_teste else '0',
                                              'AMBIENTES_INDIVIDUAIS': '0'})
        for _ in range(200):
            try:
                urllib.request.urlopen(self.origem + '/api/saude', timeout=1).close(); break
            except OSError:
                time.sleep(.05)
        else:
            raise RuntimeError('Servidor não iniciou')

    def fechar(self):
        self.processo.terminate(); self.processo.wait(); self.pasta.cleanup()

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
            bruto = resposta.read()
            return resposta.status, json.loads(bruto), len(bruto)

    def cadastrar(self, cliente, nome):
        status, dados, _ = self.pedido(cliente, '/api/cadastro', {'nome': nome, 'email': nome.lower() + '@example.com', 'senha': 'Senha longa de teste 123!'})
        assert status == 200, dados
        return dados['painel']


class ProvasAtivas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qs = [questao(i, 'enem', 2025, materia=i) for i in range(1, 5)]
        qs += [questao(i, 'fuvest', 2026, materia=i) for i in range(5, 8)]
        qs += [questao(i, 'unicamp', 2027, letras=4, materia=i) for i in range(8, 10)]
        cls.s = Servidor(qs)

    @classmethod
    def tearDownClass(cls):
        cls.s.fechar()

    def ids_do_indice(self, painel):
        return sorted(i for m in painel['indice']['materias'] for t in m['topicos'] for i in t['ids'])

    def test_padrao_todas_e_escolha_recorta_tudo(self):
        a, b = self.s.cliente(), self.s.cliente()
        painel = self.s.cadastrar(a, 'Ativas')
        self.s.cadastrar(b, 'Outra')
        self.assertEqual(painel['provas']['ativas'], ['enem', 'fuvest', 'unicamp'])
        self.assertEqual([p['id'] for p in painel['provas']['disponiveis']], ['enem', 'fuvest', 'unicamp'])
        self.assertEqual(self.ids_do_indice(painel), list(range(1, 10)))
        self.assertEqual(sorted(painel['densidade']['pendentes']), list(range(1, 10)))
        # Erra uma do Enem: entra no caderno de revisão.
        status, r, _ = self.s.pedido(a, '/api/questoes/2', {'alternativa': 0})
        self.assertEqual(status, 200); self.assertEqual(r['estudo']['revisao']['caderno'], 1)
        # Só Fuvest: índice, densidade, revisão, perfil e questão inicial ficam na Fuvest.
        status, r, _ = self.s.pedido(a, '/api/dispositivos', {'acao': 'provas', 'ativas': ['fuvest']})
        self.assertEqual(status, 200, r); self.assertEqual(r['provas']['ativas'], ['fuvest'])
        # O painel novo vem na própria resposta (uma viagem só no endereço público), já recortado.
        self.assertEqual(r['painel']['provas']['ativas'], ['fuvest'])
        self.assertEqual(self.ids_do_indice(r['painel']), [5, 6, 7])
        # Faixas de IDs por prova, para a interface tirar na hora as questões de uma prova desligada.
        faixas = {p['id']: p['faixas'] for p in r['provas']['disponiveis']}
        self.assertTrue(all(any(a <= i <= b for a, b in faixas['fuvest']) for i in [5, 6, 7]))
        self.assertFalse(any(a <= i <= b for a, b in faixas['fuvest'] for i in [1, 2, 3, 4, 8, 9]))
        status, p, _ = self.s.pedido(a, '/api/painel')
        self.assertEqual(p['provas']['ativas'], ['fuvest'])
        self.assertEqual(self.ids_do_indice(p), [5, 6, 7])
        self.assertEqual(sorted(p['densidade']['pendentes']), [5, 6, 7])
        self.assertEqual(p['densidade']['total'], 3); self.assertEqual(p['densidade']['feitas'], 0)
        self.assertIn(p['inicial']['id'], [5, 6, 7])
        self.assertEqual(p['estudo']['revisao']['caderno'], 0)
        self.assertEqual(p['perfil']['assuntos'], [])
        self.assertEqual(p['catalogo']['ativas'], 3); self.assertEqual(p['catalogo']['total'], 9)
        # A outra conta continua com todas.
        self.assertEqual(self.s.pedido(b, '/api/painel')[1]['provas']['ativas'], ['enem', 'fuvest', 'unicamp'])
        # A volta termina com as três da Fuvest, sem precisar das outras provas.
        for i in (5, 6):
            self.assertFalse(self.s.pedido(a, f'/api/questoes/{i}', {'alternativa': 1})[1]['densidadeConcluida'])
        self.assertTrue(self.s.pedido(a, '/api/questoes/7', {'alternativa': 1})[1]['densidadeConcluida'])
        # De volta a todas: a escolha some do banco e a Enem volta, com a revisão guardada.
        status, r, _ = self.s.pedido(a, '/api/dispositivos', {'acao': 'provas', 'ativas': ['unicamp', 'enem', 'fuvest']})
        self.assertEqual(r['provas']['ativas'], ['enem', 'fuvest', 'unicamp'])
        p = self.s.pedido(a, '/api/painel')[1]
        self.assertEqual(self.ids_do_indice(p), list(range(1, 10)))
        self.assertEqual(p['estudo']['revisao']['caderno'], 1)

    def test_escolha_invalida_nao_grava(self):
        a = self.s.cliente(); self.s.cadastrar(a, 'Invalida')
        for ruim in ([], ['xyz'], 'enem', [1], None, ['enem', 'xyz'], ['enem'] * 30):
            self.assertEqual(self.s.pedido(a, '/api/dispositivos', {'acao': 'provas', 'ativas': ruim})[0], 400, ruim)
        self.assertEqual(self.s.pedido(a, '/api/painel')[1]['provas']['ativas'], ['enem', 'fuvest', 'unicamp'])
        anonimo = self.s.cliente()
        self.assertEqual(self.s.pedido(anonimo, '/api/dispositivos', {'acao': 'provas', 'ativas': ['enem']})[0], 401)

    def test_quatro_alternativas(self):
        a = self.s.cliente(); self.s.cadastrar(a, 'Unicamp')
        self.assertEqual(self.s.pedido(a, '/api/questoes/8', {'alternativa': 4})[0], 400)
        status, r, _ = self.s.pedido(a, '/api/questoes/8', {'alternativa': 1})
        self.assertEqual(status, 200); self.assertTrue(r['acerto'])
        q = self.s.pedido(a, '/api/questoes/8')[1]
        self.assertEqual(len(q['alternativas']), 4); self.assertNotIn('correta', q); self.assertEqual(q['prova'], 'unicamp')


class ContaDeTeste(unittest.TestCase):
    def test_conta_de_teste_com_todas(self):
        s = Servidor([questao(1, 'enem', 2025), questao(2, 'famerp', 2026), questao(3, 'unesp', 2026, materia=1)], perfil_teste=True)
        try:
            c = s.cliente()
            status, r, _ = s.pedido(c, '/api/entrar', {'email': 'teste', 'senha': '123'})
            self.assertEqual(status, 200)
            self.assertEqual(r['painel']['provas']['ativas'], ['enem', 'unesp', 'famerp'])
        finally:
            s.fechar()


class CatalogoGrande(unittest.TestCase):
    def test_painel_cabe_em_100_kb(self):
        qs, i = [], 1
        for prova, anos, n, letras in [('enem', range(2021, 2026), 180, 5), ('fuvest', range(2023, 2028), 90, 5),
                                       ('unesp', range(2022, 2027), 90, 5), ('unicamp', range(2023, 2028), 72, 4),
                                       ('famerp', range(2023, 2027), 80, 5)]:
            for ano in anos:
                for _ in range(n):
                    qs.append(questao(i, prova, ano, letras, materia=i * 7 % 13)); i += 1
        self.assertEqual(len(qs), 2480)
        s = Servidor(qs)
        try:
            c = s.cliente(); s.cadastrar(c, 'Grande')
            inicio = time.perf_counter()
            status, p, tamanho = s.pedido(c, '/api/painel')
            tempo = time.perf_counter() - inicio
            self.assertEqual(status, 200)
            self.assertLess(tamanho, 100_000, f'painel com {tamanho} bytes')
            self.assertLess(tempo, 1.0, f'painel em {tempo:.2f} s')
            self.assertEqual(p['catalogo']['ativas'], len(qs))
            self.assertNotIn('correta', json.dumps(p))
            status, q, tamanho = s.pedido(c, f'/api/questoes/{len(qs) // 2}')
            self.assertEqual(status, 200); self.assertLess(tamanho, 100_000)
            status, r, tamanho = s.pedido(c, '/api/questoes/1', {'alternativa': 1, 'proxima': 2})
            self.assertEqual(status, 200); self.assertLess(tamanho, 100_000, f'resposta com {tamanho} bytes')
            # Trocar de provas devolve o painel junto: também abaixo de 100 KB, e de volta ao padrão com todas.
            for lista in (['enem', 'fuvest', 'unesp', 'unicamp'], ['enem', 'fuvest', 'unesp', 'unicamp', 'famerp']):
                status, r, tamanho = s.pedido(c, '/api/dispositivos', {'acao': 'provas', 'ativas': lista})
                self.assertEqual(status, 200); self.assertLess(tamanho, 100_000, f'troca de provas com {tamanho} bytes')
                self.assertEqual(r['painel']['provas']['ativas'], lista)
        finally:
            s.fechar()


if __name__ == '__main__':
    unittest.main()
