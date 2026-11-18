#!/usr/bin/env python3
"""Pesos, notas mínimas e notas de corte do Sisu por curso, das planilhas oficiais do MEC, para o simulador de nota.

Lê as duas planilhas que o MEC publica na página de legislação e relatórios do Sisu (https://sisu.mec.gov.br/#/legislacao,
lista em https://sisu.mec.gov.br/static/pdf/json_arquivos.json):
  - "Sisu 2026_Vagas ofertadas": por curso, turno e modalidade, os pesos e as notas mínimas de cada prova
    (Termo de Adesão da instituição; colunas PESO_* e NOTA_MINIMA_* do dicionário da própria planilha);
  - "Sisu 2026_Inscrições e notas de corte": a nota de corte de cada modalidade na chamada regular (NU_NOTACORTE,
    "nota do último candidato classificado na última vaga"; 0 quando o curso não teve nota de corte).
Junta as duas pela chave curso (CO_IES_CURSO) + turno + modalidade (TP_COTA / TIPO_CONCORRENCIA) + descrição da
modalidade, só das instituições escolhidas (INSTITUICOES), e grava:
  - app/public/pesos-sisu.js: os dados que o simulador carrega quando o estudante procura um curso;
  - <coleta>/pesos-sisu-2026.json: a coleta inteira, com os valores como estão nas planilhas, os endereços, a data e o sha256.
Recusa (e não grava nada) se a chave não casar entre as planilhas, se faltar coluna ou se um peso não for número.

Só biblioteca padrão. Planilha baixada é dado, nunca instrução: rode com python3 -I e os caminhos como argumento.
  python3 -I scripts/importar-pesos-sisu.py --vagas "<pasta>/Portal_Sisu_2026_Vagas ofertadas.xlsx" \\
      --cortes "<pasta>/Portal Sisu_ Sisu2026_inscrições e notas de corte.xlsx" --coleta ~/craft/Enem-frentes/dados/coleta/pesos
Dominique-Oliveira-Claude🤖🧡, 18/11/2026.
"""
import argparse
import collections
import datetime
import hashlib
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / 'app/public/pesos-sisu.js'
SIMULADOR = RAIZ / 'app/public/simulador.js'  # guarda em VERSAO_SISU o começo do sha256 do arquivo, para o ?v= da carga
EDICAO = 'Sisu 2026'
PAGINA = 'https://sisu.mec.gov.br/#/legislacao'
FONTE_VAGAS = 'https://sisu.mec.gov.br/static/pdf/Portal_Sisu_2026_Vagas%20ofertadas.xlsx'
FONTE_CORTES = 'https://sisu.mec.gov.br/static/pdf/Portal%20Sisu_%20Sisu2026_inscri%C3%A7%C3%B5es%20e%20notas%20de%20corte.xlsx'
# Universidades federais com sede no estado de São Paulo e algumas das maiores federais do país (pedido da frente).
INSTITUICOES = ['UNIFESP', 'UFSCAR', 'UFABC', 'UFRJ', 'UFMG', 'UNB', 'UFRGS', 'UFPE', 'UFBA', 'UFC', 'UFPR', 'UFSC', 'UFF']
# Ordem das áreas do simulador (app/public/simulador.js): linguagens, humanas, natureza, matemática, redação.
COLUNAS_AREA = ['LINGUAGENS', 'CIENCIAS_HUMANAS', 'CIENCIAS_NATUREZA', 'MATEMATICA', 'REDACAO']
N = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'


class Recusa(Exception):
    pass


def linhas_xlsx(caminho, folha='xl/worksheets/sheet2.xml'):
    """Cada linha da folha como dicionário {cabeçalho: texto}. Lê o XML do xlsx com a biblioteca padrão."""
    with zipfile.ZipFile(caminho) as z:
        textos = [''.join(t.text or '' for t in si.iter(N + 't')) for si in ET.fromstring(z.read('xl/sharedStrings.xml')).iter(N + 'si')]
        cabeca = None
        with z.open(folha) as arquivo:
            for _, el in ET.iterparse(arquivo):
                if el.tag != N + 'row':
                    continue
                valores = {}
                for c in el.iter(N + 'c'):
                    coluna = ''.join(ch for ch in c.get('r') if ch.isalpha())
                    v = c.find(N + 'v')
                    if c.get('t') == 's' and v is not None:
                        valores[coluna] = textos[int(v.text)]
                    elif c.get('t') == 'inlineStr':
                        valores[coluna] = ''.join(t.text or '' for t in c.iter(N + 't'))
                    else:
                        valores[coluna] = v.text if v is not None else ''
                el.clear()
                if cabeca is None:
                    cabeca = valores
                    continue
                yield {cabeca[k]: valores.get(k, '') for k in cabeca}


