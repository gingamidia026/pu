"""Tabela de acertos e nota (/acertos-e-nota-enem/, paginas/importar-acertos.py).

Sempre: conta e percentis num arquivo sintético com casos conhecidos (Linguagens com inglês e espanhol, questão anulada,
prova em branco, caderno de outra aplicação, ausente), percentis contra uma conta ingênua em dados sorteados, e a página
do repositório igual à que a tabela gravada dá, sem número único em linha nenhuma.
Com os microdados no computador (pasta em PU_MICRODADOS_INEP, padrão ~/craft/Enem-frentes/dados/inep): recontagem
independente numa amostra de linhas sorteadas da tabela. A recontagem tira o gabarito de ITENS_PROVA (pelo caderno, pela
posição e pela língua), e não da linha do participante como o script, e calcula os percentis ordenando a lista inteira.
Leva uns 4 minutos; sem os microdados, é pulada (como no CI).
Dominique-Oliveira-Claude🤖🧡, 18/11/2026.
"""
import collections
import csv
import importlib.util
import json
import os
import random
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
especificacao = importlib.util.spec_from_file_location('importar_acertos', RAIZ / 'paginas/importar-acertos.py')
ia = importlib.util.module_from_spec(especificacao)
especificacao.loader.exec_module(ia)
MICRODADOS = Path(os.environ.get('PU_MICRODADOS_INEP', Path.home() / 'craft/Enem-frentes/dados/inep'))
ANO = 2025
CABECA = ['NU_SEQUENCIAL', 'TP_PRESENCA_CN', 'TP_PRESENCA_CH', 'TP_PRESENCA_LC', 'TP_PRESENCA_MT', 'CO_PROVA_CN', 'CO_PROVA_CH',
          'CO_PROVA_LC', 'CO_PROVA_MT', 'NU_NOTA_CN', 'NU_NOTA_CH', 'NU_NOTA_LC', 'NU_NOTA_MT', 'TX_RESPOSTAS_CN', 'TX_RESPOSTAS_CH',
          'TX_RESPOSTAS_LC', 'TX_RESPOSTAS_MT', 'TP_LINGUA', 'TX_GABARITO_CN', 'TX_GABARITO_CH', 'TX_GABARITO_LC', 'TX_GABARITO_MT']


