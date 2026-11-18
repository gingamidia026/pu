"""Pesos e notas de corte do Sisu no simulador (app/public/pesos-sisu.js, gerado por scripts/importar-pesos-sisu.py).

Sempre: formato dos dados (edição, fontes oficiais https do MEC, data, pesos numéricos com soma maior que zero, nota de
corte em número ou vazia, nada de HTML nos textos) e o servidor entregando o arquivo.
Com as planilhas oficiais no computador (pasta em PU_COLETA_SISU, padrão
~/craft/Enem-frentes/dados/coleta/pesos/baixados/sisu-arquivos): 10 cursos sorteados conferidos contra as duas planilhas,
lidas aqui por outro caminho (expressões no XML da folha, sem o leitor do importador), e o arquivo igual ao que o
importador gera.
Dominique-Oliveira-Claude🤖🧡, 18/11/2026.
"""
import json
import os
import random
import re
import subprocess
import sys
import unittest
import zipfile
from html import unescape
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
COLETA = Path(os.environ.get('PU_COLETA_SISU', Path.home() / 'craft/Enem-frentes/dados/coleta/pesos/baixados/sisu-arquivos'))
VAGAS = COLETA / 'Portal_Sisu_2026_Vagas ofertadas.xlsx'
CORTES = COLETA / 'Portal Sisu_ Sisu2026_inscrições e notas de corte.xlsx'
NUMERO = re.compile(r'^\d+(,\d{1,2})?$')


def dados():
    texto = (RAIZ / 'app/public/pesos-sisu.js').read_text(encoding='utf-8')
    return json.loads(texto[texto.index('= {') + 2:texto.rindex('; })')])


def para_numero(texto):
    return float(texto.replace(',', '.'))


class Formato(unittest.TestCase):
    def test_edicao_fontes_e_valores(self):
        d = dados()
        self.assertEqual((d['edicao'], d['etapa']), ('Sisu 2026', 'chamada regular'))
        self.assertRegex(d['conferido_em'], r'^\d{4}-\d{2}-\d{2}$')
        for chave in ('pagina', 'fonte_pesos', 'fonte_cortes'):
            self.assertTrue(d[chave].startswith('https://sisu.mec.gov.br/'), d[chave])
        self.assertGreater(len(d['cursos']), 1000)
        for sigla in ('UNIFESP', 'UFSCAR', 'UFABC'):
            self.assertIn(sigla, d['instituicoes'])
        textos = list(d['instituicoes'].values()) + d['modalidades'] + [x for l in d['locais'] for x in l]
        for curso in d['cursos']:
            sigla, local, nome, grau, turno, pesos, minimas, media, modalidades = curso
            textos += [nome, grau, turno]
            self.assertIn(sigla, d['instituicoes'])
            self.assertLess(local, len(d['locais']))
            self.assertEqual(len(pesos), 5)
            self.assertTrue(all(NUMERO.match(p) for p in pesos + minimas + [media]), curso)
            self.assertGreater(sum(map(para_numero, pesos)), 0)
            self.assertTrue(modalidades and modalidades[0][1] == 'AC', 'ampla concorrência primeiro')
            for m in modalidades:
                self.assertLess(m[0], len(d['modalidades']))
                self.assertTrue(m[2] == '' or (NUMERO.match(m[2]) and 0 < para_numero(m[2]) <= 1000), m)
                self.assertGreater(m[3], 0, 'modalidade sem vaga não entra')
        self.assertFalse([t for t in textos if re.search(r'[<>]', t)], 'texto com sinal de HTML')

    def test_servidor_entrega_o_arquivo(self):
        servidor = (RAIZ / 'app/servidor.py').read_text(encoding='utf-8')
        self.assertIn("'/pesos-sisu.js': 'pesos-sisu.js'", servidor)
        self.assertEqual(servidor.count("'/pesos-sisu.js'"), 4, 'rota, tipo e as duas listas de recursos')


