"""Repara a camada de texto de PDFs cujas fontes não trazem o mapa Unicode completo.

Caso real: os cadernos do Enem 2021 usam subconjuntos da Arial com glifos chamados `g70`, `g82`...
e um ToUnicode que só cobre os glifos com nome. O pdftotext devolve lixo nesses trechos.

Como repara, sem OCR, rede ou modelo:
1. Para cada glifo `gNN`, desenha o contorno (com as sub-rotinas expandidas) e procura um glifo com nome
   padrão e o mesmo desenho, na mesma fonte ou em outra fonte de mesmo nome no documento.
2. Sem par de desenho, usa a ordem padrão de glifos do Macintosh, mas só nas faixas conferidas
   (letras, algarismos, pontuação básica e letras acentuadas do português).
3. O que sobra vira U+FFFD; a questão com esse caractere vai para revisão e não entra no ar.
O arquivo original não muda: a cópia reparada vai para a pasta indicada. Dominique-Oliveira-Claude🤖🧡, 14/11/2026.
"""
import hashlib
import io
import re
from pathlib import Path

import fitz

try:
    from fontTools import agl
    from fontTools.cffLib import CFFFontSet
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.ttLib.standardGlyphOrder import standardGlyphOrder
except ImportError:  # sem fontTools, nenhuma prova precisa de reparo pode ser lida
    agl = None

VERSAO_REPARO = 1
GLIFO_NUMERADO = re.compile(r'g(\d+)$')
# Ordem conferida contra o desenho de 110 glifos dos cadernos de 2021 (14/11/2026): até o 171 a Arial
# segue a ordem padrão do Macintosh; do 173 ao 256 está deslocada em um (173 = Atilde, 179 = aspas abertas).
# (início, fim, deslocamento). Fora dessas faixas, só o desenho decide.
FAIXAS_CONFERIDAS = [(3, 171, 0), (173, 256, 1)]
SUBSTITUTO = '�'


def _mapa_existente(doc, xref):
    """Códigos que o ToUnicode da fonte já traduz (bfchar e bfrange)."""
    tu = doc.xref_get_key(xref, 'ToUnicode')
    if tu[0] != 'xref':
        return {}
    texto = doc.xref_stream(int(tu[1].split()[0])).decode('latin1')
    mapa = {}
    for bloco in re.findall(r'beginbfchar(.*?)endbfchar', texto, re.S):
        for a, u in re.findall(r'<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>', bloco):
            mapa[int(a, 16)] = bytes.fromhex(u).decode('utf-16-be', 'replace')
    for bloco in re.findall(r'beginbfrange(.*?)endbfrange', texto, re.S):
        for a, b, u in re.findall(r'<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>', bloco):
            for i in range(int(a, 16), int(b, 16) + 1):
                mapa[i] = chr(int(u, 16) + i - int(a, 16))
    return mapa


def _codigos_numerados(diferencas):
    codigo = None
    for tok in re.findall(r'\d+|/[^\s/\[\]]+', diferencas):
        if tok[0] != '/':
            codigo = int(tok)
            continue
        yield codigo, tok[1:]
        codigo += 1


def _fontes_quebradas(doc):
    """Fontes simples com glifos `gNN` que o ToUnicode existente não traduz."""
    for x, dif in _fontes_com_numerados(doc):
        existente = _mapa_existente(doc, x)
        if any(GLIFO_NUMERADO.match(n) and c not in existente for c, n in _codigos_numerados(dif)):
            yield x, dif


def _fontes_com_numerados(doc):
    """Fontes simples com Differences contendo glifos `gNN`."""
    for x in range(1, doc.xref_length()):
        try:
            if doc.xref_get_key(x, 'Type')[1] != '/Font':
                continue
            enc = doc.xref_get_key(x, 'Encoding')
        except Exception:
            continue
        if enc[0] != 'xref':
            continue
        dif = doc.xref_get_key(int(enc[1].split()[0]), 'Differences')
        if dif[0] == 'array' and re.search(r'/g\d+\b', dif[1]):
            yield x, dif[1]


def precisa_reparo(pdf):
    with fitz.open(pdf) as doc:
        return any(True for _ in _fontes_quebradas(doc))