def percentil_ingenuo(notas, p):
    ordenadas = sorted(notas)
    posto = -(-p * len(ordenadas) // 100)  # teto(p% de n), a partir de 1
    return ordenadas[posto - 1]


class Sintetico(unittest.TestCase):
    def linha(self, **campos):
        base = {c: '' for c in CABECA}
        base.update({'TP_PRESENCA_CN': '0', 'TP_PRESENCA_CH': '0', 'TP_PRESENCA_LC': '0', 'TP_PRESENCA_MT': '0', 'TP_LINGUA': '0'})
        base.update(campos)
        return [base[c] for c in CABECA]

    def test_contagem_com_casos_conhecidos(self):
        gab_ch = 'ABCDE' * 9
        gab_cn = 'X' + 'A' * 43 + 'X'  # duas anuladas: 43 válidas
        gab_lc = 'BBBBB' + 'CCCCC' + 'D' * 40  # 5 de inglês, 5 de espanhol, 40 comuns
        linhas = [
            # CH: 45 certas; 10 certas (o resto errado); prova em branco (fora); caderno de outra aplicação (fora); ausente.
            self.linha(TP_PRESENCA_CH='1', CO_PROVA_CH='1447', NU_NOTA_CH='800.5', TX_RESPOSTAS_CH=gab_ch, TX_GABARITO_CH=gab_ch),
            self.linha(TP_PRESENCA_CH='1', CO_PROVA_CH='1448', NU_NOTA_CH='450.0', TX_RESPOSTAS_CH=gab_ch[:10] + '*' * 35, TX_GABARITO_CH=gab_ch),
            self.linha(TP_PRESENCA_CH='1', CO_PROVA_CH='1449', NU_NOTA_CH='0', TX_RESPOSTAS_CH='.' * 45, TX_GABARITO_CH=gab_ch),
            self.linha(TP_PRESENCA_CH='1', CO_PROVA_CH='1587', NU_NOTA_CH='500.0', TX_RESPOSTAS_CH=gab_ch, TX_GABARITO_CH=gab_ch),
            self.linha(TP_PRESENCA_CH='0', CO_PROVA_CH='1447', NU_NOTA_CH='', TX_RESPOSTAS_CH='', TX_GABARITO_CH=''),
            # CN: todas "A", inclusive nas anuladas: 43 acertos, nunca 45. Resposta dupla (*) é erro; a 1ª anulada não conta (19, não 20).
            self.linha(TP_PRESENCA_CN='1', CO_PROVA_CN='1483', NU_NOTA_CN='870.1', TX_RESPOSTAS_CN='A' * 45, TX_GABARITO_CN=gab_cn),
            self.linha(TP_PRESENCA_CN='1', CO_PROVA_CN='1484', NU_NOTA_CN='600.0', TX_RESPOSTAS_CN='A' * 20 + '*' * 25, TX_GABARITO_CN=gab_cn),
            # LC: inglês certo (B) e espanhol (C) dependem da língua escolhida.
            self.linha(TP_PRESENCA_LC='1', CO_PROVA_LC='1459', NU_NOTA_LC='700.0', TP_LINGUA='0', TX_RESPOSTAS_LC='BBBBB' + 'D' * 40, TX_GABARITO_LC=gab_lc),
            self.linha(TP_PRESENCA_LC='1', CO_PROVA_LC='1460', NU_NOTA_LC='650.0', TP_LINGUA='1', TX_RESPOSTAS_LC='BBBBB' + 'D' * 40, TX_GABARITO_LC=gab_lc),
            self.linha(TP_PRESENCA_LC='1', CO_PROVA_LC='1461', NU_NOTA_LC='710.0', TP_LINGUA='1', TX_RESPOSTAS_LC='CCCCC' + 'D' * 40, TX_GABARITO_LC=gab_lc),
        ]
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / 'RESULTADOS_2025.csv'
            with open(caminho, 'w', encoding='latin-1', newline='') as arquivo:
                escritor = csv.writer(arquivo, delimiter=';')
                escritor.writerow(CABECA)
                escritor.writerows(linhas)
            histogramas, validas, fora = ia.contar(caminho, 2025)
        self.assertEqual({a: dict(h) for a, h in histogramas['CH'].items()}, {45: {8005: 1}, 10: {4500: 1}})
        self.assertEqual({a: dict(h) for a, h in histogramas['CN'].items()}, {43: {8701: 1}, 19: {6000: 1}})
        self.assertEqual({a: dict(h) for a, h in histogramas['LC'].items()}, {45: {7000: 1, 7100: 1}, 40: {6500: 1}})
        self.assertEqual(dict(validas['CN']), {43: 2})
        self.assertEqual(fora[('CH', 'em branco com nota 0')], 1)
        self.assertEqual(fora[('CH', 'outro caderno')], 1)

    def test_percentis_contra_conta_ingenua(self):
        sorteio = random.Random(20261118)
        for tamanho in (1, 2, 3, 7, 30, 101, 1000):
            notas = [round(sorteio.uniform(300, 900), 1) for _ in range(tamanho)]
            contagem = collections.Counter(round(n * 10) for n in notas)
            r = ia.resumo(contagem)
            self.assertEqual(r['participantes'], tamanho)
            self.assertEqual((r['menor'], r['maior']), (min(notas), max(notas)))
            for p in ia.PERCENTIS:
                self.assertEqual(r[f'p{p}'], percentil_ingenuo(notas, p), (tamanho, p))


class Pagina(unittest.TestCase):
    def setUp(self):
        self.tabela = RAIZ / f'paginas/tabelas/acertos-nota-{ANO}.json'
        self.pagina = json.loads((RAIZ / 'paginas/conteudo/acertos-e-nota-enem.json').read_text(encoding='utf-8'))

    def test_pagina_igual_a_tabela(self):
        ano, dados, validas, fora, origem = ia.ler_tabela(self.tabela)
        self.assertEqual(ia.conteudo_da_pagina(ano, dados, validas, fora, origem, origem['contado_em']), self.pagina)
        self.assertEqual(origem['pagina_oficial'], ia.PAGINA_INEP)
        self.assertRegex(origem['sha256'], r'^[0-9a-f]{64}$')

    def test_faixa_nunca_numero_unico(self):
        blocos = [b for b in self.pagina['blocos'] if b['tipo'] == 'dados']
        self.assertEqual([b['id'] for b in blocos], ['linguagens', 'humanas', 'natureza', 'matematica'])
        for bloco in blocos:
            self.assertEqual(bloco['colunas'], ['Acertos', 'Participantes', 'Menor nota', 'P10', 'P25', 'Mediana', 'P75', 'P90', 'Maior nota'])
            for linha in bloco['linhas']:
                if linha.get('aviso'):
                    continue
                self.assertEqual(len(linha['valores']), 9)
                self.assertTrue(linha['fonte'].startswith('https://www.gov.br/inep/'))
                participantes = int(linha['valores'][1].replace('.', ''))
                if participantes < ia.AMOSTRA_MINIMA:
                    self.assertEqual(set(linha['valores'][3:8]), {'poucos participantes'})
                else:
                    numeros = [float(v.replace(',', '.')) for v in linha['valores'][2:]]
                    self.assertEqual(numeros, sorted(numeros), 'menor ≤ P10 ≤ … ≤ maior')
        texto = json.dumps(self.pagina, ensure_ascii=False)
        self.assertIn(f'Enem {ANO}', self.pagina['titulo'])
        self.assertIn('muda a cada prova', texto)
        self.assertIn('Ela não diz qual vai ser a sua nota', texto)


@unittest.skipUnless((MICRODADOS / str(ANO) / f'RESULTADOS_{ANO}.csv').is_file(), 'sem os microdados do Inep neste computador')
class Recontagem(unittest.TestCase):
    """Recontagem independente: gabarito de ITENS_PROVA, posição global do item e percentis pela lista ordenada."""
    BASE = {'LC': 1, 'CH': 46, 'CN': 91, 'MT': 136}

    def test_amostra_da_tabela(self):
        _, dados, _, _, _ = ia.ler_tabela(RAIZ / f'paginas/tabelas/acertos-nota-{ANO}.json')
        sorteio = random.Random(20261118)
        amostra = {}
        for area in ('LC', 'CH', 'CN', 'MT'):
            candidatas = sorted((int(a) for a, r in dados[area].items() if r['participantes'] >= ia.AMOSTRA_MINIMA))
            for acertos in sorteio.sample(candidatas, 3) + [min(candidatas), max(candidatas)]:
                amostra[(area, acertos)] = []
        regulares = {a: {str(c) for c in cs} for a, cs in ia.REGULARES[ANO].items()}
        # Gabarito por (caderno, posição global, língua) direto do arquivo de itens.
        gabarito = {}
        with open(MICRODADOS / str(ANO) / f'ITENS_PROVA_{ANO}.csv', encoding='latin-1', newline='') as arquivo:
            for item in csv.DictReader(arquivo, delimiter=';'):
                if item['CO_PROVA'] in regulares[item['SG_AREA']]:
                    gabarito[(item['CO_PROVA'], int(item['CO_POSICAO']), item['TP_LINGUA'])] = item['TX_GABARITO']
        totais = collections.Counter()
        with open(MICRODADOS / str(ANO) / f'RESULTADOS_{ANO}.csv', encoding='latin-1', newline='') as arquivo:
            leitor = csv.reader(arquivo, delimiter=';')
            col = {nome: i for i, nome in enumerate(next(leitor))}
            for linha in leitor:
                for area in ('LC', 'CH', 'CN', 'MT'):
                    caderno = linha[col['CO_PROVA_' + area]]
                    if linha[col['TP_PRESENCA_' + area]] != '1' or caderno not in regulares[area] or not linha[col['NU_NOTA_' + area]]:
                        continue
                    respostas = linha[col['TX_RESPOSTAS_' + area]]
                    if set(respostas) == {'.'}:
                        continue
                    certas = 0
                    for indice, letra in enumerate(respostas):
                        posicao = self.BASE[area] + indice
                        lingua = linha[col['TP_LINGUA']] if area == 'LC' and indice < 5 else ''
                        certo = gabarito[(caderno, posicao, lingua)]
                        if certo != 'X' and letra == certo:
                            certas += 1
                    totais[area] += 1
                    if (area, certas) in amostra:
                        amostra[(area, certas)].append(float(linha[col['NU_NOTA_' + area]]))
        for area in ('LC', 'CH', 'CN', 'MT'):
            self.assertEqual(totais[area], sum(r['participantes'] for r in dados[area].values()), f'participantes de {area}')
        for (area, acertos), notas in sorted(amostra.items()):
            r = dados[area][str(acertos)]
            with self.subTest(area=area, acertos=acertos):
                self.assertEqual(r['participantes'], len(notas))
                self.assertEqual((r['menor'], r['maior']), (min(notas), max(notas)))
                for p in ia.PERCENTIS:
                    self.assertEqual(r[f'p{p}'], percentil_ingenuo(notas, p))
        print(f'\n  recontagem independente: {len(amostra)} linhas sorteadas iguais; participantes por prova iguais: {dict(totais)}')


if __name__ == '__main__':
    unittest.main(verbosity=1)
