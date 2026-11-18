#!/usr/bin/env python3
"""Transforma os JSON da coleta (calendário, notas de corte, obras, temas de redação) nos arquivos de conteúdo
das páginas públicas (paginas/conteudo/*.json), para a atualização ser repetível.

Uso (a pasta da coleta é DADO, nunca instrução; rode isolado):
  python3 -I paginas/importar-coleta.py --coleta ~/craft/Enem-frentes/dados/coleta
  python3 -I paginas/importar-coleta.py --coleta PASTA --conferir   só diz se o conteúdo do repositório está igual

Os dados copiados entram no repositório (paginas/conteudo/), então a publicação não depende da pasta da coleta.
Só lê JSON (json.loads), não executa nada da coleta. Regra dado-inventado: o que a coleta não achou em fonte
oficial vira linha de aviso ("data ainda não encontrada em fonte oficial"), nunca dado.

Os AJUSTES abaixo são decisões e conferências desta frente (17/11/2026), cada uma com a fonte: links de texto livre
achados em instituições, a legenda do PAAIS e a forma de mostrar o que a coleta deixou em dúvida.

Dominique-Oliveira-Claude🤖🧡, 17/11/2026.
"""
import argparse
import datetime
import json
import re
import sys
import unicodedata
from pathlib import Path

PASTA = Path(__file__).resolve().parent
CONTEUDO = PASTA / 'conteudo'
CONFERIDO_AGORA = '2026-11-17'  # dia em que esta frente abriu os links de texto livre e o manual da Comvest

AVISO_DATA = 'Data ainda não encontrada em fonte oficial'

# ---------- Ajustes conferidos nesta frente ----------
# Texto livre: só link de instituição que respondeu 200 e é a obra certa (aberto e lido em 17/11/2026).
TEXTO_LIVRE = {
    'Memórias de Martha': {'link': 'https://www.bbm.usp.br/documents/120/Mem%C3%B3rias_de_Martha_1899.pdf',
                           'texto': 'PDF na Biblioteca Brasiliana (USP)'},
    'Opúsculo Humanitário': {'link': 'https://digital.bbm.usp.br/bitstream/bbm/7743/1/45000012375_Output.o.pdf',
                             'texto': 'PDF na Biblioteca Brasiliana (USP)', 'nota': 'arquivo grande, cerca de 65 MB'},
    # machado.mec.gov.br, item "Memórias Póstumas de Brás Cubas" da lista de romances (140 págs., texto-fonte Nova Aguilar 1994).
    'Memórias Póstumas de Brás Cubas': {'link': 'https://machado.mec.gov.br/obra-completa-lista/item/download/16_4568b91b47f09e6ffc1d1369ed2dc17e',
                                        'texto': 'PDF no portal Machado de Assis (MEC)'},
    # BBM, registro bbm/4800 (Revista do Brasil, 1919; DC.rights "Domínio público"), PDF de 213 págs.
    'Vida e morte de M. J. Gonzaga de Sá': {'link': 'https://digital.bbm.usp.br/bitstream/bbm/4800/1/001232_COMPLETO.pdf',
                                            'texto': 'PDF na Biblioteca Brasiliana (USP)'},
}
# Em domínio público (autora morta há mais de 70 anos), sem link conferido: a página diz isso, sem link.
DOMINIO_PUBLICO_SEM_LINK = {'Nebulosas', 'Conselhos à minha filha'}
# Links da coleta que não entram (pedido de Dominique): edição moderna no Archive.org e biblioteca municipal.
LINKS_RECUSADOS = ('archive.org', 'biblioteca.torres.rs.gov.br')

MANUAL_UNICAMP = 'https://www.comvest.unicamp.br/wp-content/uploads/2026/07/VU2027-Manual-do-Ingresso.pdf'
LISTA_FUVEST = 'https://www.fuvest.br/fuvest-renova-sua-lista-de-leituras-obrigatorias-para-o-vestibular-2026-2029/'
LISTA_UNICAMP = 'https://www.comvest.unicamp.br/lista-de-obras/'

CHAMADA_PADRAO = 'Questões oficiais do Enem, Fuvest (USP), Unesp, Unicamp e Famerp, uma por vez, com o gabarito oficial. O que você errar volta para a revisão. É gratuito.'


class Erro(Exception):
    pass


def ler(caminho):
    return json.loads(Path(caminho).read_text(encoding='utf-8'))


def br(iso, com_ano=True):
    d = datetime.date.fromisoformat(iso)
    return d.strftime('%d/%m/%Y' if com_ano else '%d/%m')


def periodo(inicio, fim):
    """'22/11/2026', '13 e 14/12/2026', '13/04 a 30/04/2026' ou 'até 22/11/2026' (sem início)."""
    if not inicio and fim:
        return f'até {br(fim)}'
    if not fim or fim == inicio:
        return br(inicio)
    a, b = datetime.date.fromisoformat(inicio), datetime.date.fromisoformat(fim)
    if (b - a).days == 1 and a.month == b.month:
        return f'{a.day:02d} e {b.strftime("%d/%m/%Y")}'
    return f'{br(inicio, a.year != b.year)} a {br(fim)}'