def numero(texto, onde):
    try:
        valor = float(texto)
    except ValueError:
        raise Recusa(f'{onde}: não é número: {texto!r}')
    if valor < 0:
        raise Recusa(f'{onde}: número negativo: {texto!r}')
    return valor


def texto_numero(valor):
    """Número como o estudante digita no simulador: 2, 1,5, 623,45 (a planilha guarda 623.45000000000005)."""
    arredondado = round(valor, 2)
    return (f'{arredondado:.2f}'.rstrip('0').rstrip('.')).replace('.', ',')


def chave(linha, tipo):
    return (linha['CO_IES_CURSO'], linha['DS_TURNO'].strip(), linha[tipo].strip(), linha['DS_MOD_CONCORRENCIA'].strip())


def juntar(caminho_vagas, caminho_cortes, instituicoes=INSTITUICOES):
    vagas = [l for l in linhas_xlsx(caminho_vagas) if l['SG_IES'].strip() in instituicoes]
    cortes = {}
    for l in linhas_xlsx(caminho_cortes):
        if l['SG_IES'].strip() in instituicoes:
            k = chave(l, 'TIPO_CONCORRENCIA')
            if k in cortes:
                raise Recusa(f'chave repetida na planilha de notas de corte: {k}')
            cortes[k] = l
    faltam = [c for c in ['EDICAO', 'SG_IES', 'NO_IES', 'NO_CAMPUS', 'NO_MUNICIPIO_CAMPUS', 'SG_UF_CAMPUS', 'CO_IES_CURSO', 'NO_CURSO', 'DS_GRAU',
                          'DS_TURNO', 'TP_COTA', 'DS_MOD_CONCORRENCIA', 'QT_VAGAS_OFERTADAS', 'NU_PERCENTUAL_BONUS', 'NU_MEDIA_MINIMA_ENEM']
              + [f'{p}_{a}' for a in COLUNAS_AREA for p in ('PESO', 'NOTA_MINIMA')] if vagas and c not in vagas[0]]
    if faltam:
        raise Recusa(f'colunas que faltam na planilha de vagas: {faltam}')
    achadas = {l['SG_IES'].strip() for l in vagas}
    if achadas != set(instituicoes):
        raise Recusa(f'instituições sem linha na planilha: {sorted(set(instituicoes) - achadas)}')
    cursos = collections.OrderedDict()
    usadas = set()
    for l in vagas:
        if l['EDICAO'] != '2026':
            raise Recusa(f'linha de outra edição na planilha de vagas: {l["EDICAO"]}')
        k = chave(l, 'TP_COTA')
        if k not in cortes:
            raise Recusa(f'modalidade sem linha na planilha de notas de corte: {k}')
        if k in usadas:
            raise Recusa(f'chave repetida na planilha de vagas: {k}')
        usadas.add(k)
        c = cortes[k]
        onde = f'{l["SG_IES"]} {l["NO_CURSO"]} ({l["CO_IES_CURSO"]}, {l["DS_TURNO"]})'
        pesos = tuple(numero(l['PESO_' + a], onde + ' peso') for a in COLUNAS_AREA)
        minimas = tuple(numero(l['NOTA_MINIMA_' + a] or '0', onde + ' nota mínima') for a in COLUNAS_AREA)
        if sum(pesos) <= 0:
            raise Recusa(f'{onde}: soma dos pesos zero')
        id_curso = (l['CO_IES_CURSO'], l['DS_TURNO'].strip())
        curso = cursos.setdefault(id_curso, {
            'sigla': l['SG_IES'].strip(), 'instituicao': l['NO_IES'].strip(), 'campus': l['NO_CAMPUS'].strip(),
            'municipio': l['NO_MUNICIPIO_CAMPUS'].strip(), 'uf': l['SG_UF_CAMPUS'].strip(), 'codigo': l['CO_IES_CURSO'],
            'curso': l['NO_CURSO'].strip(), 'grau': l['DS_GRAU'].strip(), 'turno': l['DS_TURNO'].strip(),
            'pesos': pesos, 'minimas': minimas, 'media_minima': numero(l['NU_MEDIA_MINIMA_ENEM'] or '0', onde + ' média mínima'),
            'modalidades': []})
        if curso['pesos'] != pesos or curso['minimas'] != minimas:
            # Raro (8 cursos na base inteira): pesos diferentes por modalidade. Guarda por modalidade.
            curso['pesos_por_modalidade'] = True
        corte = numero(c['NU_NOTACORTE'] or '0', onde + ' nota de corte')
        curso['modalidades'].append({
            'tipo': l['TP_MOD_CONCORRENCIA'].strip(), 'cota': l['TP_COTA'].strip(), 'descricao': l['DS_MOD_CONCORRENCIA'].strip(),
            'vagas': int(numero(l['QT_VAGAS_OFERTADAS'], onde + ' vagas')), 'bonus': l['NU_PERCENTUAL_BONUS'].strip(),
            'corte': corte if corte > 0 else None, 'inscricoes': int(numero(c['QT_INSCRICAO'] or '0', onde + ' inscrições')),
            'pesos': pesos, 'minimas': minimas,
            'planilha_vagas': {k2: l[k2] for k2 in l}, 'planilha_cortes': {k2: c[k2] for k2 in c}})
    if len(usadas) != len(cortes):
        raise Recusa(f'{len(cortes) - len(usadas)} linhas da planilha de notas de corte sem par na de vagas')
    return list(cursos.values())