def _desenhos(doc, xref):
    """Nome do glifo -> assinatura do contorno, para uma fonte CFF embutida."""
    _, ext, _, dados = doc.extract_font(xref)
    if ext != 'cff' or not dados or agl is None:
        return {}
    conjunto = CFFFontSet()
    conjunto.decompile(io.BytesIO(dados), None)
    topo = conjunto[conjunto.fontNames[0]]
    saida = {}
    for nome in topo.charset:
        caneta = RecordingPen()
        try:
            topo.CharStrings[nome].draw(caneta)
        except Exception:
            continue
        if caneta.value:
            saida[nome] = hashlib.sha256(repr(caneta.value).encode()).hexdigest()
    return saida


def _unicode_do_nome(nome):
    if agl is None or GLIFO_NUMERADO.match(nome):
        return None
    texto = agl.toUnicode(nome)
    return texto or None


def _cmap(mapa):
    linhas = [f'<{c:02x}> <{"".join(f"{ord(ch):04x}" for ch in u)}>' for c, u in sorted(mapa.items())]
    corpo = ('/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) '
             '/Ordering (UCS) /Supplement 0 >> def /CMapName /Reparo-PU def /CMapType 2 def\n'
             '1 begincodespacerange <00> <ff> endcodespacerange\n')
    for i in range(0, len(linhas), 100):
        bloco = linhas[i:i + 100]
        corpo += f'{len(bloco)} beginbfchar\n' + '\n'.join(bloco) + '\nendbfchar\n'
    return (corpo + 'endcmap CMapName currentdict /CMap defineresource pop end end').encode()


def reparar(pdf, pasta):
    """Devolve (caminho a ler, relatório). Sem fonte quebrada, devolve o próprio PDF."""
    pdf = Path(pdf)
    doc = fitz.open(pdf)
    try:
        quebradas = list(_fontes_quebradas(doc))
        if not quebradas:
            return pdf, {'reparo': False}
        if agl is None:
            raise ValueError('Esta prova precisa de reparo de texto e o fontTools não está instalado')
        # Desenhos de glifos com nome, por fonte de mesmo nome, em todo o documento.
        por_base, desenhos = {}, {}
        for x, _ in quebradas:
            base = re.sub(r'^/?[A-Z]{6}\+', '', doc.xref_get_key(x, 'BaseFont')[1])
            desenhos[x] = _desenhos(doc, x)
            alvo = por_base.setdefault(base, {})
            for nome, assinatura in desenhos[x].items():
                u = _unicode_do_nome(nome)
                if u:
                    alvo.setdefault(assinatura, u)
        relatorio = {'reparo': True, 'versao': VERSAO_REPARO, 'fontes': 0, 'pelo_desenho': 0,
                     'pela_ordem': 0, 'desconhecidos': 0}
        for x, diferencas in quebradas:
            base = re.sub(r'^/?[A-Z]{6}\+', '', doc.xref_get_key(x, 'BaseFont')[1])
            # O que a fonte já traduz fica como está; só se completa o que falta.
            mapa = _mapa_existente(doc, x)
            # A ordem padrão foi conferida só na Arial; nas outras (símbolos), só o desenho decide.
            arial = base.lower().startswith('arial')
            for codigo, nome in _codigos_numerados(diferencas):
                if codigo in mapa:
                    continue
                u = _unicode_do_nome(nome)
                if not u and GLIFO_NUMERADO.match(nome):
                    assinatura = desenhos[x].get(nome)
                    u = por_base[base].get(assinatura) if assinatura else None
                    if u:
                        relatorio['pelo_desenho'] += 1
                    else:
                        k = int(GLIFO_NUMERADO.match(nome)[1])
                        faixa = arial and next((f for f in FAIXAS_CONFERIDAS if f[0] <= k <= f[1]), None)
                        if faixa:
                            u = _unicode_do_nome(standardGlyphOrder[k + faixa[2]])
                            relatorio['pela_ordem'] += 1
                if not u and arial:
                    u = SUBSTITUTO
                    relatorio['desconhecidos'] += 1
                if u:
                    mapa[codigo] = u
            novo = doc.get_new_xref()
            doc.update_object(novo, '<<>>')
            doc.update_stream(novo, _cmap(mapa))
            doc.xref_set_key(x, 'ToUnicode', f'{novo} 0 R')
            relatorio['fontes'] += 1
        pasta = Path(pasta)
        pasta.mkdir(parents=True, exist_ok=True)
        saida = pasta / (pdf.stem + '-texto-reparado.pdf')
        doc.save(saida, garbage=0)
        return saida, relatorio
    finally:
        doc.close()
