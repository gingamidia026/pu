#!/usr/bin/env python3
"""Estatística oficial de marcação por questão do Enem 2024 e 2025, a partir dos microdados do Inep.

Dominique-Oliveira-Claude🤖🧡, 17/11/2026. Sem IA, sem rede. Lê o catálogo do PU, as frequências por caderno
(`frequencias_<ano>.csv`, feitas por `frequencias.py` direto de RESULTADOS_<ano>.csv) e `ITENS_PROVA_<ano>.csv`,
casa cada questão do PU com o CO_ITEM do Inep e grava `estatisticas-inep.json` ao lado do catálogo.

O arquivo de saída entrega a resposta (frequência por alternativa e percentual de acerto): fica fora do git
(GitHub Pages publica qualquer arquivo do repositório) e só o servidor o lê, depois de o aluno responder.

Regra de casamento (docs/ESTATISTICAS-INEP.md):
- caderno de referência do PU: dia 1 caderno 1 e dia 2 caderno 7, ambos AZUL na capa do PDF do Inep;
- posição: o número da questão no PDF é o CO_POSICAO do caderno azul (LC 1-45, CH 46-90, CN 91-135, MT 136-180);
- Linguagens 1 a 5: a língua da questão (Inglês = TP_LINGUA 0, Espanhol = 1) escolhe o item;
- prova: o gabarito do item no Inep tem de ser igual ao gabarito guardado pelo PU; se não for, fica indisponível.
Amostra: participantes presentes (TP_PRESENCA = 1) da 1ª aplicação regular, nas quatro cores regulares do dia.

Uso: python3 scripts/estatisticas-inep.py [--inep PASTA] [--catalogo .catalogo/atual.json] [--destino ...] [--conferir]
"""
import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PADRAO_INEP = Path(os.environ.get('PU_MICRODADOS_INEP', Path.home() / 'craft/Enem-frentes/dados/inep'))
PAGINA = 'https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/enem'
LETRAS = 'ABCDE'

# Download registrado em Enem-frentes/estado/estatisticas.md (tamanho igual ao Content-Length do servidor do Inep).
FONTES = {
    2024: {'arquivo': 'https://download.inep.gov.br/microdados/microdados_enem_2024.zip', 'baixadoEm': '2026-11-17',
           'sha256': '69ee52dbcdae61410a7b2c31b776f396f2da30febfc1d2856e9e0ad064c76fb1',
           'aplicacao': '1ª aplicação, 3 e 10/11/2024 (Leia-me Enem 2024)'},
    2025: {'arquivo': 'https://download.inep.gov.br/microdados/microdados_enem_2025.zip', 'baixadoEm': '2026-11-17',
           'sha256': 'b8d3e72cbf387ee08f18d552367005429017d43eea1f6d4b9bafe1d83a116071',
           'aplicacao': '1ª aplicação, 9 e 16/11/2025, sem a aplicação de Belém, Ananindeua e Marituba (Leia-me Enem 2025)'},
}
# Cadernos regulares da 1ª aplicação, pelo Dicionário de Microdados de cada ano (CO_PROVA_<área>): azul primeiro.
# Fora da amostra: ampliada, superampliada, ledor, Libras, atendimento especializado, leitor de tela, reaplicação,
# PPL e, em 2025, BAM (aplicação de Belém, Ananindeua e Marituba, cujos itens não estão em ITENS_PROVA_2025).
REGULARES = {
    2024: {'LC': [(1395, 'AZUL'), (1396, 'AMARELA'), (1397, 'VERDE'), (1398, 'BRANCA')],
           'CH': [(1383, 'AZUL'), (1384, 'AMARELA'), (1385, 'BRANCA'), (1386, 'VERDE')],
           'CN': [(1419, 'AZUL'), (1420, 'AMARELA'), (1421, 'VERDE'), (1422, 'CINZA')],
           'MT': [(1407, 'AZUL'), (1408, 'AMARELA'), (1409, 'VERDE'), (1410, 'CINZA')]},
    2025: {'LC': [(1459, 'AZUL'), (1460, 'AMARELA'), (1461, 'VERDE'), (1462, 'BRANCA')],
           'CH': [(1447, 'AZUL'), (1448, 'AMARELA'), (1449, 'BRANCA'), (1450, 'VERDE')],
           'CN': [(1483, 'AZUL'), (1484, 'AMARELA'), (1485, 'VERDE'), (1486, 'CINZA')],
           'MT': [(1471, 'AZUL'), (1472, 'AMARELA'), (1473, 'VERDE'), (1474, 'CINZA')]},
}
# Caderno do PDF que o PU importou -> cor de referência (capa conferida com pdftotext em 17/11/2026).
CADERNO_PU = {(1, 1): 'AZUL', (2, 7): 'AZUL'}
AREA_PU = {'Linguagens': 'LC', 'Ciências Humanas': 'CH', 'Ciências da Natureza': 'CN', 'Matemática': 'MT'}
FAIXA = {'LC': (1, 45), 'CH': (46, 90), 'CN': (91, 135), 'MT': (136, 180)}
LINGUA = {'Inglês': '0', 'Espanhol': '1'}
NOME_LINGUA = {'0': 'inglês', '1': 'espanhol'}