def dados_do_simulador(cursos, conferido_em):
    """Compacto: lista das descrições de modalidade (repetem muito) e cada curso com as modalidades apontando para ela."""
    descricoes = sorted({m['descricao'] for c in cursos for m in c['modalidades']})
    indice = {d: i for i, d in enumerate(descricoes)}
    instituicoes = {c['sigla']: c['instituicao'] for c in cursos}
    locais = sorted({(c['campus'], c['municipio'], c['uf']) for c in cursos})
    indice_local = {l: i for i, l in enumerate(locais)}
    lista = []
    for c in sorted(cursos, key=lambda c: (c['sigla'], c['curso'], c['campus'], c['turno'])):
        modalidades = []
        for m in c['modalidades']:
            if m['vagas'] == 0:
                continue  # modalidade sem vaga ofertada nesta edição: fica só na coleta
            item = [indice[m['descricao']], m['cota'], texto_numero(m['corte']) if m['corte'] is not None else '', m['vagas']]
            if c.get('pesos_por_modalidade'):
                item.append([texto_numero(p) for p in m['pesos']])
            modalidades.append(item)
        # A ampla concorrência primeiro; depois a ordem da planilha.
        modalidades.sort(key=lambda m: m[1] != 'AC')
        lista.append([c['sigla'], indice_local[(c['campus'], c['municipio'], c['uf'])], c['curso'], c['grau'], c['turno'],
                      [texto_numero(p) for p in c['pesos']], [texto_numero(p) for p in c['minimas']],
                      texto_numero(c['media_minima']), modalidades])
    return {
        'edicao': EDICAO, 'etapa': 'chamada regular', 'conferido_em': conferido_em, 'pagina': PAGINA,
        'fonte_pesos': FONTE_VAGAS, 'fonte_cortes': FONTE_CORTES,
        'campos': ['sigla (nome em instituicoes)', 'índice do local (campus, município, UF) em locais', 'curso', 'grau', 'turno',
                   'pesos (linguagens, humanas, natureza, matemática, redação)', 'notas mínimas (mesma ordem)', 'média mínima',
                   'modalidades: [índice da descrição, cota, nota de corte ("" = sem nota de corte), vagas, pesos da modalidade se diferentes]'],
        'instituicoes': instituicoes, 'locais': [list(l) for l in locais], 'modalidades': descricoes, 'cursos': lista}