def folha(caminho):
    """Linhas da folha 2 como listas de texto, lidas com expressões no XML (outro caminho que o do importador)."""
    with zipfile.ZipFile(caminho) as z:
        compartilhados = [unescape(re.sub(r'<[^>]+>', '', si)) for si in re.findall(r'<si>(.*?)</si>', z.read('xl/sharedStrings.xml').decode(), re.S)]
        xml = z.read('xl/worksheets/sheet2.xml').decode()
    linhas = []
    for linha in re.finditer(r'<row [^>]*>(.*?)</row>', xml, re.S):
        celulas = {}
        for c in re.finditer(r'<c r="([A-Z]+)\d+"([^>]*?)(?:/>|>(.*?)</c>)', linha.group(1), re.S):
            coluna, atributos, corpo = c.groups()
            valor = re.search(r'<v>(.*?)</v>', corpo or '')
            texto = valor.group(1) if valor else ''
            if 't="s"' in atributos and valor:
                texto = compartilhados[int(texto)]
            celulas[coluna] = unescape(texto)
        linhas.append(celulas)
    cabeca = linhas[0]
    return [{cabeca[k]: l.get(k, '') for k in cabeca} for l in linhas[1:]]


@unittest.skipUnless(VAGAS.is_file() and CORTES.is_file(), 'sem as planilhas oficiais do Sisu neste computador')
class ContraAsPlanilhas(unittest.TestCase):
    def test_dez_cursos_sorteados(self):
        d = dados()
        sorteio = random.Random(20261118)
        escolhidos = sorteio.sample(d['cursos'], 10)
        vagas, cortes = folha(VAGAS), folha(CORTES)
        areas = ['LINGUAGENS', 'CIENCIAS_HUMANAS', 'CIENCIAS_NATUREZA', 'MATEMATICA', 'REDACAO']
        relato = []
        for sigla, local, nome, grau, turno, pesos, minimas, media, modalidades in escolhidos:
            campus, municipio, uf = d['locais'][local]
            linhas_v = [l for l in vagas if l['SG_IES'].strip() == sigla and l['NO_CURSO'].strip() == nome and l['DS_TURNO'].strip() == turno
                        and l['NO_CAMPUS'].strip() == campus and l['DS_GRAU'].strip() == grau]
            with self.subTest(curso=f'{sigla} {nome} {campus} {turno}'):
                self.assertTrue(linhas_v)
                codigos = {l['CO_IES_CURSO'] for l in linhas_v}
                self.assertEqual(len(codigos), 1, 'um curso só com esse nome, campus, grau e turno')
                for l in linhas_v:
                    self.assertEqual([float(l['PESO_' + a]) for a in areas], [para_numero(p) for p in pesos])
                    self.assertEqual([round(float(l['NOTA_MINIMA_' + a] or 0), 2) for a in areas], [para_numero(p) for p in minimas])
                self.assertEqual(len(modalidades), sum(1 for l in linhas_v if int(l['QT_VAGAS_OFERTADAS']) > 0))
                for indice, cota, corte, vagas_m in modalidades:
                    descricao = d['modalidades'][indice]
                    par = [c for c in cortes if c['CO_IES_CURSO'] in codigos and c['DS_TURNO'].strip() == turno
                           and c['TIPO_CONCORRENCIA'].strip() == cota and c['DS_MOD_CONCORRENCIA'].strip() == descricao]
                    self.assertEqual(len(par), 1, (cota, descricao[:40]))
                    oficial = round(float(par[0]['NU_NOTACORTE'] or 0), 2)
                    self.assertEqual(para_numero(corte) if corte else 0.0, oficial)
                    self.assertEqual(int(par[0]['QT_VAGAS_CONCORRENCIA']), vagas_m)
                ac = modalidades[0][2]
                relato.append(f'{sigla} {nome} ({campus}, {turno}): pesos {"/".join(pesos)}, corte AC {ac or "sem nota de corte"}')
        print('\n  ' + '\n  '.join(relato))

    def test_arquivo_igual_ao_importador(self):
        saida = subprocess.run([sys.executable, '-I', str(RAIZ / 'scripts/importar-pesos-sisu.py'), '--vagas', str(VAGAS), '--cortes', str(CORTES),
                                '--coleta', '/nao-usado', '--conferir'], capture_output=True, text=True)
        self.assertEqual(saida.returncode, 0, saida.stdout + saida.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=1)