def ler_csv(caminho, codificacao):
    with open(caminho, encoding=codificacao, newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))


def pct(n, total):
    return round(100 * n / total, 2) if total else None


def carregar_ano(inep, ano):
    """Linhas de frequência e de itens indexadas por (área, caderno, posição, língua)."""
    freq = {}
    for r in ler_csv(inep / f'frequencias_{ano}.csv', 'utf-8'):
        chave = (r['area'], int(r['co_prova']), int(r['posicao']), r['lingua'])
        if chave in freq:
            raise SystemExit(f'Linha repetida em frequencias_{ano}.csv: {chave}')
        freq[chave] = r
    itens = {}
    for r in ler_csv(inep / str(ano) / f'ITENS_PROVA_{ano}.csv', 'latin-1'):
        itens[(r['SG_AREA'], int(r['CO_PROVA']), int(r['CO_POSICAO']), r['TP_LINGUA'])] = r
    return freq, itens


def casar(q, freq, itens, processado):
    """Devolve o registro da questão: validado, com a frequência, ou indisponível, com o motivo."""
    ano, dia, caderno, numero = q['ano'], q['dia'], q['caderno'], q['numero']
    indisponivel = lambda motivo: {'situacao': 'indisponivel', 'motivo': motivo}
    cor = CADERNO_PU.get((dia, caderno))
    if cor is None:
        return indisponivel(f'Caderno {caderno} do dia {dia} sem correspondência conferida com os microdados.')
    area = AREA_PU.get(q.get('area'))
    if area is None or not FAIXA[area][0] <= numero <= FAIXA[area][1]:
        return indisponivel('Área e número da questão não correspondem à numeração do caderno do Inep.')
    lingua = ''
    if area == 'LC' and numero <= 5:
        lingua = LINGUA.get(q.get('materia'))
        if lingua is None:
            return indisponivel('Questão de língua estrangeira sem a língua identificada no PU.')
    regulares = REGULARES[ano][area]
    azul = regulares[0][0]
    linha = freq.get((area, azul, numero, lingua))
    item = itens.get((area, azul, numero, lingua))
    if not linha or not item or linha['cor'] != cor or item['TX_COR'] != cor:
        return indisponivel('Posição sem item no caderno azul dos microdados.')
    co_item = linha['co_item']
    if item['CO_ITEM'] != co_item or item['TX_GABARITO'] != linha['gabarito']:
        return indisponivel('Microdados inconsistentes entre ITENS_PROVA e as frequências.')
    if linha['gabarito'] == 'X':
        return indisponivel('Item anulado pelo Inep.')
    gabarito_pu = LETRAS[q['correta']] if isinstance(q.get('correta'), int) and 0 <= q['correta'] < 5 else None
    if gabarito_pu != linha['gabarito']:
        return indisponivel(f'Gabarito do PU ({gabarito_pu}) diferente do gabarito do item no Inep ({linha["gabarito"]}).')
    # O mesmo item nas quatro cores regulares do dia (ordem diferente, mesmas questões).
    cadernos, soma = [], dict.fromkeys(['n_presentes', 'n_A', 'n_B', 'n_C', 'n_D', 'n_E', 'n_branco', 'n_dupla', 'n_outro'], 0)
    for codigo, cor_regular in regulares:
        achados = [r for (a, c, p, l), r in freq.items() if a == area and c == codigo and l == lingua and r['co_item'] == co_item]
        if len(achados) != 1:
            return indisponivel(f'Item {co_item} não aparece uma vez só no caderno {codigo} ({cor_regular}).')
        r = achados[0]
        if r['cor'] != cor_regular or r['gabarito'] != linha['gabarito']:
            return indisponivel(f'Caderno {codigo} com cor ou gabarito diferente do esperado.')
        cadernos.append({'codigo': codigo, 'cor': cor_regular.lower(), 'posicao': int(r['posicao']), 'amostra': int(r['n_presentes'])})
        for campo in soma:
            soma[campo] += int(r[campo])
    amostra = soma['n_presentes']
    if amostra == 0:
        return indisponivel('Nenhum participante presente nos cadernos regulares.')
    if sum(v for k, v in soma.items() if k != 'n_presentes') != amostra:
        return indisponivel('Soma das marcações diferente da amostra.')
    alternativas = [{'letra': l, 'n': soma['n_' + l], 'pct': pct(soma['n_' + l], amostra)} for l in LETRAS]
    erradas = [a for a in alternativas if a['letra'] != linha['gabarito']]
    fonte = FONTES[ano]
    return {
        'situacao': 'validado', 'ano': ano, 'area': area, 'coItem': int(co_item), 'posicaoAzul': numero,
        'lingua': NOME_LINGUA.get(lingua), 'habilidade': int(item['CO_HABILIDADE']) if item['CO_HABILIDADE'].strip() else None,
        'itemAbandonadoTri': item['IN_ITEM_ABAN'] == '1',
        'amostra': amostra, 'alternativas': alternativas,
        'branco': {'n': soma['n_branco'], 'pct': pct(soma['n_branco'], amostra)},
        'dupla': {'n': soma['n_dupla'], 'pct': pct(soma['n_dupla'], amostra)},
        'outro': {'n': soma['n_outro'], 'pct': pct(soma['n_outro'], amostra)},
        'acerto': pct(soma['n_' + linha['gabarito']], amostra),
        'maisMarcada': max(alternativas, key=lambda a: a['n'])['letra'],
        'erradaMaisMarcada': max(erradas, key=lambda a: a['n'])['letra'],
        'cadernos': cadernos,
        'populacao': f'Participantes presentes na prova da área com os cadernos regulares ({", ".join(c["cor"] for c in cadernos)})'
                     + (f' que escolheram {NOME_LINGUA[lingua]}' if lingua else '') + '.',
        'aplicacao': fonte['aplicacao'],
        'fonte': f'Microdados do Enem {ano}, Inep', 'pagina': PAGINA, 'arquivo': fonte['arquivo'],
        'baixadoEm': fonte['baixadoEm'], 'processadoEm': processado,
    }


