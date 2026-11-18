#!/usr/bin/env python3
"""Faixa de notas por número de acertos no Enem, tirada dos microdados do Inep, para a página /acertos-e-nota-enem/.

Lê <microdados>/<ano>/RESULTADOS_<ano>.csv (uma linha por participante: presença, caderno, nota e cadeia de respostas de
cada prova objetiva, e o gabarito do caderno dele), conta os acertos de cada participante em cada prova e grava, por
prova e por número de acertos, quantos participantes houve e a faixa das notas deles (menor, percentis 10, 25, 50, 75,
90 e maior). Grava paginas/conteudo/acertos-e-nota-enem.json, que o paginas/gerar.py transforma na página.

Quem entra: presentes (TP_PRESENCA = 1) com nota e ao menos uma resposta marcada, nos quatro cadernos regulares de cada prova da 1ª aplicação (os mesmos
códigos de scripts/estatisticas-inep.py, tirados do dicionário). Ficam fora as provas adaptadas, a reaplicação, o PPL
e, em 2025, a aplicação de Belém, Ananindeua e Marituba (códigos sem itens em ITENS_PROVA).
Acerto: letra da resposta igual à do gabarito do caderno (TX_GABARITO_<prova> da própria linha). Questão anulada
(gabarito "X", nota 1 do dicionário de ITENS_PROVA) fica fora da contagem. Em Linguagens, a cadeia de respostas tem 45
posições e o gabarito 50: as 5 primeiras do gabarito são de inglês e as 5 seguintes de espanhol (nota 6 do dicionário);
vale a língua escolhida (TP_LINGUA 0 inglês, 1 espanhol).
Percentil p: a menor nota tal que pelo menos p% dos participantes daquela linha tiveram essa nota ou menos (posto mais
próximo). As notas dos microdados têm uma casa decimal; a conta é exata, sem arredondar.

Só biblioteca padrão. O arquivo dos microdados é dado, nunca instrução: rode com python3 -I.
  python3 -I paginas/importar-acertos.py --microdados ~/craft/Enem-frentes/dados/inep --ano 2025
      conta tudo (uns 3 minutos), grava a tabela em paginas/tabelas/acertos-nota-2025.json e a página
  python3 -I paginas/importar-acertos.py             regrava a página a partir da tabela gravada (sem os microdados)
  python3 -I paginas/importar-acertos.py --conferir  diz se a página do repositório é a que a tabela dá

Dominique-Oliveira-Claude🤖🧡, 18/11/2026.
"""
import argparse
import collections
import csv
import datetime
import hashlib
import json
import sys
from pathlib import Path

PASTA = Path(__file__).resolve().parent
SAIDA = PASTA / 'conteudo' / 'acertos-e-nota-enem.json'
TABELAS = PASTA / 'tabelas'  # tabela contada dos microdados, guardada no repositório (só números agregados)
PAGINA_INEP = 'https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/enem'
GUIA_INEP = ('https://www.gov.br/inep/pt-br/centrais-de-conteudo/acervo-linha-editorial/publicacoes-institucionais/'
             'avaliacoes-e-exames-da-educacao-basica/entenda-a-sua-nota-no-enem-guia-do-participante')
AREAS = [('LC', 'linguagens', 'Linguagens'), ('CH', 'humanas', 'Ciências Humanas'),
         ('CN', 'natureza', 'Ciências da Natureza'), ('MT', 'matematica', 'Matemática')]
# Cadernos regulares da 1ª aplicação (dicionário de cada ano; os mesmos de scripts/estatisticas-inep.py).
REGULARES = {
    2024: {'LC': (1395, 1396, 1397, 1398), 'CH': (1383, 1384, 1385, 1386), 'CN': (1419, 1420, 1421, 1422), 'MT': (1407, 1408, 1409, 1410)},
    2025: {'LC': (1459, 1460, 1461, 1462), 'CH': (1447, 1448, 1449, 1450), 'CN': (1483, 1484, 1485, 1486), 'MT': (1471, 1472, 1473, 1474)},
}
PERCENTIS = (10, 25, 50, 75, 90)
AMOSTRA_MINIMA = 30  # abaixo disso, a linha mostra só menor e maior nota (percentil com poucos participantes engana)


class Recusa(Exception):
    pass


