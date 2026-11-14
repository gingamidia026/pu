"""Regressões do extrator nos cadernos oficiais da Fuvest, Unesp, Unicamp e Famerp. Sem rede, IA ou escrita no cofre.

Rodar com a cópia do cofre: PU_COFRE_VESTIBULAR=<cópia> .venv-extracao/bin/python -I tests/extracao_bancas.py
Os cadernos ficam em `Provas <Banca>/<banca>-<ano>-<caderno>.pdf`, com o `-gabarito.pdf` e o `.json` ao lado.
Dominique-Oliveira-Claude🤖🧡, 14/11/2026.
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'ferramentas/importar-prova'))
import importar  # noqa: E402
import formatos  # noqa: E402

EDICOES = {
    'Fuvest': ['fuvest-2023-V', 'fuvest-2024-V', 'fuvest-2025-V1', 'fuvest-2026-V1', 'fuvest-2027-V1'],
    'Unesp': ['unesp-2022-V1', 'unesp-2023-V1', 'unesp-2024-V1', 'unesp-2025-V1', 'unesp-2026-V1'],
    'Unicamp': ['unicamp-2023-QZ', 'unicamp-2024-QY', 'unicamp-2025-QZ', 'unicamp-2026-QX', 'unicamp-2027-QY'],
    'Famerp': ['famerp-2023-V1', 'famerp-2024-V1', 'famerp-2025-V1', 'famerp-2026-V1'],
}


def caderno(stem):
    banca = stem.split('-')[0]
    return importar.COFRE / f'Provas {formatos.FORMATOS[banca].nome}' / f'{stem}.pdf'


def numeros_marcados(pdf):
    """Números de questão que o recorte acha no caderno, sem extrair mídias."""
    paginas = importar.ler_paginas(pdf)
    formatos.formato_de(pdf).normalizar(paginas)
    achados = []
    for pg in paginas:
        importar.preparar_pagina(pg)
        achados += [int(m[1]) for l in pg['corpo'] if (m := importar.MARCADOR.match(l[4]))]
    return achados


def alternativas(texto, letras):
    return [m[1] for m in re.finditer(r'^([' + letras + r'])(?:[ \t]+|$)', texto, re.M)][-len(letras):]


@unittest.skipUnless(caderno('fuvest-2026-V1').exists(), 'cadernos das bancas ausentes na cópia do cofre')
class Bancas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.pasta = Path(cls.tmp.name)
        cls.lotes = {}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def recortar(self, stem, *numeros):
        banca, ano, _ = formatos.identificar(caderno(stem))
        chave = (stem, numeros)
        if chave not in self.lotes:
            self.lotes[chave] = {q['n']: q for q in importar.recortar(caderno(stem), f'{banca}-{ano}', self.pasta, set(numeros))}
        return self.lotes[chave]

    def test_nome_do_arquivo(self):
        ident = importar.identificar(Path('fuvest-2026-V1.pdf'))
        self.assertEqual((tuple(ident), ident.prova), ((2026, 1, 'V1'), 'fuvest'))
        self.assertEqual(formatos.identificar(Path('unicamp-2026-QX.pdf')), ('unicamp', 2026, 'QX'))
        enem = importar.identificar(Path('2024_PV_impresso_D1_CD1.pdf'))
        self.assertEqual((tuple(enem), enem.prova), ((2024, 1, 1), 'enem'))
        self.assertIsNone(formatos.identificar(Path('fuvest-2026-V1-gabarito.pdf')))

    def test_numero_de_questoes_por_edicao(self):
        for banca, stems in EDICOES.items():
            for stem in stems:
                with self.subTest(stem=stem):
                    meta = json.loads(caderno(stem).with_suffix('.json').read_text())
                    self.assertEqual(sorted(set(numeros_marcados(caderno(stem)))), list(range(1, meta['questoes'] + 1)))

    def test_fuvest_texto_comum_e_simbolo_de_espaco(self):
        q = self.recortar('fuvest-2026-V1', 1, 2, 5)
        self.assertEqual(q[1]['grupo'], 'fuvest-2026-V1:Q01a02')
        self.assertEqual(q[1]['texto_comum'], q[2]['texto_comum'])
        self.assertIn('Maria Bethânia', q[1]['texto_comum'])
        for n in (1, 2, 5):
            self.assertNotIn('¬', q[n]['texto'] + q[n]['texto_comum'])
            self.assertEqual(alternativas(q[n]['texto'], 'ABCDE'), list('ABCDE'))
        self.assertIn('Mas, embora me encha de orgulho', q[1]['texto'])

    def test_fuvest_alternativas_graficas_com_a_figura_inteira(self):
        from PIL import Image
        q = self.recortar('fuvest-2026-V1', 1, 2, 5)[5]
        figuras = re.findall(r'^[A-E] !\[\[([^]]+)\]\]', q['texto'], re.M)
        self.assertEqual(len(figuras), 5)
        for f in figuras:  # a tabela inteira (cerca de 95 pt de altura), não só a metade abaixo da letra
            with Image.open(self.pasta / f) as img:
                self.assertGreater(img.height, 230)
        self.assertIn('bingo das ligações químicas', q['texto'])

    def test_fuvest_quadro_depois_das_alternativas_e_enunciado_inteiro(self):
        q = self.recortar('fuvest-2024-V', 13, 26)
        self.assertIn('Matrizes podem ser usadas', q[13]['texto'])
        self.assertEqual(alternativas(q[13]['texto'], 'ABCDE'), list('ABCDE'))
        self.assertIn('temperatura de cor', q[26]['texto'])  # letras D e E na outra coluna
        self.assertEqual(alternativas(q[26]['texto'], 'ABCDE'), list('ABCDE'))

    def test_unicamp_so_quatro_alternativas(self):
        q = self.recortar('unicamp-2026-QX', 1, 3)
        for n in (1, 3):
            self.assertTrue(q[n]['completa'])
            self.assertEqual(alternativas(q[n]['texto'], 'ABCD'), list('ABCD'))
            self.assertIsNone(re.search(r'^E\s', q[n]['texto'], re.M))
        self.assertIn('injustiça de um personagem', q[3]['texto'])

    def test_unicamp_texto_de_uma_questao_vai_no_enunciado(self):
        q = self.recortar('unicamp-2025-QZ', 18, 19)
        self.assertEqual(q[18]['grupo'], q[19]['grupo'])
        self.assertIn('Para responder questão 19', q[19]['texto'])
        self.assertNotIn('Para responder questão 19', q[18]['texto'])

    def test_vunesp_figuras_nas_alternativas_e_tarja(self):
        q = self.recortar('unesp-2025-V1', 15)[15]
        self.assertIn('Uma obra representativa do movimento', q['texto'])
        self.assertEqual(len(re.findall(r'^[A-E] !\[\[', q['texto'], re.M)), 5)
        f = self.recortar('famerp-2025-V1', 2, 9)
        self.assertEqual(f[2]['imagens'], [])  # a tarja "QUESTÃO 02" não é mídia
        self.assertEqual(len(f[9]['imagens']), 1)  # a linha sublinhada vai inteira
        self.assertNotIn('não obstante o ceticismo', f[9]['texto'])

    def test_unesp_texto_comum_em_varias_linhas(self):
        q = self.recortar('unesp-2026-V1', 1, 5, 7)
        self.assertEqual(q[1]['grupo'], 'unesp-2026-V1:Q01a05')
        self.assertEqual(q[5]['grupo'], 'unesp-2026-V1:Q01a05')
        self.assertTrue(q[1]['texto_comum'].startswith('Para responder às questões de 01 a 05'))
        self.assertEqual(q[7]['grupo'], 'unesp-2026-V1:Q07a11')

    def test_gabarito_oficial(self):
        pdf = caderno('fuvest-2024-V')
        meta = json.loads(pdf.with_suffix('.json').read_text())
        respostas, duvidas = formatos.conferir_gabarito(meta, pdf.with_name(pdf.stem + '-gabarito.pdf'), 'fuvest', 'V', 'ABCDE')
        self.assertEqual(list(duvidas), [48])
        self.assertIsNone(respostas[48])
        pdf = caderno('unicamp-2025-QZ')
        meta = json.loads(pdf.with_suffix('.json').read_text())
        respostas, duvidas = formatos.conferir_gabarito(meta, pdf.with_name(pdf.stem + '-gabarito.pdf'), 'unicamp', 'QZ', 'ABCD')
        self.assertEqual((respostas[53], duvidas), ('Anulada', {}))
        self.assertEqual(len(respostas), 72)

    def test_grupo_sem_questao_fora_do_ar(self):
        qs = [{'n': n, 'grupo': 'x-2026-V1:Q05a08'} for n in range(5, 9)]
        self.assertEqual(formatos.grupos_no_ar(qs, {6}), {7: 'x-2026-V1:Q07a08', 8: 'x-2026-V1:Q07a08'})
        self.assertEqual(formatos.grupos_no_ar(qs, set()), {n: 'x-2026-V1:Q05a08' for n in range(5, 9)})


if __name__ == '__main__':
    unittest.main()