def gerar(catalogo, inep, processado):
    questoes = [q for q in json.loads(Path(catalogo).read_text())['questoes'] if q.get('prova') == 'enem' and q.get('ano') in FONTES]
    dados = {ano: carregar_ano(inep, ano) for ano in FONTES}
    saida = {}
    for q in sorted(questoes, key=lambda q: q['chave']):
        saida[q['chave']] = casar(q, *dados[q['ano']], processado)
    return {'formato': 1, 'processadoEm': processado, 'pagina': PAGINA,
            'fontes': {str(a): f for a, f in FONTES.items()},
            'regraCadernos': 'Só a 1ª aplicação regular: as quatro cores regulares do dia (Dicionário de Microdados). '
                             'Fora: ampliada, superampliada, ledor, Libras, atendimento especializado, leitor de tela, reaplicação, PPL e BAM (2025).',
            'questoes': saida}


def matriz(pdf):
    """Habilidades da Matriz de Referência do Enem (PDF do Inep, no zip dos microdados): área -> H -> (competência, texto)."""
    import re
    import subprocess
    texto = subprocess.run(['pdftotext', str(pdf), '-'], capture_output=True, text=True, check=True).stdout
    texto = texto[:texto.index('Objetos de conhecimento associados')]
    nomes = {'Linguagens': 'LC', 'Matemática': 'MT', 'Ciências da Natureza': 'CN', 'Ciências Humanas': 'CH'}
    partes = re.split(r'Matriz de Referência de (Linguagens|Matemática|Ciências da Natureza|Ciências Humanas)[^\n]*\n', texto)
    habilidades = {}
    for nome, corpo in zip(partes[1::2], partes[2::2]):
        corpo, area = re.sub(r'\s+', ' ', corpo), {}
        for bloco in re.split(r'(?=Competência de área \d+)', corpo):
            m = re.match(r'Competência de área (\d+)', bloco)
            if m:
                for h, txt in re.findall(r'H ?(\d{1,2}) ?[–-] (.*?)(?= H ?\d{1,2} ?[–-] |$)', bloco):
                    area[int(h)] = (int(m[1]), txt.strip())
        if sorted(area) != list(range(1, 31)):
            raise SystemExit(f'Matriz: {nome} sem as 30 habilidades.')
        habilidades[nomes[nome]] = area
    return habilidades


