#!/usr/bin/env python3
"""Duração da sessão: os documentos dizem o mesmo que o código (achado N7 da revisão de 14/11/2026).

Lê em app/servidor.py a validade gravada na tabela sessoes (time.time() + N * 86400) e o Max-Age do cookie, confere que
os dois batem, e procura em docs/*.md toda frase que fala da duração da sessão ou do cookie em horas ou dias. Cada uma
precisa trazer a duração do código ("30 dias"); registro antigo pode citar o valor da época desde que diga o atual.
PU_DOCS aponta outra pasta de documentos (ex.: a da árvore principal, só leitura).
Uso: python3 tests/sessao_documentada.py
Dominique-Oliveira-Claude🤖🧡, 17/11/2026.
"""
import os
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DOCS = Path(os.environ.get('PU_DOCS') or RAIZ / 'docs')
FRASE_DE_DURACAO = re.compile(r'(sess[ãa]o|sess[õo]es|cookie)[^.;\n]{0,90}?\b\d+\s*(horas?|dias?)\b|\b\d+\s*(horas?|dias?)\b[^.;\n]{0,40}?(sess[ãa]o|cookie)', re.I)


def dias_no_codigo():
    codigo = (RAIZ / 'app/servidor.py').read_text(encoding='utf-8')
    gravado = re.search(r"INSERT INTO sessoes\(token,conta,expira,dispositivo\)[^\n]*time\.time\(\) \+ (\d+) \* 86400", codigo)
    cookie = re.search(r'Max-Age=(\d+)\'', codigo)
    assert gravado and cookie, 'não achei a validade da sessão em app/servidor.py'
    return int(gravado[1]), int(cookie[1])


def frases_de_duracao(pasta):
    for arquivo in sorted(pasta.glob('*.md')):
        for numero, linha in enumerate(arquivo.read_text(encoding='utf-8').splitlines(), 1):
            for frase in re.split(r'(?<=[.;])\s', linha):
                if FRASE_DE_DURACAO.search(frase):
                    yield arquivo.name, numero, frase.strip()


class SessaoDocumentada(unittest.TestCase):
    def test_documentos_dizem_a_duracao_do_codigo(self):
        dias, max_age = dias_no_codigo()
        self.assertEqual(max_age, dias * 86400, 'cookie e tabela sessoes com validades diferentes')
        esperado = f'{dias} dias'
        achadas = list(frases_de_duracao(DOCS))
        self.assertTrue(achadas, f'nenhum documento em {DOCS} diz quanto dura a sessão')
        erradas = [f'{nome}:{numero}: {frase[:160]}' for nome, numero, frase in achadas if esperado not in frase]
        self.assertEqual(erradas, [], f'documento com duração de sessão diferente do código ({esperado})')


if __name__ == '__main__':
    unittest.main(verbosity=1)