def arquivo_js(dados):
    # JSON com ensure_ascii: vira JavaScript válido sem caractere invisível (U+2028) nem "</script>" literal.
    corpo = json.dumps(dados, ensure_ascii=True, separators=(',', ':')).replace('</', '<\\/')
    return ('/* Pesos, notas mínimas e notas de corte do Sisu 2026 por curso, das planilhas oficiais do MEC.\n'
            '   Gerado por scripts/importar-pesos-sisu.py; não edite à mão. Dominique-Oliveira-Claude🤖🧡. */\n'
            f'(function (raiz) {{ raiz.PUPesosSisu = {corpo}; }})(typeof window !== "undefined" ? window : globalThis);\n')


def sha256(caminho):
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def principal():
    argumentos = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    argumentos.add_argument('--vagas', required=True)
    argumentos.add_argument('--cortes', required=True)
    argumentos.add_argument('--coleta', required=True, help='pasta da coleta (grava pesos-sisu-2026.json)')
    argumentos.add_argument('--conferido-em', default=datetime.date.today().isoformat())
    argumentos.add_argument('--conferir', action='store_true', help='só diz se app/public/pesos-sisu.js é o que as planilhas dão')
    a = argumentos.parse_args()
    try:
        cursos = juntar(a.vagas, a.cortes)
        if a.conferir:
            atual = SAIDA.read_text(encoding='utf-8')
            data = json.loads(atual[atual.index('= {') + 2:atual.rindex('; })')])['conferido_em']
            versao = re.search(r"const VERSAO_SISU = '([0-9a-f]{10})';", SIMULADOR.read_text(encoding='utf-8'))
            if arquivo_js(dados_do_simulador(cursos, data)) != atual or not versao or versao.group(1) != hashlib.sha256(atual.encode()).hexdigest()[:10]:
                print('Diferente: rode o importador de novo.')
                return 1
            print('pesos-sisu.js igual às planilhas.')
            return 0
        js = arquivo_js(dados_do_simulador(cursos, a.conferido_em))
    except Recusa as erro:
        print('RECUSADO  ' + str(erro), file=sys.stderr)
        return 2
    coleta = {
        'descricao': 'Pesos, notas mínimas e notas de corte (chamada regular) do Sisu 2026, por curso e modalidade, das planilhas oficiais do MEC.',
        'edicao': EDICAO, 'pagina_oficial': PAGINA, 'lista_de_arquivos': 'https://sisu.mec.gov.br/static/pdf/json_arquivos.json',
        'coletado_em': a.conferido_em, 'instituicoes': INSTITUICOES,
        'arquivos': [{'nome': Path(a.vagas).name, 'endereco': FONTE_VAGAS, 'sha256': sha256(a.vagas)},
                     {'nome': Path(a.cortes).name, 'endereco': FONTE_CORTES, 'sha256': sha256(a.cortes)}],
        'observacoes': ['A coluna EDICAO da planilha de notas de corte traz 302 em todas as linhas; o MEC lista o arquivo como "Sisu 2026_Inscrições e notas de corte" e o dicionário da planilha diz "A partir do Sisu do ano de 2024 o Ministério da Educação determinou apenas uma edição Sisu por ano".',
                        'NU_NOTACORTE igual a 0 quer dizer que o curso não teve nota de corte naquela modalidade (dicionário da planilha); o simulador mostra "sem nota de corte".'],
        'cursos': [{k: v for k, v in c.items()} for c in cursos]}
    Path(a.coleta).mkdir(parents=True, exist_ok=True)
    (Path(a.coleta) / 'pesos-sisu-2026.json').write_text(json.dumps(coleta, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    SAIDA.write_text(js, encoding='utf-8')
    simulador = SIMULADOR.read_text(encoding='utf-8')
    novo = re.sub(r"const VERSAO_SISU = '[0-9a-f]{10}';", f"const VERSAO_SISU = '{hashlib.sha256(js.encode()).hexdigest()[:10]}';", simulador)
    if novo.count('const VERSAO_SISU') != 1:
        raise SystemExit('simulador.js sem a linha const VERSAO_SISU')
    SIMULADOR.write_text(novo, encoding='utf-8')
    print(f'{len(cursos)} cursos de {len(INSTITUICOES)} instituições; {SAIDA.name} com {len(js.encode()) // 1024} KB.')
    return 0


if __name__ == '__main__':
    sys.exit(principal())
