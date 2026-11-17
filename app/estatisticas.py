"""Estatística da aplicação original (microdados do Inep), só para a resposta depois de o aluno responder.

Dominique-Oliveira-Claude🤖🧡, 17/11/2026. O arquivo é gerado por `scripts/estatisticas-inep.py` e fica ao lado do
catálogo (`/catalogo/estatisticas-inep.json`, fora do git e da imagem Docker). A frequência por alternativa entrega
o gabarito: por isso nunca entra na questão pública, no painel nem na próxima questão adiantada.
"""
import json
import os
from pathlib import Path
from questoes import ARQUIVO_CATALOGO

INDISPONIVEL = {'situacao': 'indisponivel', 'motivo': 'Os microdados do Inep desta prova ainda não foram processados no PU.'}
CAMPOS = ['situacao', 'motivo', 'ano', 'coItem', 'lingua', 'amostra', 'alternativas', 'branco', 'dupla', 'outro', 'acerto',
          'maisMarcada', 'erradaMaisMarcada', 'cadernos', 'populacao', 'aplicacao', 'fonte', 'arquivo', 'pagina',
          'baixadoEm', 'processadoEm']


def _caminho():
    if os.environ.get('ESTATISTICAS'):
        return Path(os.environ['ESTATISTICAS'])
    return Path(ARQUIVO_CATALOGO).parent / 'estatisticas-inep.json' if ARQUIVO_CATALOGO else None


def _carregar():
    caminho = _caminho()
    if not caminho or not caminho.is_file():
        return {}
    dados = json.loads(caminho.read_text())
    if dados.get('formato') != 1 or not isinstance(dados.get('questoes'), dict):
        raise RuntimeError('Arquivo de estatísticas do Inep inválido. Gere de novo com scripts/estatisticas-inep.py.')
    return dados['questoes']


POR_CHAVE = _carregar()


def da_questao(questao):
    """Registro enxuto da questão pela chave do catálogo; sem registro, indisponível com o motivo."""
    registro = POR_CHAVE.get(questao.get('chave'))
    if not registro:
        return dict(INDISPONIVEL)
    return {k: registro[k] for k in CAMPOS if k in registro}