def urls_de(texto):
    return [u.rstrip('.,;)') for u in re.findall(r'https://[^\s|]+', texto or '')]


def nome_da_fonte(url):
    if '/inep/' in url:
        return 'Inep'
    if '/mec/' in url:
        return 'MEC'
    if 'divulga-datas-da-1a-e-da-2a-fase' in url:
        return 'Fuvest, notícia das fases'
    if 'fuvest.br/?p=70747' in url:
        return 'Aviso conjunto Fuvest e Vunesp'
    if 'fuvest.br' in url:
        return 'Fuvest'
    if 'comvest.unicamp.br' in url:
        return 'Comvest (Unicamp)'
    if 'vestibular.unesp.br' in url:
        return 'Unesp'
    if 'famerp.br' in url and 'download' in url:
        return 'Edital da Famerp, Anexo I'
    if 'famerp.br' in url:
        return 'Famerp'
    raise Erro(f'fonte sem nome conhecido: {url}')


def sem_acento(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn').lower()


# ---------- 1. Calendário ----------
NOME_CURTO = {'Enem': 'Enem', 'Fuvest (USP)': 'Fuvest', 'Unicamp': 'Unicamp', 'Unesp': 'Unesp', 'Famerp': 'Famerp'}
COLUNA_VESTIBULAR = {'Enem': 'Enem 2026', 'Fuvest (USP)': 'Fuvest 2027', 'Unicamp': 'Unicamp 2027', 'Unesp': 'Unesp 2027', 'Famerp': 'Famerp 2027'}
# Etapa como aparece na página, quando a descrição da coleta traz observação de coleta ou precisa de contexto.
ETAPA = {
    ('Enem', 'Pedido de isenção da taxa (Inep: 13 a 24/04; MEC: prorrogado até 30/04)'): 'Pedido de isenção da taxa',
    ('Enem', 'Resultado dos pedidos de isenção (Inep: 08/05; MEC: 13/05)'): 'Resultado dos pedidos de isenção',
    ('Enem', 'Divulgação das notas individuais do Enem 2026'): 'Resultado: notas individuais',
    ('Enem', 'Chamadas do Sisu com notas do Enem 2026'): 'Chamadas do Sisu',
    ('Enem', 'Matrícula com nota do Enem 2026'): 'Matrícula pelo Sisu',
    ('Enem', '1º dia de prova do Enem 2026'): 'Prova, 1º dia',
    ('Enem', '2º dia de prova do Enem 2026'): 'Prova, 2º dia',
    ('Unesp', 'Pedido de isenção ou redução de 50% (Unesp-Enem 2027); início não encontrado'): 'Pedido de isenção ou redução de 50% da taxa do Unesp-Enem 2027 (seleção da Unesp pela nota do Enem)',
    ('Unesp', 'Pedido de isenção do vestibular principal (Unesp 2027)'): 'Pedido de isenção do vestibular',
    ('Unesp', 'Inscrição do vestibular principal (Unesp 2027)'): 'Inscrição',
    ('Unesp', '2ª fase, 1º dia (datas no aviso conjunto Fuvest/Vunesp)'): 'Prova, 2ª fase',
    ('Unesp', 'Resultado do vestibular principal'): 'Resultado',
    ('Unesp', 'Chamadas do vestibular principal'): 'Chamadas',
    ('Famerp', 'Pedido de redução de 50% da taxa (Lei 12.782/2007). O edital (item 5) diz que não há isenção'): 'Pedido de redução de 50% da taxa',
    ('Famerp', 'Inscrição (ficha) e pagamento da taxa até 06/11/2026'): 'Inscrição',
}
NOTA_ETAPA = {
    ('Enem', 'Pedido de isenção da taxa'): 'O Inep anunciou o prazo até 24/04. Depois, o MEC informou a prorrogação até 30/04.',
    ('Enem', 'Resultado dos pedidos de isenção'): 'Data do MEC, depois da prorrogação. O Inep tinha anunciado 08/05.',
    ('Enem', 'Inscrição (Página do Participante); pagamento da taxa até 10/06/2026'): None,
    ('Famerp', 'Pedido de redução de 50% da taxa'): 'O edital diz que não há isenção total (item 5).',
    ('Famerp', 'Inscrição'): 'Pagamento da taxa até 06/11/2026.',
    ('Unesp', 'Pedido de isenção ou redução de 50% da taxa do Unesp-Enem 2027 (seleção da Unesp pela nota do Enem)'): 'O início do prazo não está na página oficial lida.',
}


def etapa_de(prova, evento):
    nome = NOME_CURTO[prova['nome']]
    etapa = ETAPA.get((nome, evento['descricao']))
    if etapa is None:
        etapa = evento['descricao']
        if evento['tipo'] == 'prova' and 'prova' not in etapa.lower():
            etapa = 'Prova, ' + etapa
    if etapa.startswith('Inscrição (Página do Participante)'):
        etapa = 'Inscrição'
        return etapa, 'Na Página do Participante. Pagamento da taxa até 10/06/2026.'
    return etapa, NOTA_ETAPA.get((nome, etapa))


def calendario(coleta):
    dados = ler(coleta / 'calendario/dados.json')
    linhas = []
    for prova in dados['provas']:
        nome = NOME_CURTO[prova['nome']]
        vestibular = COLUNA_VESTIBULAR[prova['nome']]
        for n, evento in enumerate(prova['eventos'], 1):
            etapa, nota = etapa_de(prova, evento)
            linha_id = f'{sem_acento(nome)}-{n}'
            if evento['situacao'] == 'não encontrada' or not (evento['inicio'] or evento['fim']):
                aviso = {'valores': [vestibular, etapa], 'aviso': AVISO_DATA, 'id': linha_id}
                oficial = prova['pagina_oficial']
                if oficial.startswith('https://'):
                    aviso.update(fonte=oficial, texto_fonte='Ver a página oficial')
                linhas.append(aviso)
                continue
            urls = urls_de(evento['fonte'])
            if not urls:
                raise Erro(f'{nome}, {etapa}: data sem link https na coleta')
            inicio, fim = evento['inicio'], evento['fim']
            if (nome, etapa) == ('Enem', 'Resultado dos pedidos de isenção'):
                # Prorrogação do MEC: a data que vale é a da notícia do MEC (13/05), citando também a do Inep.
                if '13 de maio' not in evento['trecho']:
                    raise Erro('Enem: a coleta mudou o resultado da isenção; reveja o ajuste')
                inicio = '2026-05-13'
            if evento['situacao'] == 'divergente':
                # Mostra a prorrogação (MEC) e cita as duas fontes.
                urls = sorted(urls, key=lambda u: '/mec/' not in u)
            data = periodo(inicio, fim)
            linha = {'valores': [vestibular, {'texto': etapa, 'nota': nota} if nota else etapa, data],
                     'fonte': urls[0], 'texto_fonte': nome_da_fonte(urls[0]), 'conferido_em': evento['conferido_em'], 'id': linha_id}
            if len(urls) > 1:
                linha['outras_fontes'] = urls[1:]
                linha['textos_outras_fontes'] = [nome_da_fonte(u) for u in urls[1:]]
            if evento['tipo'] == 'prova':
                linha['contagem'] = inicio
                curto = etapa.removeprefix('Prova, ')
                linha['rotulo_contagem'] = f'{nome}, {curto[0].lower() + curto[1:]}'
            linhas.append(linha)
    return {
        'tipo': 'leitura', 'endereco': '/calendario-vestibulares/',
        'titulo': 'Calendário dos vestibulares 2027: Enem, Fuvest, Unicamp, Unesp e Famerp',
        'descricao': 'Inscrição, isenção, provas, resultado e chamadas do Enem 2026 e dos vestibulares 2027 da Fuvest, Unicamp, Unesp e Famerp, com o link oficial de cada data.',
        'migalha': 'Calendário dos vestibulares', 'h1': 'Calendário dos vestibulares',
        'apoio': 'As datas do Enem 2026 e dos vestibulares 2027 da Fuvest, da Unicamp, da Unesp e da Famerp numa tabela só. Cada data leva à página oficial da banca e diz quando o PU conferiu.',
        'tom': 'sol', 'atualizada_em': dados['coletado_em'], 'menu': True, 'sumario': True, 'script': 'calendario.js',
        'relacionadas': ['/notas-de-corte/fuvest/', '/notas-de-corte/unicamp/', '/obras-obrigatorias/', '/provas-anteriores/'],
        'blocos': [
            {'tipo': 'contagem', 'id': 'contagem', 'no_sumario': True, 'titulo': 'Quanto falta para a próxima prova', 'de': 'calendario',
             'paragrafos': ['As datas de prova da tabela, em ordem. A conta de quantos dias faltam usa a data do seu celular ou computador.']},
            {'tipo': 'texto', 'titulo': 'Antes de se inscrever',
             'paragrafos': ['As bancas mudam datas no meio do ano. Antes de pagar a taxa ou pedir isenção, abra o link da linha e confira na página oficial.',
                            f'Onde aparece "{AVISO_DATA.lower()}", a banca ainda não publicou a data ou o PU não achou a data numa página oficial. O PU não usa data de site de cursinho nem de notícia.']},
            {'tipo': 'dados', 'id': 'calendario', 'titulo': 'Datas do Enem 2026 e dos vestibulares 2027', 'rotulos': True,
             'colunas': ['Vestibular', 'Etapa', 'Data'], 'coluna_fonte': 'Fonte oficial', 'linhas': linhas},
        ],
        'chamada': {'titulo': 'Use o tempo até a prova', 'texto': CHAMADA_PADRAO},
    }


# ---------- 2 e 3. Notas de corte ----------
def numero(valor, decimal=False):
    if valor is None:
        return None
    return f'{valor:.1f}'.replace('.', ',') if decimal else str(valor)


def fuvest(coleta):
    d = ler(coleta / 'notas-de-corte/fuvest.json')
    doc = d['documento']
    if d.get('nao_lidos'):
        raise Erro('Fuvest: a coleta tem linhas não lidas; acrescente o aviso no importador')
    modalidades = ['Ampla Concorrência', 'Candidatos de Escola Pública', 'Candidatos de Escola Pública − Grupo PPI']
    linhas = []
    for curso in d['cursos']:
        if list(curso['modalidades']) != modalidades:
            raise Erro(f'Fuvest: modalidades diferentes em {curso["nome"]}')
        valores = [{'texto': curso['nome'], 'nota': f'código {curso["codigo"]}'}]
        valores += [numero(curso['modalidades'][m]) or 'sem nota no PDF' for m in modalidades]
        linhas.append({'valores': valores, 'fonte': doc['endereco'], 'texto_fonte': 'PDF da Fuvest', 'conferido_em': doc['data_de_conferencia']})
    sem = [f'{s["curso"]} ({s["modalidade"].replace("Candidatos de Escola Pública − Grupo PPI", "escola pública, grupo PPI")})' for s in d['sem_corte_no_pdf']]
    return {
        'tipo': 'leitura', 'endereco': '/notas-de-corte/fuvest/',
        'titulo': 'Notas de corte da Fuvest 2027 por carreira e modalidade',
        'descricao': f'Nota do último convocado para a 2ª fase da Fuvest 2027 nas {len(linhas)} carreiras da USP, em ampla concorrência, escola pública e grupo PPI, com o PDF oficial.',
        'migalha': 'Notas de corte da Fuvest', 'h1': 'Notas de corte da Fuvest 2027',
        'apoio': f'A nota do último convocado para a 2ª fase em cada uma das {len(linhas)} carreiras da USP, nas três modalidades. Os números vêm do PDF oficial da Fuvest.',
        'tom': 'mar', 'atualizada_em': doc['data_de_conferencia'], 'menu': True, 'sumario': True, 'script': 'notas-de-corte.js',
        'relacionadas': ['/notas-de-corte/unicamp/', '/calendario-vestibulares/', '/provas-anteriores/'],
        'blocos': [
            {'tipo': 'texto', 'titulo': 'O que é a nota de corte da Fuvest',
             'paragrafos': [
                 'É a nota do último candidato chamado para a 2ª fase do Vestibular Fuvest 2027, em cada carreira e em cada modalidade. Quem fez essa nota ou mais na 1ª fase foi convocado. No PDF, é a coluna dos pontos mínimos dos convocados.',
                 'As modalidades são as do PDF: ampla concorrência, candidatos de escola pública e candidatos de escola pública do grupo PPI (pretos, pardos e indígenas). Quem pode concorrer em cada uma está no edital da Fuvest.',
                 'O PDF não diz qual é a nota máxima da 1ª fase. Por isso o PU mostra o número como a Fuvest publicou, sem converter em porcentagem.',
                 f'[Abrir o PDF oficial da Fuvest]({doc["endereco"]}).']},
            {'tipo': 'dados', 'id': 'cortes', 'titulo': 'Nota de corte por carreira', 'rotulos': True, 'filtro': 'Procure sua carreira',
             'nota': [f'{len(linhas)} carreiras do Vestibular Fuvest 2027, 1ª fase.'] + ([f'Sem nota no PDF: {", ".join(sem)}. O PDF traz um traço no lugar do número.'] if sem else []),
             'colunas': ['Carreira', 'Ampla concorrência', 'Escola pública', 'Escola pública, grupo PPI'], 'coluna_fonte': 'Fonte oficial', 'linhas': linhas},
        ],
        'chamada': {'titulo': 'Treine para a próxima Fuvest', 'texto': 'As questões objetivas das provas anteriores da Fuvest estão no PU, uma por vez, com o gabarito oficial. O que você errar volta para a revisão. É gratuito.'},
    }


COLUNAS_UNICAMP = ['Não cotista PAAIS 0', 'Não cotista PAAIS 20', 'Não cotista PAAIS 40', 'Não cotista PAAIS 60',
                   'Cotista PAAIS 0', 'Cotista PAAIS 20', 'Cotista PAAIS 40', 'Cotista PAAIS 60']


def unicamp(coleta):
    d = ler(coleta / 'notas-de-corte/unicamp.json')
    doc, musica = d['documento'], d['cursos_musica']
    linhas = []
    for curso in d['cursos']:
        if list(curso['modalidades']) != COLUNAS_UNICAMP:
            raise Erro(f'Unicamp: colunas diferentes em {curso["nome"]}')
        nome = {'texto': curso['nome'], 'nota': 'treineiros'} if curso.get('tipo') == 'treineiros' else curso['nome']
        valores = [nome] + [numero(curso['modalidades'][c]) or 'sem valor' for c in COLUNAS_UNICAMP]
        linhas.append((sem_acento(curso['nome']), {'valores': valores, 'fonte': doc['endereco'], 'texto_fonte': 'PDF da Comvest',
                                                    'conferido_em': doc['data_de_conferencia']}))
    for nao_lido in d['nao_lidos']:
        nome = re.match(r'\s*(.+?)\s{2,}\d', nao_lido['linha_crua']).group(1).strip()
        linhas.append((sem_acento(nome), {'valores': [nome], 'aviso': 'Não lido no PDF, ver o documento oficial',
                                          'fonte': doc['endereco'], 'texto_fonte': 'PDF da Comvest'}))
    linhas = [l for _, l in sorted(linhas, key=lambda par: par[0])]
    linhas_musica = []
    for curso in musica['cursos']:
        valores = [curso['nome']] + [numero(curso['modalidades'].get(c), decimal=True) or 'sem nota no PDF' for c in ('Não cotista', 'Cotista')]
        linhas_musica.append({'valores': valores, 'fonte': musica['documento']['endereco'], 'texto_fonte': 'PDF da Comvest (música)',
                              'conferido_em': musica['documento']['data_de_conferencia']})
    cursos = sum(1 for c in d['cursos'] if c.get('tipo') != 'treineiros') + len(d['nao_lidos'])
    return {
        'tipo': 'leitura', 'endereco': '/notas-de-corte/unicamp/',
        'titulo': 'Notas de corte da Unicamp 2027 por curso: acertos para a 2ª fase',
        'descricao': 'Número de acertos do último convocado para a 2ª fase da Unicamp 2027 em cada curso, para cotistas, não cotistas e cada faixa do PAAIS, com o PDF oficial.',
        'migalha': 'Notas de corte da Unicamp', 'h1': 'Notas de corte da Unicamp 2027',
        'apoio': 'Quantas questões o último convocado para a 2ª fase acertou em cada curso, separado por cota e por bônus do PAAIS. Os números vêm do PDF oficial da Comvest.',
        'tom': 'ipe', 'atualizada_em': doc['data_de_conferencia'], 'menu': True, 'sumario': True, 'script': 'notas-de-corte.js',
        'relacionadas': ['/notas-de-corte/fuvest/', '/calendario-vestibulares/', '/obras-obrigatorias/'],
        'blocos': [
            {'tipo': 'texto', 'titulo': 'O que é a nota de corte da Unicamp',
             'paragrafos': [
                 'Na Unicamp, o corte da 1ª fase vem como número de acertos: quantas questões o último candidato chamado para a 2ª fase acertou, em cada curso e em cada grupo. É contagem de questões certas, sem conversão em nota.',
                 'O PDF não diz quantas questões a prova tinha nem qual é a nota máxima. Por isso o PU mostra o número como a Comvest publicou.',
                 f'[Abrir o PDF oficial da Comvest]({doc["endereco"]}).']},
            {'tipo': 'texto', 'id': 'colunas', 'no_sumario': True, 'titulo': 'Cotista e PAAIS: o que cada coluna quer dizer',
             'paragrafos': [
                 f'Cotista é quem optou pela reserva de vagas para candidatos autodeclarados pretos e pardos. Não cotista é quem não optou. Fonte: [Manual do Ingresso do Vestibular Unicamp 2027]({MANUAL_UNICAMP}), página 13.',
                 'PAAIS é o Programa de Ação Afirmativa e Inclusão Social, um bônus somado à nota da 1ª fase de quem estudou em escola pública no Brasil: 20 pontos para quem cursou o Ensino Fundamental II em escola pública, 40 para quem cursou todo o Ensino Médio em escola pública e 60 para quem cursou os dois. PAAIS 0 é o grupo sem esse bônus. A participação é opcional e se marca na inscrição.',
                 f'Fonte do PAAIS: [Manual do Ingresso do Vestibular Unicamp 2027]({MANUAL_UNICAMP}), página 16. As letras entre parênteses depois do nome do curso estão como no PDF.']},
            {'tipo': 'dados', 'id': 'cortes', 'titulo': 'Acertos do último convocado, por curso', 'largo': True, 'filtro': 'Procure seu curso',
             'nota': [f'{cursos} cursos e as linhas de treineiros do Vestibular Unicamp 2027, 1ª fase. No celular, arraste a tabela para o lado para ver todas as colunas.',
                      '"Sem valor": o PDF traz um traço nessa coluna. Uma linha não foi lida com segurança no PDF e aparece com o aviso; confira no documento oficial.'],
             'colunas': ['Curso'] + COLUNAS_UNICAMP, 'coluna_fonte': 'Fonte oficial', 'linhas': linhas},
            {'tipo': 'dados', 'id': 'musica', 'titulo': 'Cursos de música: outra escala', 'rotulos': True,
             'nota': ['O corte dos cursos de música vem em outro PDF da Comvest e em outra escala: uma nota com casa decimal, no lugar do número de acertos. Por isso fica numa tabela à parte. Não compare estes números com os da tabela de cima. O PDF não diz a nota máxima.',
                      f'{len(linhas_musica)} cursos de música. "Sem nota no PDF": o documento não traz nota nesse grupo.'],
             'colunas': ['Curso', 'Não cotista', 'Cotista'], 'coluna_fonte': 'Fonte oficial', 'linhas': linhas_musica},
        ],
        'chamada': {'titulo': 'Treine para a próxima Unicamp', 'texto': 'As questões objetivas das provas anteriores da Unicamp estão no PU, uma por vez, com o gabarito oficial. O que você errar volta para a revisão. É gratuito.'},
    }


# ---------- 4. Obras obrigatórias ----------
def obra_fuvest(item):
    achado = re.fullmatch(r'(.+?) \((\d{4})\) – (.+)', item['trecho_literal'])
    if not achado:
        raise Erro(f'Fuvest: trecho fora do padrão: {item["trecho_literal"]}')
    return {'titulo': achado.group(1), 'ano': achado.group(2), 'autor': achado.group(3)}


def obra_unicamp(item):
    partes = [p.strip() for p in item['trecho_literal'].split('|')]
    return {'autor': partes[0], 'titulo': partes[1], 'extensao': partes[2] if len(partes) > 2 else ''}


def chave_obra(titulo):
    return sem_acento(re.sub(r'\s+', ' ', titulo.replace('M.J.', 'M. J.')))


def texto_livre(item, titulo):
    for chave, link in TEXTO_LIVRE.items():
        if chave_obra(chave) == chave_obra(titulo) or chave_obra(chave) == chave_obra(item['titulo']):
            return dict(link)
    if item['titulo'] in DOMINIO_PUBLICO_SEM_LINK:
        return 'Em domínio público. O PU ainda não achou um link oficial.'
    return 'Sem texto livre'


def obras(coleta):
    d = ler(coleta / 'obras/dados.json')
    blocos_ano, mudancas = {}, {}
    for banca in ('fuvest', 'unicamp'):
        for ano in ('2027', '2028'):
            linhas = []
            for item in d[banca][ano]:
                if any(r in str(item.get('texto_livre_url', '')) for r in LINKS_RECUSADOS) and item['titulo'] not in TEXTO_LIVRE:
                    raise Erro(f'{item["titulo"]}: só há link recusado; acrescente o ajuste')
                if banca == 'fuvest':
                    o = obra_fuvest(item)
                    valores = [f'{o["titulo"]} ({o["ano"]})', o['autor'], texto_livre(item, o['titulo'])]
                else:
                    o = obra_unicamp(item)
                    if o['extensao'] == 'Obra completa' and chave_obra(o['titulo']) == chave_obra('O direito à literatura'):
                        extensao = {'texto': 'Obra completa, pela tabela oficial',
                                    'nota': 'O comunicado da Comvest chama o texto de capítulo de Vários Escritos, de Antonio Candido.'}
                    elif o['extensao'] == 'Obra completa':
                        extensao = 'Obra completa'
                    else:
                        extensao = 'Textos escolhidos (lista na página oficial)'
                    valores = [o['titulo'], o['autor'], item['genero'], extensao, texto_livre(item, o['titulo'])]
                linhas.append({'valores': valores, 'fonte': item['fonte_url'], 'conferido_em': item['conferido_em'],
                               'texto_fonte': 'Lista da Fuvest' if banca == 'fuvest' else 'Lista da Comvest', '_titulo': o['titulo'], '_autor': o['autor']})
            blocos_ano[(banca, ano)] = linhas
        # O que entra e o que sai em 2028: cálculo do PU a partir das duas listas oficiais.
        t27 = {chave_obra(l['_titulo']): l['_titulo'] for l in blocos_ano[(banca, '2027')]}
        t28 = {chave_obra(l['_titulo']): l['_titulo'] for l in blocos_ano[(banca, '2028')]}
        mudancas[banca] = ([t28[k] for k in t28 if k not in t27], [t27[k] for k in t27 if k not in t28])
        coleta_entra = sorted(chave_obra(x['titulo']) for x in d[banca]['entram_em_2028'])
        coleta_sai = sorted(chave_obra(x['titulo']) for x in d[banca]['saem_em_2028'])
        if sorted(map(chave_obra, mudancas[banca][0])) != coleta_entra or sorted(map(chave_obra, mudancas[banca][1])) != coleta_sai:
            raise Erro(f'{banca}: o cálculo de entra e sai não bate com o da coleta')
    # Autoras e autores nas duas listas do mesmo ano (com obras diferentes), conferido contra o cálculo da coleta.
    em_comum = {}
    for ano in ('2027', '2028'):
        autores = [{sem_acento(l['_autor']): l['_autor'] for l in blocos_ano[(b, ano)]} for b in ('fuvest', 'unicamp')]
        obras_iguais = {chave_obra(l['_titulo']) for l in blocos_ano[('fuvest', ano)]} & {chave_obra(l['_titulo']) for l in blocos_ano[('unicamp', ano)]}
        em_comum[ano] = sorted(autores[0][k] for k in autores[0] if k in autores[1])
        if obras_iguais or sorted(map(sem_acento, em_comum[ano])) != sorted(map(sem_acento, d['nas_duas'][ano]['mesma_autora_ou_autor_obras_diferentes'])):
            raise Erro(f'{ano}: obras ou autores em comum não batem com a coleta')
    for linhas in blocos_ano.values():
        for l in linhas:
            del l['_titulo'], l['_autor']
    colunas = {'fuvest': ['Obra', 'Autora ou autor', 'Texto livre'],
               'unicamp': ['Obra', 'Autora ou autor', 'Gênero', 'O que ler', 'Texto livre']}

    def par(ano):
        return {'tipo': 'par', 'id': f'ano-{ano}', 'titulo': f'Vestibular {ano}',
                'blocos': [{'tipo': 'dados', 'id': f'{b}-{ano}', 'titulo': f'{"Fuvest (USP)" if b == "fuvest" else "Unicamp"} {ano}', 'rotulos': True,
                            'colunas': colunas[b], 'coluna_fonte': 'Fonte oficial', 'linhas': blocos_ano[(b, ano)]} for b in ('fuvest', 'unicamp')]}

    def lista(titulos):
        return ', '.join(titulos[:-1]) + ' e ' + titulos[-1] if len(titulos) > 1 else titulos[0]

    (fe, fs), (ue, us) = mudancas['fuvest'], mudancas['unicamp']
    unesp = d['unesp']
    if unesp['tem_lista'] != 'nao_encontrado':
        raise Erro('Unesp: a coleta mudou; reveja o aviso da página')
    return {
        'tipo': 'leitura', 'endereco': '/obras-obrigatorias/',
        'titulo': 'Obras obrigatórias da Fuvest e da Unicamp 2027 e 2028',
        'descricao': 'Lista de leituras obrigatórias da Fuvest e da Unicamp para 2027 e 2028, lado a lado, com o que entra e o que sai e o link do texto livre das obras em domínio público.',
        'migalha': 'Obras obrigatórias', 'h1': 'Obras obrigatórias da Fuvest e da Unicamp',
        'apoio': 'As leituras de 2027 e de 2028 das duas listas oficiais, lado a lado. Quando a obra está em domínio público e o PU achou o texto numa biblioteca oficial, a linha leva ao PDF.',
        'tom': 'goiaba', 'atualizada_em': d['coletado_em'], 'menu': True, 'sumario': True,
        'relacionadas': ['/calendario-vestibulares/', '/temas-de-redacao-enem/', '/provas-anteriores/'],
        'blocos': [
            {'tipo': 'texto', 'titulo': 'Como usar estas listas',
             'paragrafos': [
                 f'Os títulos e os nomes estão escritos como nas páginas oficiais: [lista da Fuvest de 2026 a 2029]({LISTA_FUVEST}) e [lista da Unicamp de 2027 a 2029]({LISTA_UNICAMP}). Antes de comprar um livro, confira a edição e os trechos pedidos na página oficial.',
                 'Esta página não traz resumo de obra. A leitura é sua: o PU só diz onde achar a lista e o texto.',
                 'A Fuvest não informa o gênero de cada obra, então a coluna de gênero aparece só na Unicamp.']},
            par('2027'), par('2028'),
            {'tipo': 'texto', 'id': 'mudancas', 'no_sumario': True, 'titulo': 'O que entra e o que sai em 2028',
             'paragrafos': [
                 'O PU comparou as listas oficiais de 2027 e de 2028 de cada instituição. O resultado abaixo é esse cálculo, não um texto das bancas.',
                 f'Fuvest: entram {lista(fe)}; saem {lista(fs)}.',
                 f'Unicamp: entram {lista(ue)}; saem {lista(us)}.',
                 f'Nenhuma obra aparece nas duas listas no mesmo ano. Com livros diferentes, {lista(em_comum["2027"])} está nas duas instituições em 2027, e {lista(em_comum["2028"])} em 2028.']},
            {'tipo': 'aviso', 'id': 'unesp', 'titulo': 'Unesp: lista não encontrada em fonte oficial',
             'paragrafos': [
                 'O PU leu a [página do vestibular da Unesp](https://vestibular.unesp.br/) e não achou lista de obras obrigatórias. O Manual do Candidato 2027 e o site da Vunesp não abriram na conferência.',
                 'Isso não quer dizer que a Unesp não tem lista: quer dizer que o PU ainda não confirmou numa fonte oficial. Confira no Manual do Candidato da Unesp.']},
        ],
        'chamada': {'titulo': 'Treine as outras matérias no PU', 'texto': CHAMADA_PADRAO},
    }


# ---------- 5. Temas de redação ----------
NOMES_PROPRIOS = {'brasil': 'Brasil'}
# Anos em que o caderno escreve o tema em caixa alta (2006, 2012) ou com maiúscula em cada palavra (1998, 2010).
CAIXA_DO_CADERNO = {1998, 2006, 2010, 2012}


def caixa(tema, ano):
    """Só a apresentação das maiúsculas: nos anos de CAIXA_DO_CADERNO o tema fica com maiúscula só no começo e nos
    nomes próprios (números romanos mantidos), e em todos a primeira letra fica maiúscula. As palavras não mudam."""
    if ano in CAIXA_DO_CADERNO:
        def palavra(achado):
            p = achado.group(0)
            if re.fullmatch(r'[IVXLC]+', p):  # século XXI
                return p
            return NOMES_PROPRIOS.get(p.lower(), p.lower())
        tema = re.sub(r'\w+', palavra, tema)
    return tema[0].upper() + tema[1:]


def temas(coleta):
    d = ler(coleta / 'temas-redacao/dados.json')
    linhas = []
    anos = sorted(d['edicoes'], key=lambda t: -t['ano'])
    for t in anos:
        if t['aplicacao'] != 'regular':
            continue
        ano = str(t['ano'])
        if t['tema'] == 'nao_encontrado':
            proposta = re.search(r'Proposta literal[^"]*"([^"]+)"', t['motivo_nao_encontrado'])
            if not proposta:
                raise Erro(f'{ano}: sem proposta literal na coleta')
            tema = {'texto': f'Sem título. A proposta pedia: "{proposta.group(1)}"',
                    'nota': f'Em {ano} a prova não deu título ao tema. A proposta partia do texto "A máquina de chuva da Amazônia".'}
        else:
            original = t['tema']
            tema = caixa(original, t['ano'])
            if tema.lower() != original.lower():
                raise Erro(f'{ano}: a padronização mudou palavras')
        if t['prova_url'] == 'nao_encontrado':
            prova = 'O Inep ainda não publicou o caderno desta prova'
        else:
            prova = {'texto': f'Provas e gabaritos de {ano} no Inep', 'link': t['prova_url']}
        if t.get('tema_pagina_pdf'):
            texto_fonte = f'Caderno do Inep, página {t["tema_pagina_pdf"]}'
        else:
            texto_fonte = 'Notícia oficial do Inep'
        linhas.append({'valores': [ano, tema, prova], 'fonte': t['tema_fonte_url'], 'texto_fonte': texto_fonte, 'conferido_em': t['conferido_em']})
    primeiro, ultimo = min(t['ano'] for t in anos), max(t['ano'] for t in anos)
    return {
        'tipo': 'leitura', 'endereco': '/temas-de-redacao-enem/',
        'titulo': f'Temas de redação do Enem de {primeiro} a {ultimo}',
        'descricao': f'Todos os temas de redação do Enem de {primeiro} a {ultimo}, ano a ano, com o link da prova no Inep e a fonte de cada tema. Para treinar a escrita com temas reais.',
        'migalha': 'Temas de redação do Enem', 'h1': 'Temas de redação do Enem',
        'apoio': f'O tema de cada ano, de {ultimo} até {primeiro}, tirado do caderno oficial do Inep. Use para treinar a escrita com propostas que já caíram.',
        'tom': 'boia', 'atualizada_em': d['coletado_em'], 'menu': True, 'sumario': True,
        'relacionadas': ['/provas-anteriores/', '/calendario-vestibulares/', '/obras-obrigatorias/'],
        'blocos': [
            {'tipo': 'texto', 'titulo': 'Antes de começar',
             'paragrafos': [
                 'O PU não corrige redação. Esta página serve para você conhecer os temas e treinar a escrita por conta própria, com um professor ou com colegas.',
                 'Cada tema foi lido no caderno de prova do Inep, na página indicada na linha. Em 2026 o caderno ainda não saiu, então o tema vem da notícia oficial do Inep. A lista traz só a aplicação principal de cada ano, sem reaplicação nem a prova para pessoas privadas de liberdade (PPL).',
                 'Alguns cadernos escrevem o tema todo em maiúsculas. Aqui todos aparecem com maiúscula só no começo e nos nomes, sem mudar nenhuma palavra.']},
            {'tipo': 'dados', 'id': 'temas', 'titulo': f'Temas de {ultimo} a {primeiro}', 'rotulos': True,
             'colunas': ['Ano', 'Tema', 'Prova'], 'coluna_fonte': 'Fonte do tema', 'linhas': linhas},
        ],
        'chamada': {'titulo': 'Treine as questões objetivas do Enem', 'texto': 'A redação fica com você. As questões objetivas do Enem de 2021 a 2025 estão no PU, uma por vez, com o gabarito oficial. É gratuito.'},
    }


PAGINAS = {'calendario-vestibulares.json': calendario, 'notas-de-corte-fuvest.json': fuvest, 'notas-de-corte-unicamp.json': unicamp,
           'obras-obrigatorias.json': obras, 'temas-de-redacao-enem.json': temas}


def montar(coleta):
    return {nome: json.dumps(funcao(Path(coleta)), ensure_ascii=False, indent=1) + '\n' for nome, funcao in PAGINAS.items()}


def principal():
    argumentos = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    argumentos.add_argument('--coleta', required=True, help='pasta da coleta (calendario/, notas-de-corte/, obras/, temas-redacao/)')
    argumentos.add_argument('--conferir', action='store_true')
    a = argumentos.parse_args()
    try:
        arquivos = montar(a.coleta)
    except (Erro, KeyError, ValueError) as erro:
        print(f'RECUSADO  {erro}', file=sys.stderr)
        return 2
    if a.conferir:
        diferentes = [n for n, t in arquivos.items() if not (CONTEUDO / n).is_file() or (CONTEUDO / n).read_text(encoding='utf-8') != t]
        print('Conteúdo igual à coleta.' if not diferentes else 'Diferente da coleta: ' + ', '.join(diferentes))
        return 1 if diferentes else 0
    for nome, texto in arquivos.items():
        (CONTEUDO / nome).write_text(texto, encoding='utf-8')
    print(f'{len(arquivos)} arquivos gravados em {CONTEUDO}: ' + ', '.join(arquivos))
    print('Agora rode python3 paginas/gerar.py e python3 tests/paginas.py.')
    return 0


if __name__ == '__main__':
    sys.exit(principal())
