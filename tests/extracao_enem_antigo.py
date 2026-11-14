"""Regressões do extrator nos cadernos do Enem 2021 a 2023, com os PDFs oficiais da pasta de provas.

Rodar com a cópia do cofre: PU_COFRE_VESTIBULAR=<cópia> .venv-extracao/bin/python -I tests/extracao_enem_antigo.py
Dominique-Oliveira-Claude🤖🧡, 14/11/2026.
"""
import re
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'ferramentas/importar-prova'))
import importar  # noqa: E402
import reparo_texto  # noqa: E402


def caderno(ano, dia):
    return importar.PROVAS / f'{ano}_PV_impresso_D{dia}_CD{1 if dia == 1 else 7}.pdf'


@unittest.skipUnless(caderno(2021, 1).exists(), 'cadernos de 2021 a 2023 ausentes na pasta de provas')
class EnemAntigo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.pasta = Path(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_reparo_do_texto_de_2021(self):
        reparado, relatorio = reparo_texto.reparar(caderno(2021, 1), self.pasta / 'reparo')
        self.assertTrue(relatorio['reparo'])
        self.assertGreater(relatorio['pelo_desenho'] + relatorio['pela_ordem'], 100)
        texto = importar.subprocess.run(['pdftotext', '-f', '4', '-l', '4', str(reparado), '-'], capture_output=True, text=True).stdout
        self.assertIn('Federico García Lorca', texto)
        self.assertNotIn(reparo_texto.SUBSTITUTO, texto)
        # O original não muda e um PDF sem fonte quebrada não é copiado.
        self.assertNotEqual(reparado, caderno(2021, 1))
        self.assertEqual(reparo_texto.reparar(caderno(2023, 1), self.pasta / 'outro')[0], caderno(2023, 1))

    def test_rodape_sem_faixa_nao_corta_a_alternativa_e(self):
        q = importar.recortar(caderno(2021, 1), 2021, self.pasta / 'img', {17})[0]
        self.assertTrue(q['completa'])
        self.assertIn('E atitude contestadora', q['texto'])
        # Linha justificada partida pelo pdftotext volta a ser uma linha só.
        self.assertIn('depreciação de um esporte associado à marginalidade', re.sub(r'\s+', ' ', q['texto']))

    def test_letra_separada_vira_alternativa_de_texto(self):
        q = importar.recortar(caderno(2022, 1), 2022, self.pasta / 'img', {1})[0]
        self.assertTrue(q['completa'])
        self.assertNotIn('![[', q['texto'])
        self.assertRegex(q['texto'], r'(?m)^E \S')

    def test_cadernos_completos(self):
        for ano in (2021, 2022, 2023):
            pdf, _ = importar.fonte_legivel(caderno(ano, 1))
            paginas = importar.ler_paginas(pdf)
            numeros = set()
            for pg in paginas:
                importar.preparar_pagina(pg)
                numeros |= {int(m[1]) for l in pg['corpo'] if (m := importar.MARCADOR.match(l[4]))}
            self.assertTrue(set(range(1, 91)) <= numeros, (ano, sorted(set(range(1, 91)) - numeros)))


if __name__ == '__main__':
    unittest.main()
