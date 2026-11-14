"""Provas ativas de cada conta: quais vestibulares entram no estudo, no simulado e no acompanhamento.

Guardada no banco central, numa tabela própria. Sem linha para a conta = todas as provas do catálogo,
inclusive as que entrarem depois (padrão de toda conta, e da conta de teste). Gravar a lista completa
apaga a linha e volta ao padrão. Dominique-Oliveira-Claude🤖🧡, 14/11/2026.
"""
import json
from acompanhamento import indice

NOMES = {'enem': 'Enem', 'fuvest': 'Fuvest (USP)', 'unesp': 'Unesp', 'unicamp': 'Unicamp', 'famerp': 'Famerp'}
ORDEM = list(NOMES)


def prova_de(q):
    return q.get('prova') or 'enem'


def disponiveis(questoes):
    """Provas presentes no catálogo, na ordem fixa, com edições e número de questões."""
    resumo = {}
    for q in sorted(questoes, key=lambda q: q['id']):
        item = resumo.setdefault(prova_de(q), {'questoes': 0, 'edicoes': set(), 'faixas': []})
        item['questoes'] += 1
        item['edicoes'].add(q.get('ano'))
        # Faixas de IDs da prova ([primeiro, último]): a interface tira na hora as questões de uma prova desligada,
        # sem esperar o painel novo. Com o registro de IDs por prova, cada prova cabe em poucas faixas.
        faixas = item['faixas']
        if faixas and faixas[-1][1] == q['id'] - 1: faixas[-1][1] = q['id']
        else: faixas.append([q['id'], q['id']])
    siglas = sorted(resumo, key=lambda s: (ORDEM.index(s) if s in ORDEM else len(ORDEM), s))
    return [{'id': s, 'nome': NOMES.get(s, s.capitalize()), 'questoes': resumo[s]['questoes'],
             'edicoes': sorted((a for a in resumo[s]['edicoes'] if a), reverse=True), 'faixas': resumo[s]['faixas']} for s in siglas]


def preparar(con):
    con.execute('CREATE TABLE IF NOT EXISTS provas_ativas(conta INTEGER PRIMARY KEY REFERENCES contas(id), ativas TEXT NOT NULL)')


def ativas(con, conta, siglas):
    """Lista de siglas ativas da conta, sempre dentro das disponíveis. Lista vazia nunca sai daqui."""
    linha = con.execute('SELECT ativas FROM provas_ativas WHERE conta=?', (conta,)).fetchone()
    if not linha:
        return list(siglas)
    escolhidas = [s for s in siglas if s in set(json.loads(linha[0]))]
    # Se todas as escolhidas saíram do catálogo, volta ao padrão em vez de deixar a conta sem questões.
    return escolhidas or list(siglas)


def gravar(con, conta, pedido, siglas):
    """Valida e grava a escolha. Devolve a lista ativa resultante."""
    if not isinstance(pedido, list) or not 1 <= len(pedido) <= 20 or any(not isinstance(s, str) for s in pedido):
        raise ValueError('Escolha ao menos uma prova.')
    escolhidas = [s for s in siglas if s in set(pedido)]
    if len(escolhidas) != len(set(pedido)):
        raise ValueError('Prova desconhecida.')
    if set(escolhidas) == set(siglas):
        con.execute('DELETE FROM provas_ativas WHERE conta=?', (conta,))
    else:
        con.execute('INSERT INTO provas_ativas(conta,ativas) VALUES(?,?) ON CONFLICT(conta) DO UPDATE SET ativas=excluded.ativas',
                    (conta, json.dumps(escolhidas)))
    return escolhidas


class Recorte:
    """Questões, índice e mapa de um conjunto de provas ativas, calculados uma vez por conjunto."""

    def __init__(self, questoes):
        self.todas = questoes
        self.siglas = [p['id'] for p in disponiveis(questoes)]
        self._cache = {}

    def de(self, ativas):
        chave = frozenset(ativas)
        if chave not in self._cache:
            qs = [q for q in self.todas if prova_de(q) in chave]
            self._cache[chave] = {'questoes': qs, 'indice': indice(qs), 'ids': {q['id'] for q in qs}}
        return self._cache[chave]
