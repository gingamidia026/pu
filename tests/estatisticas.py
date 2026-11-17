"""Estatística oficial do Inep por questão: casamento, somas e segurança do gabarito. Sem tokens, sem rede.

Dominique-Oliveira-Claude🤖🧡, 17/11/2026.
1. Gerador com microdados sintéticos: casa pela cor, posição e língua, recusa gabarito diferente e caderno incompleto.
2. Servidor real com catálogo temporário: a estatística só sai na resposta depois de responder (questão simples,
   repetição do envio e conjunto); nunca na questão, no painel, na próxima questão adiantada nem nos estáticos.
3. Repositório: nenhum arquivo de estatística no git (o GitHub Pages publica tudo) e nenhum texto chama a
   distribuição do catálogo de "média histórica".
4. Dados reais, quando existem (PU_CATALOGO ou .catalogo/atual.json e PU_MICRODADOS_INEP): 100% de gabarito
   igual nas questões casadas, conferido de novo direto no CSV, e soma das frequências igual à amostra.
"""
import csv
import http.cookiejar
import importlib.util
import json
import os
import re
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('estatisticas_inep', RAIZ / 'scripts/estatisticas-inep.py')
gerador = importlib.util.module_from_spec(spec); spec.loader.exec_module(gerador)
MARCA = 777013  # contagem sintética única: se aparecer fora da resposta, vazou
CAB_FREQ = 'ano;co_prova;cor;area;posicao;co_item;lingua;gabarito;anulado;n_presentes;n_A;n_B;n_C;n_D;n_E;n_branco;n_dupla;n_outro;pct_acerto'
CAB_ITENS = 'CO_POSICAO;SG_AREA;CO_ITEM;TX_GABARITO;CO_HABILIDADE;IN_ITEM_ABAN;TX_MOTIVO_ABAN;NU_PARAM_A;NU_PARAM_B;NU_PARAM_C;TX_COR;CO_PROVA;TP_LINGUA;IN_ITEM_ADAPTADO'


def questao(id, chave, numero, correta, area='Ciências Humanas', materia='História', **extra):
    prova, ano, dia, caderno, _ = chave.split(':')
    return dict(id=id, chave=chave, prova=prova, edicao=f'{prova.capitalize()} {ano}', ano=int(ano), dia=int(dia), caderno=int(caderno),
                numero=numero, area=area, materia=materia, topico='Tópico', assunto='Assunto', conteudo='', titulo=f'Questão {numero}',
                enunciado='Enunciado sintético.', alternativas=['a', 'b', 'c', 'd', 'e'], correta=correta,
                explicacao='Ainda não há solução comentada para esta questão.', imagens=[], textoParcial=False,
                revisar=False, oficial=True, **{'textoComum': '', 'grupo': '', **extra})


def microdados(pasta):
    """2024: itens 9001 (pos 46, gabarito B), 9002 e 9003 (conjunto), 9004 (PU diverge), 9005 (falta num caderno),
    9006 (inglês, pos 1) e 9007 (espanhol, pos 1). 2025 vazio."""
    linhas_f, linhas_i = [CAB_FREQ], [CAB_ITENS]
    regulares = gerador.REGULARES[2024]
    itens = {('CH', 46, ''): ('9001', 'B'), ('CH', 47, ''): ('9002', 'A'), ('CH', 48, ''): ('9003', 'E'),
             ('CH', 49, ''): ('9004', 'C'), ('CH', 50, ''): ('9005', 'D'), ('LC', 1, '0'): ('9006', 'D'), ('LC', 1, '1'): ('9007', 'A')}
    for (area, pos, lingua), (item, gab) in itens.items():
        for n, (codigo, cor) in enumerate(regulares[area]):
            if item == '9005' and n == 3:
                continue  # o item some do 4º caderno: casamento inseguro
            p = pos if n == 0 else (pos + n if area == 'CH' else pos)  # outra ordem nos outros cadernos
            conta = [100 + n, MARCA if (item == '9001' and n == 0) else 200, 300, 400, 500, 7, 3, 0]
            linhas_f.append(';'.join(map(str, [2024, codigo, cor, area, p, item, lingua, gab, 'nao', sum(conta), *conta, ''])))
            linhas_i.append(';'.join(map(str, [p, area, item, gab, 12, 0, '', 1, 1, 0.2, cor, codigo, lingua, 0])))
    (pasta / '2024').mkdir(parents=True); (pasta / '2025').mkdir()
    (pasta / 'frequencias_2024.csv').write_text('\n'.join(linhas_f) + '\n')
    (pasta / '2024/ITENS_PROVA_2024.csv').write_text('\n'.join(linhas_i) + '\n', encoding='latin-1')
    (pasta / 'frequencias_2025.csv').write_text(CAB_FREQ + '\n')
    (pasta / '2025/ITENS_PROVA_2025.csv').write_text(CAB_ITENS + '\n', encoding='latin-1')