def gabarito_do_participante(area, gabarito, lingua):
    """Gabarito de 45 letras na ordem da cadeia de respostas. Em Linguagens, escolhe as 5 da língua do participante."""
    if area != 'LC':
        return gabarito
    if len(gabarito) != 50 or lingua not in ('0', '1'):
        return None
    return (gabarito[:5] if lingua == '0' else gabarito[5:10]) + gabarito[10:]


def acertos_de(respostas, gabarito):
    """Quantas letras da resposta batem com o gabarito, sem contar questão anulada (X). Devolve (acertos, válidas)."""
    validas = sum(1 for g in gabarito if g != 'X')
    return sum(1 for r, g in zip(respostas, gabarito) if g != 'X' and r == g), validas


def contar(caminho, ano, limite=None):
    """Lê o RESULTADOS_<ano>.csv e devolve {área: {acertos: Counter(nota em décimos)}}, o número de questões válidas
    por área e as contagens de quem ficou de fora (por motivo)."""
    regulares = {a: set(c) for a, c in REGULARES[ano].items()}
    histogramas = {a: collections.defaultdict(collections.Counter) for a, _, _ in AREAS}
    validas = {a: collections.Counter() for a, _, _ in AREAS}
    fora = collections.Counter()
    with open(caminho, encoding='latin-1', newline='') as arquivo:
        leitor = csv.reader(arquivo, delimiter=';')
        cabeca = next(leitor)
        col = {nome: i for i, nome in enumerate(cabeca)}
        faltam = [f'{p}_{a}' for a, _, _ in AREAS for p in ('TP_PRESENCA', 'CO_PROVA', 'NU_NOTA', 'TX_RESPOSTAS', 'TX_GABARITO') if f'{p}_{a}' not in col]
        if faltam or 'TP_LINGUA' not in col:
            raise Recusa(f'colunas que faltam no arquivo: {faltam}')
        lingua = col['TP_LINGUA']
        for n, linha in enumerate(leitor):
            if limite is not None and n >= limite:
                break
            for area, _, _ in AREAS:
                if linha[col['TP_PRESENCA_' + area]] != '1':
                    continue
                prova = linha[col['CO_PROVA_' + area]]
                if not prova.isdigit() or int(prova) not in regulares[area]:
                    fora[area, 'outro caderno'] += 1
                    continue
                nota = linha[col['NU_NOTA_' + area]]
                if nota == '':
                    fora[area, 'sem nota'] += 1
                    continue
                respostas = linha[col['TX_RESPOSTAS_' + area]]
                gabarito = gabarito_do_participante(area, linha[col['TX_GABARITO_' + area]], linha[lingua])
                if gabarito is None or len(gabarito) != 45 or len(respostas) != 45:
                    fora[area, 'cadeia fora do formato'] += 1
                    continue
                decimos = round(float(nota) * 10)
                if respostas.count('.') == 45:
                    # Prova inteira em branco: fica fora da tabela (no Enem 2025, todos com nota 0), contada à parte.
                    fora[area, 'em branco com nota 0' if decimos == 0 else 'em branco com nota maior que 0'] += 1
                    continue
                certas, total = acertos_de(respostas, gabarito)
                validas[area][total] += 1
                histogramas[area][certas][decimos] += 1
    return histogramas, validas, fora