def revisao_md(resultado, catalogo, habilidades, pdf):
    """Apoio à revisão humana: habilidade oficial (CO_HABILIDADE) das questões em revisão. Não reclassifica nada."""
    import re
    cat = {q['chave']: q for q in json.loads(Path(catalogo).read_text())['questoes']}
    dados = resultado['questoes']
    hab = lambda r: habilidades[r['area']][r['habilidade']] if r.get('habilidade') else (None, 'sem habilidade no Inep')
    linhas = ['# Classificações em revisão e habilidade oficial do Inep', '',
              f'Gerado por `scripts/estatisticas-inep.py --revisao` em {resultado["processadoEm"]}; não editar à mão. '
              f'Fontes: `ITENS_PROVA_<ano>.csv` (CO_HABILIDADE) e Matriz de Referência do Enem do zip dos microdados de 2025 '
              f'(sha256 {hashlib.sha256(Path(pdf).read_bytes()).hexdigest()[:16]}…). Sem gabarito.', '',
              'A matéria, o tópico e o assunto são a classificação do próprio PU e não têm fonte oficial por questão: os microdados só '
              'trazem a habilidade da matriz (H1 a H30 de cada área), que não é uma matéria. A tabela serve de prova para quem revisar; '
              'nenhuma classificação foi trocada.', '',
              '## As 34 questões marcadas para revisão', '',
              '| Questão | Matéria e assunto no PU | CO_ITEM | Habilidade oficial |', '|---|---|---|---|']
    for chave in sorted(k for k in dados if cat.get(k, {}).get('revisar')):
        r = dados[chave]; q = cat[chave]
        if r['situacao'] != 'validado':
            linhas.append(f'| {chave} | {q["materia"]}: {q["assunto"]} | sem casamento | {r["motivo"]} |'); continue
        comp, txt = hab(r)
        linhas.append(f'| {chave} | {q["materia"]}: {q["assunto"]} | {r["coItem"]} | {r["area"]} H{r["habilidade"]} (competência {comp}): {txt} |')
    linhas += ['', '## Habilidades citadas no assunto do PU', '',
               '| Questão | Assunto no PU | Habilidade oficial | Situação |', '|---|---|---|---|']
    for chave in sorted(dados):
        q = cat.get(chave, {}); r = dados[chave]
        citadas = [int(h) for h in re.findall(r'\bH(\d{1,2})\b', q.get('assunto', ''))]
        if citadas and r['situacao'] == 'validado':
            comp, txt = hab(r)
            linhas.append(f'| {chave} | {q["assunto"]} | H{r["habilidade"]}: {txt} | {"bate" if r["habilidade"] in citadas else "diferente"} |')
    return '\n'.join(linhas) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--inep', type=Path, default=PADRAO_INEP)
    parser.add_argument('--catalogo', type=Path, default=RAIZ / '.catalogo/atual.json')
    parser.add_argument('--destino', type=Path, default=None, help='padrão: estatisticas-inep.json ao lado do catálogo')
    parser.add_argument('--conferir', action='store_true', help='confere o sha256 dos zips em <inep>/zips (lento: 1,5 GB)')
    parser.add_argument('--revisao', type=Path, default=None, help='grava também a tabela de apoio às classificações em revisão (sem gabarito)')
    parser.add_argument('--matriz', type=Path, default=None, help='PDF da Matriz de Referência (padrão: <inep>/2025/Matriz_Referencia_ENEM.pdf)')
    args = parser.parse_args()
    if args.conferir:
        for ano, fonte in FONTES.items():
            arquivo = args.inep / 'zips' / f'microdados_enem_{ano}.zip'
            h = hashlib.sha256()
            with arquivo.open('rb') as f:
                for bloco in iter(lambda: f.read(1 << 20), b''):
                    h.update(bloco)
            if h.hexdigest() != fonte['sha256']:
                raise SystemExit(f'sha256 de {arquivo} diferente do registrado.')
            print(f'{arquivo.name}: sha256 confere.')
    processado = datetime.now(timezone(timedelta(hours=-3))).strftime('%Y-%m-%d')
    resultado = gerar(args.catalogo, args.inep, processado)
    destino = args.destino or args.catalogo.parent / 'estatisticas-inep.json'
    temporario = destino.with_suffix('.novo')
    temporario.write_text(json.dumps(resultado, ensure_ascii=False, indent=1))
    temporario.chmod(0o644)
    temporario.replace(destino)
    contagem = {}
    for chave, r in resultado['questoes'].items():
        ano = chave.split(':')[1]
        contagem.setdefault(ano, {}).setdefault(r['situacao'], 0)
        contagem[ano][r['situacao']] += 1
    print('Gravado:', destino, json.dumps(contagem, ensure_ascii=False))
    if args.revisao:
        pdf = args.matriz or args.inep / '2025' / 'Matriz_Referencia_ENEM.pdf'
        args.revisao.write_text(revisao_md(resultado, args.catalogo, matriz(pdf), pdf))
        print('Gravado:', args.revisao)
    for chave, r in resultado['questoes'].items():
        if r['situacao'] != 'validado':
            print('  indisponível', chave, '-', r['motivo'])


if __name__ == '__main__':
    sys.exit(main())