class Estatisticas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); raiz = Path(cls.tmp.name)
        microdados(raiz / 'inep')
        grupo = dict(grupo='teste:Q47a48', textoComum='Texto comum sintético.', grupoIds=[21, 22])
        cls.questoes = [questao(20, 'enem:2024:1:1:46', 46, 1),
                        questao(21, 'enem:2024:1:1:47', 47, 0, **grupo), questao(22, 'enem:2024:1:1:48', 48, 4, **grupo),
                        questao(23, 'enem:2024:1:1:49', 49, 0), questao(24, 'enem:2024:1:1:50', 50, 3),
                        questao(25, 'enem:2024:1:1:1', 1, 3, area='Linguagens', materia='Inglês'),
                        questao(26, 'enem:2024:2:5:91', 91, 0, area='Ciências da Natureza', materia='Física'),
                        questao(27, 'fuvest:2025:1:1:1', 1, 2)]
        (raiz / 'catalogo').mkdir()
        cls.catalogo = raiz / 'catalogo/atual.json'
        cls.catalogo.write_text(json.dumps({'formato': 1, 'questoes': cls.questoes, 'anuladas': 0, 'revisar': 0, 'versao': 'teste'}))
        cls.resultado = gerador.gerar(cls.catalogo, raiz / 'inep', '2026-11-17')
        (raiz / 'catalogo/estatisticas-inep.json').write_text(json.dumps(cls.resultado, ensure_ascii=False))
        cls.raiz = raiz

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_1_casamento_e_motivos(self):
        q = self.resultado['questoes']
        self.assertNotIn('fuvest:2025:1:1:1', q, 'só Enem 2024 e 2025')
        e = q['enem:2024:1:1:46']
        self.assertEqual(e['situacao'], 'validado'); self.assertEqual(e['coItem'], 9001)
        self.assertEqual([c['codigo'] for c in e['cadernos']], [1383, 1384, 1385, 1386])
        self.assertEqual(e['alternativas'][1]['n'], MARCA + 600)
        self.assertEqual(e['erradaMaisMarcada'], 'E'); self.assertEqual(e['maisMarcada'], 'B')
        self.assertEqual(q['enem:2024:1:1:1']['coItem'], 9006, 'inglês escolhe o item de TP_LINGUA 0')
        self.assertIn('Gabarito do PU (A) diferente', q['enem:2024:1:1:49']['motivo'])
        self.assertIn('não aparece uma vez só', q['enem:2024:1:1:50']['motivo'])
        self.assertIn('Caderno 5 do dia 2 sem correspondência', q['enem:2024:2:5:91']['motivo'])
        for chave, r in q.items():
            if r['situacao'] == 'validado':
                soma = sum(a['n'] for a in r['alternativas']) + r['branco']['n'] + r['dupla']['n'] + r['outro']['n']
                self.assertEqual(soma, r['amostra'], chave)
                self.assertEqual(sum(c['amostra'] for c in r['cadernos']), r['amostra'], chave)
            else:
                self.assertTrue(r['motivo'], chave)

    def test_2_servidor_so_entrega_depois_da_resposta(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0)); porta = s.getsockname()[1]
        origem = f'http://127.0.0.1:{porta}'
        (self.raiz / 'dados').mkdir(exist_ok=True)
        proc = subprocess.Popen(['python3', str(RAIZ / 'app/servidor.py')], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                env={**os.environ, 'DADOS': str(self.raiz / 'dados'), 'PORTA': str(porta), 'ORIGEM': origem,
                                     'CATALOGO': str(self.catalogo), 'PERFIL_TESTE': '0'})
        cliente = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

        def pedido(caminho, dados=None, cru=False):
            req = urllib.request.Request(origem + caminho, data=None if dados is None else json.dumps(dados).encode(),
                                         headers={'Origin': origem, 'Content-Type': 'application/json'})
            try: r = cliente.open(req)
            except urllib.error.HTTPError as e: r = e
            with r:
                corpo = r.read()
                return r.status, (corpo.decode('utf-8', 'replace') if cru else json.loads(corpo))
        vazou = lambda texto: str(MARCA) in texto or '"erradaMaisMarcada"' in texto or '"amostra"' in texto
        try:
            for _ in range(100):
                try: urllib.request.urlopen(origem + '/api/saude', timeout=1).close(); break
                except OSError: time.sleep(.05)
            cadastro = pedido('/api/cadastro', {'nome': 'Estatística', 'email': 'estat@example.com', 'senha': 'Senha longa estatística 123!'})
            self.assertEqual(cadastro[0], 200, cadastro)
            for caminho in ['/', '/app.js', '/api/painel', '/api/questoes/20', '/api/questoes/21', '/api/questoes/27']:
                status, texto = pedido(caminho, cru=True)
                self.assertEqual(status, 200, caminho); self.assertFalse(vazou(texto), 'estatística antes da resposta em ' + caminho)
            status, r = pedido('/api/questoes/20', {'alternativa': 0, 'envio': 'estatistica-envio-0000000001', 'proxima': 21})
            self.assertEqual(status, 200, r)
            e = r['estatisticaOriginal']
            self.assertEqual(e['situacao'], 'validado'); self.assertEqual(e['alternativas'][1]['n'], MARCA + 600)
            for campo in ['amostra', 'cadernos', 'fonte', 'arquivo', 'baixadoEm', 'processadoEm', 'coItem']:
                self.assertIn(campo, e)
            self.assertFalse(vazou(json.dumps(r['proximaQuestao'])), 'próxima questão adiantada sem estatística')
            self.assertEqual(pedido('/api/questoes/20', {'alternativa': 0, 'envio': 'estatistica-envio-0000000001'})[1]['estatisticaOriginal'], e,
                             'repetição do envio devolve a mesma estatística')
            status, r = pedido('/api/questoes/21', {'respostas': [{'id': 21, 'alternativa': 0}, {'id': 22, 'alternativa': 1}], 'envio': 'estatistica-conjunto-000000001'})
            self.assertEqual(status, 200, r)
            self.assertEqual([x['estatisticaOriginal']['coItem'] for x in r['resultados']], [9002, 9003])
            self.assertEqual(pedido('/api/questoes/27', {'alternativa': 2})[1]['estatisticaOriginal']['situacao'], 'indisponivel')
            self.assertEqual(pedido('/api/questoes/23', {'alternativa': 0})[1]['estatisticaOriginal']['situacao'], 'indisponivel')
            status, texto = pedido('/api/painel', cru=True)
            self.assertFalse(vazou(texto), 'painel depois de responder também sem estatística')
        finally:
            proc.terminate(); proc.wait(); proc.stderr.close()

    def test_3_repositorio_sem_estatistica_publica(self):
        arquivos = subprocess.run(['git', 'ls-files'], cwd=RAIZ, capture_output=True, text=True, check=True).stdout.split('\n')
        self.assertFalse([a for a in arquivos if a.endswith('estatisticas-inep.json')])
        for a in arquivos:
            if a.endswith(('.json', '.csv', '.js', '.html')) and (RAIZ / a).is_file():
                self.assertNotIn('"erradaMaisMarcada":', (RAIZ / a).read_text(errors='replace'), a)
        self.assertEqual(subprocess.run(['git', 'check-ignore', '-q', '.catalogo/estatisticas-inep.json'], cwd=RAIZ).returncode, 0)
        self.assertIn('.catalogo', (RAIZ / '.dockerignore').read_text().split())
        for a in ['app/public/app.js', 'app/public/index.html', 'index.html', 'app/acompanhamento.py']:
            for trecho in re.findall(r'.{0,40}m[ée]dia hist[óo]rica', (RAIZ / a).read_text(), re.I):
                self.assertRegex(trecho, r'[Nn]ão', f'{a}: "{trecho}" chama a distribuição de média histórica')

    def test_5_texto_da_correcao(self):
        """A linha da correção: indisponível sem dado; com dado, acerto, errada mais marcada, amostra e fonte.
        E ela só é montada em revelar(), que roda com a resposta certa já na tela."""
        js = (RAIZ / 'app/public/app.js').read_text()
        inicio = js.index('function estatisticaHtml(')
        funcao = js[inicio:js.index('\n}\n', inicio) + 2]
        self.assertEqual(js.count('estatisticaHtml('), 2, 'definida uma vez e chamada só em revelar()')
        chamada = js.index('estatisticaHtml(resultado.estatisticaOriginal)')
        self.assertLess(js.rindex('const revelar = ', 0, chamada), chamada)
        self.assertGreater(js.index('ligarTreino();', chamada), chamada)
        e = self.resultado['questoes']['enem:2024:1:1:46']
        programa = (js[js.index('const escapar = '):js.index('\n', js.index('const escapar = '))] + '\n' + funcao +
                    f'\nconsole.log(JSON.stringify([estatisticaHtml({json.dumps(e)}), estatisticaHtml({{situacao: "indisponivel"}}), estatisticaHtml(null)]));')
        validado, indisponivel, nulo = json.loads(subprocess.run(['node', '-e', programa], capture_output=True, text=True, check=True).stdout)
        self.assertIn(f'{e["acerto"]:.1f}%'.replace('.', ','), validado)
        self.assertIn('A errada mais marcada foi a E', validado)
        self.assertIn(f'{e["amostra"]:,}'.replace(',', '.'), validado)
        self.assertIn('Microdados do Enem 2024, Inep', validado); self.assertIn('17/11/2026', validado)
        self.assertIn('Dado da aplicação original indisponível.', indisponivel); self.assertEqual(indisponivel, nulo)

    def test_4_dados_reais(self):
        catalogo = Path(os.environ.get('PU_CATALOGO', RAIZ / '.catalogo/atual.json'))
        inep = gerador.PADRAO_INEP
        if not catalogo.is_file() or not (inep / 'frequencias_2024.csv').is_file():
            self.skipTest('sem catálogo ou microdados locais (normal fora do PC do PU)')
        resultado = gerador.gerar(catalogo, inep, 'teste')
        pu = {q['chave']: q for q in json.loads(catalogo.read_text())['questoes']}
        azul = {}
        for ano in gerador.FONTES:
            with open(inep / f'frequencias_{ano}.csv', encoding='utf-8', newline='') as f:
                for r in csv.DictReader(f, delimiter=';'):
                    if r['cor'] == 'AZUL' and int(r['co_prova']) == gerador.REGULARES[ano][r['area']][0][0]:
                        azul[(ano, int(r['posicao']), r['lingua'])] = r
        validadas = 0
        for chave, r in resultado['questoes'].items():
            if r['situacao'] != 'validado':
                continue
            validadas += 1
            q = pu[chave]; lingua = {'inglês': '0', 'espanhol': '1'}.get(r['lingua'], '')
            linha = azul[(q['ano'], q['numero'], lingua)]
            self.assertEqual(int(linha['co_item']), r['coItem'], chave)
            self.assertEqual(linha['gabarito'], 'ABCDE'[q['correta']], f'{chave}: gabarito do PU diferente do Inep')
            soma = sum(a['n'] for a in r['alternativas']) + r['branco']['n'] + r['dupla']['n'] + r['outro']['n']
            self.assertEqual(soma, r['amostra'], chave)
            self.assertAlmostEqual(r['acerto'], 100 * r['alternativas']['ABCDE'.index(linha['gabarito'])]['n'] / r['amostra'], places=2)
        enem = [k for k, q in pu.items() if q.get('prova') == 'enem' and q.get('ano') in gerador.FONTES]
        self.assertEqual(len(resultado['questoes']), len(enem))
        print(f'\n  dados reais: {validadas} de {len(enem)} questões do Enem 2024/2025 validadas, gabarito 100% igual')
        instalado = catalogo.parent / 'estatisticas-inep.json'
        if instalado.is_file():
            gravado = json.loads(instalado.read_text())['questoes']
            limpa = lambda d: {k: {c: v for c, v in r.items() if c != 'processadoEm'} for k, r in d.items()}
            self.assertEqual(limpa(gravado), limpa(resultado['questoes']), 'arquivo instalado desatualizado: rode scripts/estatisticas-inep.py')


if __name__ == '__main__':
    unittest.main(verbosity=2)