def resumo(contagem):
    """Participantes, menor, percentis e maior nota de um Counter {nota em décimos: participantes} (posto mais próximo)."""
    total = sum(contagem.values())
    notas = sorted(contagem)
    saida = {'participantes': total, 'menor': notas[0] / 10, 'maior': notas[-1] / 10}
    alvos = {p: -(-p * total // 100) for p in PERCENTIS}  # posto = teto(p% de n), contado a partir de 1
    acumulado, i = 0, 0
    pendentes = sorted(alvos.items(), key=lambda x: x[1])
    for nota in notas:
        acumulado += contagem[nota]
        while i < len(pendentes) and acumulado >= pendentes[i][1]:
            saida[f'p{pendentes[i][0]}'] = nota / 10
            i += 1
    return saida


def tabela(histogramas):
    return {area: {str(a): resumo(h) for a, h in sorted(histogramas[area].items())} for area, _, _ in AREAS}


def numero(valor):
    """Nota com uma casa decimal e vírgula, como no boletim (ex.: 612,4)."""
    return f'{valor:.1f}'.replace('.', ',')


def milhar(n):
    return f'{n:,}'.replace(',', '.')


def conteudo_da_pagina(ano, dados, validas, fora, origem, conferido_em):
    fonte = {'fonte': PAGINA_INEP, 'conferido_em': conferido_em}
    blocos_dados, notas_area, exemplos = [], {}, {}
    for area, chave, nome in AREAS:
        questoes = validas[area].most_common(1)[0][0]
        if len(validas[area]) != 1:
            raise Recusa(f'{area}: cadernos com número diferente de questões válidas: {dict(validas[area])}')
        linhas = []
        participantes = 0
        for acertos in range(questoes + 1):
            r = dados[area].get(str(acertos))
            if not r:
                linhas.append({'valores': [str(acertos), '0'], 'aviso': 'Ninguém teve esse número de acertos'})
                continue
            participantes += r['participantes']
            if r['participantes'] < AMOSTRA_MINIMA:
                meio = ['poucos participantes'] * len(PERCENTIS)
            else:
                meio = [numero(r[f'p{p}']) for p in PERCENTIS]
            linhas.append({'valores': [str(acertos), milhar(r['participantes']), numero(r['menor']), *meio, numero(r['maior'])],
                           'texto_fonte': 'Inep', **fonte})
        anuladas = 45 - questoes
        nota = [f'{milhar(participantes)} participantes, {questoes} questões contadas. Fonte: [microdados do Enem {ano}]({PAGINA_INEP}), do Inep.']
        if anuladas:
            nota.append(f'{anuladas} {"questão anulada ficou" if anuladas == 1 else "questões anuladas ficaram"} fora da contagem, '
                        f'por isso os acertos vão de 0 a {questoes}.')
        notas_area[area] = (participantes, questoes)
        blocos_dados.append({'tipo': 'dados', 'id': chave, 'titulo': f'{nome}: acertos e nota no Enem {ano}', 'largo': True, 'compacta': True,
                             'colunas': ['Acertos', 'Participantes', 'Menor nota', 'P10', 'P25', 'Mediana', 'P75', 'P90', 'Maior nota'],
                             'coluna_fonte': 'Fonte', 'nota': nota, 'linhas': linhas})
        # Exemplo do texto: a linha de 30 acertos (ou a mais perto) de cada prova.
        alvo = min(dados[area], key=lambda a: (abs(int(a) - 30), -int(a)))
        exemplos[area] = (int(alvo), dados[area][alvo])
    mt_acertos, mt = exemplos['MT']
    ch_acertos, ch = exemplos['CH']
    if any(m in ('sem nota', 'cadeia fora do formato') for (_, m) in fora):
        raise Recusa(f'participantes fora por motivo que a página não explica: {dict(fora)}')
    total_fora = {area: fora.get((area, 'outro caderno'), 0) for area, _, _ in AREAS}
    brancos = {area: fora.get((area, 'em branco com nota 0'), 0) for area, _, _ in AREAS}
    if any(fora.get((area, 'em branco com nota maior que 0')) for area, _, _ in AREAS):
        raise Recusa('há prova inteira em branco com nota maior que 0: o texto da página precisa mudar')
    return {
        'tipo': 'leitura', 'endereco': '/acertos-e-nota-enem/',
        'titulo': f'Quantos acertos para cada nota no Enem {ano}: faixa por prova',
        'descricao': (f'Para cada número de acertos, a faixa de notas que os participantes tiveram nas quatro provas objetivas '
                      f'do Enem {ano}, com a amostra e os microdados do Inep. E por que a TRI muda a nota.'),
        'migalha': 'Acertos e nota no Enem',
        'h1': 'Acertos e nota no Enem',
        'apoio': (f'Quem acertou o mesmo número de questões não teve a mesma nota. Aqui está a faixa de notas de cada número de '
                  f'acertos nas quatro provas objetivas do Enem {ano}, contada nos microdados oficiais do Inep.'),
        'tom': 'mar', 'atualizada_em': conferido_em, 'menu': True, 'sumario': True,
        'relacionadas': ['/calculadora-nota-enem/', '/provas-anteriores/', '/temas-de-redacao-enem/'],
        'blocos': [
            {'tipo': 'texto', 'id': 'tri', 'no_sumario': True, 'titulo': 'Por que o mesmo número de acertos dá notas diferentes', 'paragrafos': [
                'A nota de cada prova objetiva do Enem é calculada pela Teoria de Resposta ao Item, a TRI. Ela olha quais questões você acertou, e não só quantas.',
                'Cada questão tem três medidas calculadas pelo Inep: quanto ela separa quem domina a habilidade de quem não domina, quão difícil ela é e qual a chance de alguém acertar sem dominar o assunto, no chute. Essas medidas estão no dicionário dos microdados.',
                'Para a TRI, quem acerta as questões difíceis também deve acertar as fáceis. Quando alguém acerta difíceis e erra fáceis, o modelo entende que parte desses acertos pode ter vindo do chute, e eles somam menos na nota. Por isso duas pessoas com o mesmo número de acertos podem ter notas diferentes.',
                'Isso não tira pontos de ninguém: segundo o Inep, uma questão certa sempre aumenta a nota, e questão em branco é corrigida como errada. Vale responder todas.',
                (f'Um exemplo da tabela: no Enem {ano}, quem acertou {mt_acertos} questões de Matemática teve nota entre {numero(mt["menor"])} e {numero(mt["maior"])}; '
                 f'metade dessas pessoas ficou com até {numero(mt["p50"])}. Em Ciências Humanas, {ch_acertos} acertos deram notas entre {numero(ch["menor"])} e {numero(ch["maior"])}.'),
                f'O Inep explica a TRI no [guia Entenda a sua nota no Enem]({GUIA_INEP}).']},
            {'tipo': 'texto', 'id': 'colunas', 'no_sumario': True, 'titulo': 'Como ler a tabela', 'paragrafos': [
                'Cada linha junta as pessoas que tiveram aquele número de acertos na prova.',
                'Participantes: quantas pessoas tiveram esse número de acertos. Menor nota e Maior nota: a nota mais baixa e a mais alta entre elas.',
                'P10 e P25: 10% e 25% dessas pessoas tiraram essa nota ou menos.',
                'Mediana: metade tirou essa nota ou menos, e a outra metade tirou essa nota ou mais.',
                'P75 e P90: 75% e 90% tiraram essa nota ou menos.',
                'Entre P25 e P75 está a metade do meio, a faixa mais comum para aquele número de acertos. Menor e maior nota mostram os casos raros.',
                f'Com menos de {AMOSTRA_MINIMA} participantes numa linha, a tabela mostra só a menor e a maior nota: com tão poucas pessoas, os percentis enganam.']},
            *blocos_dados,
            {'tipo': 'texto', 'id': 'origem', 'no_sumario': True, 'titulo': 'De onde vêm os números', 'paragrafos': [
                (f'Dos [microdados do Enem {ano}]({PAGINA_INEP}), publicados pelo Inep: o arquivo de resultados traz, para cada participante, '
                 f'as respostas, o gabarito do caderno dele e a nota de cada prova. O PU baixou o arquivo em {origem["baixado_em"]} e contou os acertos de cada pessoa em {datetime.date.fromisoformat(conferido_em).strftime("%d/%m/%Y")}.'),
                'Entram os presentes com nota nos quatro cadernos regulares de cada dia da 1ª aplicação. Ficam fora as provas adaptadas (ampliada, braile, leitor de tela, Libras), a reaplicação e o Enem para pessoas privadas de liberdade (PPL), que têm outra condição de prova ou outra data.'
                + (' Em 2025, também a aplicação de Belém, Ananindeua e Marituba, feita em outra data por causa da COP30.' if ano == 2025 else ''),
                'Acerto é a letra marcada igual à do gabarito. Resposta em branco ou com duas marcações conta como erro. Questão anulada pelo Inep fica fora da contagem. Em Linguagens, as cinco questões de língua estrangeira são as da língua que a pessoa escolheu.',
                (f'Quem deixou a prova inteira em branco tem nota 0 nos microdados e ficou fora da tabela, para não misturar com quem respondeu e errou tudo: '
                 f'{milhar(brancos["LC"])} pessoas em Linguagens, {milhar(brancos["CH"])} em Ciências Humanas, {milhar(brancos["CN"])} em Ciências da Natureza e {milhar(brancos["MT"])} em Matemática.'),
                (f'Também ficaram fora, por terem feito a prova num caderno adaptado ou de outra aplicação: {milhar(total_fora["LC"])} em Linguagens, {milhar(total_fora["CH"])} em Ciências Humanas, '
                 f'{milhar(total_fora["CN"])} em Ciências da Natureza e {milhar(total_fora["MT"])} em Matemática.'),
                f'Esta é a edição mais recente com microdados publicados pelo Inep quando a tabela foi feita: Enem {ano}. A relação entre acertos e nota muda a cada prova, porque as questões mudam. A tabela de outra edição dá outros números.']},
            {'tipo': 'texto', 'id': 'limites', 'no_sumario': True, 'titulo': 'O que a tabela não diz', 'paragrafos': [
                'Ela não diz qual vai ser a sua nota. Na próxima prova as questões são outras, e a faixa de cada número de acertos também.',
                'Use a tabela para entender a ordem de grandeza e para ver que acertar as questões que você domina pesa. Para planejar a média de um curso, digite as notas por área na [calculadora de média](/calculadora-nota-enem/).']},
        ],
        'chamada': {'titulo': 'Treine com questões do Enem', 'texto': 'No PU você resolve questões oficiais do Enem, uma por vez, e acompanha o progresso por matéria. O que você errar volta para a revisão em 1, 3 e 7 dias. É gratuito.'},
    }


def sha256(caminho):
    resumo_ = hashlib.sha256()
    with open(caminho, 'rb') as arquivo:
        for pedaco in iter(lambda: arquivo.read(1 << 20), b''):
            resumo_.update(pedaco)
    return resumo_.hexdigest()


def ler_tabela(caminho):
    """Tabela gravada (paginas/tabelas/acertos-nota-<ano>.json) -> (ano, dados, validas, fora, origem)."""
    salvo = json.loads(Path(caminho).read_text(encoding='utf-8'))
    origem = salvo['origem']
    validas = {a: collections.Counter({int(k): v for k, v in c.items()}) for a, c in origem['questoes_validas'].items()}
    fora = collections.Counter({tuple(k.split(' ', 1)): v for k, v in origem['fora'].items()})
    return origem['ano'], salvo['tabela'], validas, fora, origem


def principal():
    argumentos = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    argumentos.add_argument('--microdados', help='pasta com <ano>/RESULTADOS_<ano>.csv; sem ela, a página sai da tabela já gravada')
    argumentos.add_argument('--ano', type=int, default=2025, choices=sorted(REGULARES))
    argumentos.add_argument('--baixado-em', default='17/11/2026', help='data em que o zip dos microdados foi baixado (DD/MM/AAAA)')
    argumentos.add_argument('--conferido-em', default=datetime.date.today().isoformat())
    argumentos.add_argument('--conferir', action='store_true', help='só diz se a página do repositório é a que a tabela gravada dá')
    a = argumentos.parse_args()
    caminho_tabela = TABELAS / f'acertos-nota-{a.ano}.json'
    try:
        if a.microdados:
            caminho = Path(a.microdados).expanduser() / str(a.ano) / f'RESULTADOS_{a.ano}.csv'
            if not caminho.is_file():
                raise Recusa(f'arquivo não encontrado: {caminho}')
            histogramas, validas, fora = contar(caminho, a.ano)
            origem = {'arquivo': caminho.name, 'tamanho': caminho.stat().st_size, 'sha256': sha256(caminho), 'baixado_em': a.baixado_em,
                      'contado_em': a.conferido_em, 'ano': a.ano, 'pagina_oficial': PAGINA_INEP,
                      'questoes_validas': {k: dict(v) for k, v in validas.items()}, 'fora': {f'{k[0]} {k[1]}': v for k, v in sorted(fora.items())}}
            TABELAS.mkdir(exist_ok=True)
            caminho_tabela.write_text(json.dumps({'origem': origem, 'tabela': tabela(histogramas)}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        ano, dados, validas, fora, origem = ler_tabela(caminho_tabela)
        conteudo = conteudo_da_pagina(ano, dados, validas, fora, origem, origem['contado_em'])
        if a.conferir:
            if json.loads(SAIDA.read_text(encoding='utf-8')) != conteudo:
                print('Diferente: rode python3 -I paginas/importar-acertos.py para regravar a página a partir da tabela.')
                return 1
            print('Página igual à tabela dos microdados.')
            return 0
    except Recusa as erro:
        print('RECUSADO  ' + str(erro), file=sys.stderr)
        return 2
    SAIDA.write_text(json.dumps(conteudo, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'Gravado {SAIDA}. Participantes por prova: ' + ', '.join(f'{k} {sum(r["participantes"] for r in v.values())}' for k, v in dados.items()))
    return 0


if __name__ == '__main__':
    sys.exit(principal())
