#!/usr/bin/env python3
"""Gerador das páginas públicas do PU (endereços próprios para a busca).

Lê um arquivo JSON por página em paginas/conteudo/, aplica o molde comum (paginas/molde.html) e grava, na raiz do
repositório (que o GitHub Pages serve): uma pasta com index.html por página de leitura, a porta /criar-conta/
(a entrada já no cadastro), 404.html, robots.txt, sitemap.xml e o bloco de dados estruturados dos dois index.html.

Só biblioteca padrão. Uso:
  python3 paginas/gerar.py                  grava na raiz do repositório
  python3 paginas/gerar.py --saida PASTA    grava noutra pasta (teste)
  python3 paginas/gerar.py --conferir       só confere se o que está no repositório é o que o gerador grava
  python3 paginas/gerar.py --marcar-a-confirmar   grava mesmo com dado sem fonte, com o aviso "Dado a confirmar" na página

Regra dado-inventado: todo dado de um bloco "dados" precisa de fonte (endereço https oficial) e de data de conferência.
Sem isso o gerador recusa e não grava nada, a não ser com --marcar-a-confirmar.

Dominique-Oliveira-Claude🤖🧡, 17/11/2026.
"""
import argparse
import datetime
import filecmp
import hashlib
import html
import json
import re
import sys
import tempfile
from pathlib import Path
from string import Template

RAIZ = Path(__file__).resolve().parent.parent
PASTA = Path(__file__).resolve().parent
DOMINIO = 'https://pu.gingamidia.com'
NOME = 'Pé na Universidade (PU)'
TIPOS = {'entrada', 'cadastro', 'leitura', 'erro'}
TONS = {'mar', 'boia', 'sol', 'ipe', 'goiaba'}
MARCA_INICIO, MARCA_FIM = '<!-- dados-estruturados:inicio -->', '<!-- dados-estruturados:fim -->'
LINK = re.compile(r'\[([^\]]+)\]\(([^)\s]+)\)')
DATA = re.compile(r'\d{4}-\d{2}-\d{2}')
SCRIPT = re.compile(r'[a-z0-9-]+\.js')
# Módulo compartilhado com as telas de dentro (ex.: a conta do simulador de nota), servido pelo Pages em /app/public/.
MODULO = re.compile(r'/app/public/[a-z0-9-]+\.js')
MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']


class Recusa(Exception):
    pass


def e(texto):
    return html.escape(str(texto), quote=True)


def data_br(iso):
    return datetime.date.fromisoformat(iso).strftime('%d/%m/%Y')


def endereco_valido(url):
    return url.startswith('https://') or (url.startswith('/') and not url.startswith('//'))


def texto_com_links(texto):
    """Escapa o texto e troca [rótulo](endereço) por link. Só https ou caminho do próprio site."""
    saida, fim = [], 0
    for achado in LINK.finditer(texto):
        rotulo, url = achado.groups()
        if not endereco_valido(url):
            raise Recusa(f'link com endereço não aceito: {url}')
        saida += [e(texto[fim:achado.start()]), f'<a href="{e(url)}">{e(rotulo)}</a>']
        fim = achado.end()
    return ''.join(saida + [e(texto[fim:])])


def absoluto(endereco):
    return DOMINIO + endereco


# ---------- Leitura e conferência do conteúdo ----------
def carregar(pasta_conteudo):
    paginas = []
    for arquivo in sorted(Path(pasta_conteudo).glob('*.json')):
        pagina = json.loads(arquivo.read_text(encoding='utf-8'))
        pagina['_arquivo'] = arquivo.name
        if pagina.get('tipo') not in TIPOS:
            raise Recusa(f'{arquivo.name}: tipo deve ser um de {sorted(TIPOS)}')
        exigidos = ['endereco', 'migalha'] + {'entrada': ['atualizada_em'], 'cadastro': ['titulo', 'descricao'],
                                              'leitura': ['titulo', 'descricao', 'h1', 'apoio', 'atualizada_em', 'blocos'],
                                              'erro': ['titulo', 'descricao', 'h1', 'apoio']}[pagina['tipo']]
        faltam = [c for c in exigidos if not pagina.get(c)]
        if faltam:
            raise Recusa(f'{arquivo.name}: faltam os campos {faltam}')
        if pagina['tipo'] in ('leitura', 'cadastro') and not re.fullmatch(r'/[a-z0-9-]+(/[a-z0-9-]+)*/', pagina['endereco']):
            raise Recusa(f'{arquivo.name}: endereço deve ser /nome-da-pasta/ em minúsculas, sem acento')
        if pagina.get('tom', 'mar') not in TONS:
            raise Recusa(f'{arquivo.name}: tom deve ser um de {sorted(TONS)}')
        if pagina.get('atualizada_em') and not DATA.fullmatch(pagina['atualizada_em']):
            raise Recusa(f'{arquivo.name}: atualizada_em no formato AAAA-MM-DD')
        if 'script' in pagina:
            # Script só do próprio site e só em página de leitura que o declara: nome.js da pasta paginas/ ou,
            # numa lista, também um módulo de /app/public/ que as telas de dentro já usam (carregado na ordem da lista).
            lista = pagina['script'] if isinstance(pagina['script'], list) else [pagina['script']]
            if pagina['tipo'] != 'leitura' or not lista or not all(isinstance(s, str) and (SCRIPT.fullmatch(s) or MODULO.fullmatch(s)) for s in lista):
                raise Recusa(f'{arquivo.name}: script deve ser nome-do-arquivo.js da pasta paginas/ (ou /app/public/nome.js numa lista), só em página de leitura')
            for s in lista:
                if not arquivo_do_script(s).is_file():
                    raise Recusa(f'{arquivo.name}: script {s} não existe')
        paginas.append(pagina)
    # Ordem do menu e do mapa: a entrada, as páginas de leitura (pelo nome do arquivo), a porta do cadastro e a 404.
    paginas.sort(key=lambda p: ['entrada', 'leitura', 'cadastro', 'erro'].index(p['tipo']))
    tipos = [p['tipo'] for p in paginas]
    for tipo in ('entrada', 'cadastro', 'erro'):
        if tipos.count(tipo) != 1:
            raise Recusa(f'precisa de exatamente uma página do tipo {tipo}')
    enderecos = [p['endereco'] for p in paginas]
    if len(set(enderecos)) != len(enderecos):
        raise Recusa('dois arquivos com o mesmo endereço')
    for pagina in paginas:
        for endereco in pagina.get('relacionadas', []):
            if endereco not in enderecos or endereco == pagina['endereco']:
                raise Recusa(f"{pagina['_arquivo']}: página relacionada que não existe: {endereco}")
    return paginas


def scripts_de(pagina):
    """Os scripts da página na ordem: nome.js (pasta paginas/) ou /app/public/nome.js (módulo das telas de dentro)."""
    if not pagina.get('script'):
        return []
    return pagina['script'] if isinstance(pagina['script'], list) else [pagina['script']]


def arquivo_do_script(nome):
    return RAIZ / nome.lstrip('/') if nome.startswith('/') else PASTA / nome


def endereco_do_script(nome):
    return nome if nome.startswith('/') else '/paginas/' + nome


def blocos_de_dados(pagina):
    """Os blocos 'dados' da página, inclusive os que estão dentro de um bloco 'par'."""
    for bloco in pagina.get('blocos', []):
        if bloco.get('tipo') == 'dados':
            yield bloco
        elif bloco.get('tipo') == 'par':
            yield from (b for b in bloco.get('blocos', []) if b.get('tipo') == 'dados')


def links_das_celulas(linha):
    return [v['link'] for v in linha.get('valores', []) if isinstance(v, dict) and v.get('link')]


def problemas_de_fonte(pagina, hoje):
    """Lista os dados sem fonte oficial ou sem data de conferência válida.
    Linha de aviso (campo 'aviso') não é dado: mostra que a informação não foi achada em fonte oficial."""
    problemas = []
    for bloco in blocos_de_dados(pagina):
        for n, linha in enumerate(bloco.get('linhas', []), 1):
            onde = f"{pagina['_arquivo']}, bloco {bloco.get('id')}, linha {n}"
            extras = linha.get('outras_fontes', []) + links_das_celulas(linha)
            if any(not str(u).startswith('https://') for u in extras):
                problemas.append(f'{onde}: link de célula ou fonte extra sem https')
            if linha.get('aviso'):
                if linha.get('fonte') and not linha['fonte'].startswith('https://'):
                    problemas.append(f'{onde}: aviso com link sem https')
                continue
            fonte, conferido = linha.get('fonte', ''), linha.get('conferido_em', '')
            if not fonte.startswith('https://'):
                problemas.append(f'{onde}: sem fonte https')
            if not DATA.fullmatch(conferido):
                problemas.append(f'{onde}: sem data de conferência (AAAA-MM-DD)')
            elif datetime.date.fromisoformat(conferido) > hoje:
                problemas.append(f'{onde}: data de conferência no futuro')
            if linha.get('contagem') and not DATA.fullmatch(linha['contagem']):
                problemas.append(f'{onde}: contagem no formato AAAA-MM-DD')
            if linha.get('contagem') and linha.get('artigo_contagem') not in ('a', 'o'):
                problemas.append(f'{onde}: contagem sem artigo_contagem ("a" ou "o")')
    return problemas


# ---------- Partes comuns ----------
def migalhas_de(pagina, inicio):
    itens = [inicio] if pagina['tipo'] != 'entrada' else []
    return itens + [pagina]


def dados_estruturados(pagina, inicio):
    organizacao = {'@type': 'Organization', '@id': absoluto('/#organizacao'), 'name': NOME, 'alternateName': 'PU',
                   'url': absoluto('/'), 'logo': absoluto('/icones/pu-512.png')}
    site = {'@type': 'WebSite', '@id': absoluto('/#site'), 'name': NOME, 'url': absoluto('/'), 'inLanguage': 'pt-BR',
            'publisher': {'@id': absoluto('/#organizacao')}}
    itens = [{'@type': 'ListItem', 'position': i, 'name': p['migalha'], 'item': absoluto(p['endereco'])}
             for i, p in enumerate(migalhas_de(pagina, inicio), 1)]
    if pagina['tipo'] == 'erro':
        del itens[-1]['item']
    graficos = [organizacao, site, {'@type': 'BreadcrumbList', 'itemListElement': itens}]
    texto = json.dumps({'@context': 'https://schema.org', '@graph': graficos}, ensure_ascii=False, separators=(',', ':'))
    return texto.replace('</', '<\\/')


def bloco_jsonld(pagina, inicio):
    return f'{MARCA_INICIO}<script type="application/ld+json">{dados_estruturados(pagina, inicio)}</script>{MARCA_FIM}'


def meta_do_index(texto, chave):
    achado = re.search(r'<meta (?:name|property)="' + re.escape(chave) + r'" content="([^"]*)"', texto)
    if not achado:
        raise Recusa(f'index.html sem {chave}')
    return html.unescape(achado.group(1))


# ---------- Página de leitura e 404 ----------
def data_por_extenso(iso):
    d = datetime.date.fromisoformat(iso)
    dia = '1º' if d.day == 1 else d.day  # "1º de novembro", como se escreve data em português
    return f'{dia} de {MESES[d.month - 1]} de {d.year}'


def id_do_titulo(bloco):
    return 't-' + bloco.get('id', re.sub(r'[^a-z0-9]+', '-', bloco.get('titulo', 'bloco').lower()).strip('-'))


def celula(valor):
    """Valor de célula: texto simples, ou {"texto", "link" (https), "nota"}. Nada vira HTML sem escapar."""
    if isinstance(valor, dict):
        texto = e(valor.get('texto', ''))
        if valor.get('link'):
            if not str(valor['link']).startswith('https://'):
                raise Recusa(f'link de célula sem https: {valor["link"]}')
            texto = f'<a href="{e(valor["link"])}">{texto}</a>'
        if valor.get('nota'):
            texto += f' <small>{texto_com_links(valor["nota"])}</small>'
        return texto
    if valor is None:
        raise Recusa('célula vazia: escreva o texto que a página deve mostrar (ex.: "sem valor no PDF")')
    return e(valor)


def tabela_de(bloco, marcar, pagina, nivel='h2'):
    """Título, nota, campo de busca (opcional) e a tabela de um bloco 'dados'.
    Opções do bloco: largo (tabela com rolagem lateral própria no celular, em vez de cartões),
    rotulos (no celular, cada valor do cartão leva o nome da coluna), filtro (campo de busca de linhas, ligado
    pelo script da página; sem script fica escondido e a tabela aparece inteira)."""
    titulo_id = id_do_titulo(bloco)
    colunas = bloco['colunas'] + [bloco.get('coluna_fonte', 'Fonte')]
    topo = ''.join(f'<th scope="col">{e(c)}</th>' for c in colunas)
    linhas = []
    hoje = datetime.date.today()
    for linha in bloco['linhas']:
        valores = linha['valores']
        id_linha = f' id="{e(linha["id"])}"' if linha.get('id') else ''
        if linha.get('aviso'):
            # Linha sem dado oficial: só os valores descritivos e o aviso no lugar do resto, sem data-dado.
            if not 1 <= len(valores) < len(bloco['colunas']):
                raise Recusa(f"{pagina['_arquivo']}, bloco {bloco.get('id')}: linha de aviso precisa de menos valores que colunas")
            celulas = ''.join(f'<td data-rotulo="{e(c)}">{celula(v)}</td>' for c, v in zip(bloco['colunas'], valores))
            link = ''
            if linha.get('fonte'):
                link = f' <a href="{e(linha["fonte"])}">{e(linha.get("texto_fonte", "ver o documento oficial"))}</a>'
            resto = len(colunas) - len(valores)
            linhas.append(f'<tr data-aviso{id_linha}>{celulas}<td class="sem-dado" colspan="{resto}" data-rotulo="{e(colunas[len(valores)])}">'
                          f'<strong class="aviso-dado">{e(linha["aviso"])}</strong>{link}</td></tr>')
            continue
        if len(valores) != len(bloco['colunas']):
            raise Recusa(f"{pagina['_arquivo']}, bloco {bloco.get('id')}: linha com {len(valores)} valores para {len(bloco['colunas'])} colunas")
        celulas = ''.join(f'<td data-rotulo="{e(c)}">{celula(v)}</td>' for c, v in zip(bloco['colunas'], valores))
        fonte, conferido = linha.get('fonte', ''), linha.get('conferido_em', '')
        valido = fonte.startswith('https://') and DATA.fullmatch(conferido) and datetime.date.fromisoformat(conferido) <= hoje
        if valido:
            extras = ''.join(f' <a href="{e(u)}">{e(r)}</a>' for u, r in zip(linha.get('outras_fontes', []), linha.get('textos_outras_fontes', [])))
            celula_fonte = (f'<a href="{e(fonte)}">{e(linha.get("texto_fonte", bloco.get("texto_fonte", "Fonte oficial")))}</a>{extras} '
                            f'<small>conferido em {data_br(conferido)}</small>')
            atributos = f' data-dado data-fonte="{e(fonte)}" data-conferido="{conferido}"'
        elif marcar:
            celula_fonte = '<strong class="a-confirmar">Dado a confirmar</strong>'
            atributos = ' data-dado data-a-confirmar'
        else:
            raise Recusa('dado sem fonte')  # já barrado antes; segurança extra
        linhas.append(f'<tr{atributos}{id_linha}>{celulas}<td data-rotulo="{e(colunas[-1])}">{celula_fonte}</td></tr>')
    nota = ''.join(f'<p class="nota">{texto_com_links(n)}</p>\n' for n in ([bloco['nota']] if isinstance(bloco.get('nota'), str) else bloco.get('nota', [])))
    filtro = ''
    if bloco.get('filtro'):
        campo = f'busca-{e(bloco["id"])}'
        filtro = (f'<div class="filtro" data-filtro="{e(bloco["id"])}" hidden><label for="{campo}">{e(bloco["filtro"])}</label>'
                  f'<input id="{campo}" type="search" autocomplete="off" spellcheck="false" enterkeyhint="search">'
                  f'<p class="filtro-total" aria-live="polite"></p></div>\n')
    classes = ' '.join(c for c in ('larga' if bloco.get('largo') else '', 'rotulada' if bloco.get('rotulos') else '',
                                   'compacta' if bloco.get('compacta') else '') if c)
    classe = f' class="{classes}"' if classes else ''
    tabela = f'<table{classe}><thead><tr>{topo}</tr></thead><tbody>\n' + '\n'.join(linhas) + '\n</tbody></table>'
    if bloco.get('largo'):
        tabela = f'<div class="rolagem" role="region" aria-labelledby="{titulo_id}" tabindex="0">{tabela}</div>'
    return f'<{nivel} id="{titulo_id}">{e(bloco["titulo"])}</{nivel}>\n{nota}{filtro}{tabela}\n'


def contagem_de(bloco, pagina):
    """Lista das próximas datas, tiradas das linhas do bloco 'de' que têm o campo 'contagem'.
    Sem script, mostra cada data por extenso; o script da página escreve quantos dias faltam, pela data do aparelho."""
    origem = next((b for b in blocos_de_dados(pagina) if b.get('id') == bloco['de']), None)
    if origem is None:
        raise Recusa(f"{pagina['_arquivo']}: contagem aponta para um bloco que não existe: {bloco['de']}")
    eventos = sorted((l for l in origem['linhas'] if l.get('contagem') and not l.get('aviso')), key=lambda l: l['contagem'])
    if not eventos or any(not l.get('id') for l in eventos):
        raise Recusa(f"{pagina['_arquivo']}: contagem sem datas, ou linha com contagem sem id")
    itens = ''.join(f'<li data-data="{l["contagem"]}" data-artigo="{l["artigo_contagem"]}"><time datetime="{l["contagem"]}">{data_por_extenso(l["contagem"])}</time> '
                    f'<a href="#{e(l["id"])}">{e(l["rotulo_contagem"])}</a></li>' for l in eventos)
    titulo_id = id_do_titulo(bloco)
    texto = ''.join(f'<p>{texto_com_links(p)}</p>\n' for p in bloco.get('paragrafos', []))
    return (f'<div class="faixa"><section class="miolo bloco contagem" id="{e(bloco.get("id", titulo_id))}" aria-labelledby="{titulo_id}">\n'
            f'<h2 id="{titulo_id}">{e(bloco["titulo"])}</h2>\n<p class="contagem-saida" data-contagem-saida aria-live="polite"></p>\n{texto}'
            f'<ol class="datas-de-prova">{itens}</ol>\n</section></div>')


def html_bloco(bloco, paginas, marcar, pagina):
    tipo = bloco.get('tipo')
    titulo_id = id_do_titulo(bloco)
    cabeca = f'<h2 id="{titulo_id}">{e(bloco["titulo"])}</h2>\n' if bloco.get('titulo') else ''
    if tipo == 'texto':
        corpo = ''.join(f'<p>{texto_com_links(p)}</p>\n' for p in bloco['paragrafos'])
        id_secao = f' id="{e(bloco["id"])}"' if bloco.get('id') else ''
        return f'<div class="faixa"><section class="miolo bloco"{id_secao} aria-labelledby="{titulo_id}">\n{cabeca}{corpo}</section></div>'
    if tipo == 'aviso':
        # Informação que não foi achada em fonte oficial: caixa visível, sem dado.
        corpo = ''.join(f'<p>{texto_com_links(p)}</p>\n' for p in bloco['paragrafos'])
        return (f'<div class="faixa"><section class="miolo bloco" id="{e(bloco.get("id", titulo_id))}" aria-labelledby="{titulo_id}">\n'
                f'<div class="aviso" data-aviso>\n{cabeca}{corpo}</div>\n</section></div>')
    if tipo == 'links':
        itens = ''.join(f'<li><a href="{e(p["endereco"])}">{e(p["migalha"])}</a></li>' for p in paginas if p.get('menu'))
        return f'<div class="faixa"><section class="miolo bloco" aria-labelledby="{titulo_id}">\n{cabeca}<ul class="lista-links">{itens}<li><a href="/#privacidade">Dados e segurança</a></li></ul>\n</section></div>'
    if tipo == 'dados':
        largura = ' miolo-largo' if bloco.get('largo') else ''
        return (f'<div class="faixa"><section class="miolo{largura} bloco dados" id="{e(bloco.get("id", titulo_id))}" aria-labelledby="{titulo_id}">\n'
                + tabela_de(bloco, marcar, pagina) + '</section></div>')
    if tipo == 'par':
        # Duas tabelas lado a lado no computador e uma embaixo da outra no celular.
        partes = ''.join(f'<div class="dados" id="{e(b["id"])}">\n{tabela_de(b, marcar, pagina, "h3")}</div>\n' for b in bloco['blocos'])
        nota = ''.join(f'<p class="nota">{texto_com_links(n)}</p>\n' for n in bloco.get('nota', []))
        return (f'<div class="faixa"><section class="miolo miolo-largo bloco par" id="{e(bloco["id"])}" aria-labelledby="{titulo_id}">\n'
                f'{cabeca}{nota}<div class="par-grade">\n{partes}</div>\n</section></div>')
    if tipo == 'contagem':
        return contagem_de(bloco, pagina)
    if tipo == 'calculadora':
        # Caixa que o script da página preenche com o formulário; sem script, os parágrafos (a conta por extenso).
        if 'calculadora.js' not in scripts_de(pagina):
            raise Recusa(f"{pagina['_arquivo']}: bloco calculadora sem o script calculadora.js")
        # Sem título próprio: os títulos (Suas notas por área, Compare suas opções) vêm do formulário, logo abaixo do h1.
        corpo = ''.join(f'<p>{texto_com_links(p)}</p>\n' for p in bloco['paragrafos'])
        return (f'<div class="faixa"><section class="miolo bloco calculadora" id="{e(bloco.get("id", "calculadora"))}" aria-label="{e(bloco.get("rotulo", "Calculadora"))}">\n'
                f'<div data-calculadora>\n<div class="sem-script">\n{corpo}</div>\n</div>\n</section></div>')
    raise Recusa(f"{pagina['_arquivo']}: bloco de tipo desconhecido {tipo}")


def relacionadas_de(pagina, paginas):
    if not pagina.get('relacionadas'):
        return ''
    por_endereco = {p['endereco']: p for p in paginas}
    itens = ''.join(f'<li><a href="{e(a)}">{e(por_endereco[a]["migalha"])}</a></li>' for a in pagina['relacionadas'])
    return (f'<div class="faixa"><nav class="miolo bloco relacionadas" aria-labelledby="t-relacionadas">\n'
            f'<h2 id="t-relacionadas">Veja também</h2>\n<ul class="lista-links">{itens}</ul>\n</nav></div>')


def chamada_de(pagina):
    c = pagina.get('chamada') or {'titulo': 'Treine no PU', 'texto': 'Questões oficiais, uma por vez, com revisão do que você errar. É gratuito.'}
    return (f'<div class="faixa faixa-chamada"><section class="miolo chamada" aria-labelledby="t-chamada">\n<h2 id="t-chamada">{e(c["titulo"])}</h2>\n'
            f'<p>{texto_com_links(c["texto"])}</p>\n<p class="acoes"><a class="botao" href="/criar-conta/">Criar minha conta</a> <a class="entrar" href="/#entrar">Já tenho conta</a></p>\n</section></div>')


def pagina_de_leitura(pagina, paginas, inicio, molde, versao_estilo, imagem, imagem_alt, marcar, versoes_script=None):
    erro = pagina['tipo'] == 'erro'
    trilha = migalhas_de(pagina, inicio)
    itens = ''.join(f'<li><a href="{e(p["endereco"])}">{e(p["migalha"])}</a></li>' for p in trilha[:-1])
    migalhas = f'<nav class="migalhas" aria-label="Você está em"><ol>{itens}<li aria-current="page">{e(trilha[-1]["migalha"])}</li></ol></nav>\n'
    # Sumário: os blocos de dados, os pares de tabelas e os blocos marcados com "no_sumario": true, na ordem da página.
    dados = [b for b in pagina.get('blocos', []) if b.get('id') and (b.get('tipo') in ('dados', 'par') or b.get('no_sumario'))]
    sumario = ''
    if pagina.get('sumario') and dados:
        sumario = '<nav class="sumario" aria-label="Nesta página"><ul>' + ''.join(f'<li><a href="#{e(b["id"])}">{e(b["titulo"])}</a></li>' for b in dados) + '</ul></nav>\n'
    menu = ''.join(f'<li><a href="{e(p["endereco"])}"' + (' aria-current="page"' if p is pagina else '') + f'>{e(p["migalha"])}</a></li>'
                   for p in paginas if p.get('menu')) + '<li><a href="/#privacidade">Dados e segurança</a></li>'
    valores = {
        'titulo': e(pagina['titulo']), 'descricao': e(pagina['descricao']),
        'robots': '<meta name="robots" content="noindex">\n' if erro else '',
        'canonico': '' if erro else f'<link rel="canonical" href="{absoluto(pagina["endereco"])}">\n',
        'og_url': '' if erro else f'<meta property="og:url" content="{absoluto(pagina["endereco"])}">\n',
        'imagem': e(absoluto(pagina.get('imagem', imagem))), 'imagem_alt': e(pagina.get('imagem_alt', imagem_alt)),
        'versao_estilo': versao_estilo, 'dados_estruturados': dados_estruturados(pagina, inicio), 'tom': pagina.get('tom', 'mar'),
        'migalhas': migalhas, 'h1': e(pagina['h1']), 'apoio': texto_com_links(pagina['apoio']), 'sumario': sumario,
        'blocos': '\n'.join(html_bloco(b, paginas, marcar, pagina) for b in pagina.get('blocos', [])),
        'chamada': relacionadas_de(pagina, paginas) + chamada_de(pagina), 'menu': menu,
        # Página sem script: script-src 'none'. Com o campo "script": só o arquivo do próprio site, nada embutido.
        'script_src': "'self'" if pagina.get('script') else "'none'",
        'script': ''.join(f'<script src="{endereco_do_script(s)}?v={(versoes_script or {})[s]}" defer></script>\n' for s in scripts_de(pagina)),
    }
    return Template(molde).substitute(valores)


# ---------- Entrada (index.html) e porta do cadastro ----------
def com_bloco(texto, bloco):
    if MARCA_INICIO in texto:
        inicio, fim = texto.index(MARCA_INICIO), texto.index(MARCA_FIM) + len(MARCA_FIM)
        return texto[:inicio] + bloco + texto[fim:]
    if '</head>' not in texto:
        raise Recusa('index.html sem </head>')
    return texto.replace('</head>', bloco + '\n</head>', 1)


def trocar(texto, antigo, novo, quantas=None):
    achadas = texto.count(antigo)
    if not achadas or (quantas is not None and achadas != quantas):
        raise Recusa(f'porta do cadastro: esperava {quantas or "ao menos 1"} de {antigo!r} no index.html, achei {achadas}')
    return texto.replace(antigo, novo)


def porta_do_cadastro(index_raiz, pagina, inicio):
    """A entrada inteira, igual à da raiz, com caminhos absolutos, título próprio e o pedido de abrir no cadastro.
    O endereço canônico continua o da raiz: é a mesma página, aberta em outro ponto."""
    texto = com_bloco(index_raiz, bloco_jsonld(pagina, inicio))
    texto = trocar(texto, '<html lang="pt-BR" data-publico="1">', '<html lang="pt-BR" data-publico="1" data-abrir="criar-conta">', 1)
    for antigo in ('href="./', 'src="./'):
        texto = trocar(texto, antigo, antigo[:-2] + '/')
    titulo_antigo = re.search(r'<title>([^<]*)</title>', texto).group(1)
    descricao_antiga = e(meta_do_index(texto, 'description'))
    texto = trocar(texto, f'<title>{titulo_antigo}</title>', f'<title>{e(pagina["titulo"])}</title>', 1)
    texto = trocar(texto, f'<meta property="og:title" content="{titulo_antigo}">', f'<meta property="og:title" content="{e(pagina["titulo"])}">', 1)
    texto = trocar(texto, f'content="{descricao_antiga}"', f'content="{e(pagina["descricao"])}"', 2)
    if './' in re.sub(r'<!-- .*? -->', '', texto, flags=re.S).split('<body', 1)[0]:
        raise Recusa('porta do cadastro: sobrou caminho relativo no cabeçalho')
    return texto


# ---------- Mapa do site e robots ----------
def mapa(paginas):
    linhas = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for p in paginas:
        if p.get('no_mapa'):
            continue
        linhas.append(f'  <url><loc>{absoluto(p["endereco"])}</loc><lastmod>{p["atualizada_em"]}</lastmod></url>')
    return '\n'.join(linhas + ['</urlset>', ''])


def robots():
    return f'User-agent: *\nAllow: /\n\nSitemap: {DOMINIO}/sitemap.xml\n'


# ---------- Gravação ----------
def gerar(saida, marcar=False, raiz=RAIZ, conteudo=None, hoje=None):
    """Monta tudo na memória e só grava se nada foi recusado. Devolve a lista de arquivos gravados (relativos)."""
    hoje = hoje or datetime.date.today()
    paginas = carregar(conteudo or PASTA / 'conteudo')
    problemas = [p for pagina in paginas for p in problemas_de_fonte(pagina, hoje)]
    if problemas and not marcar:
        raise Recusa('dado sem fonte ou sem data de conferência (regra dado-inventado):\n  ' + '\n  '.join(problemas))
    for aviso in problemas:
        print('AVISO  dado a confirmar: ' + aviso, file=sys.stderr)
    inicio = next(p for p in paginas if p['tipo'] == 'entrada')
    molde = (PASTA / 'molde.html').read_text(encoding='utf-8')
    versao_estilo = hashlib.sha256((PASTA / 'estilo.css').read_bytes()).hexdigest()[:10]
    versoes_script = {s: hashlib.sha256(arquivo_do_script(s).read_bytes()).hexdigest()[:10] for p in paginas for s in scripts_de(p)}
    index_raiz = com_bloco((raiz / 'index.html').read_text(encoding='utf-8'), bloco_jsonld(inicio, inicio))
    index_app = com_bloco((raiz / 'app/public/index.html').read_text(encoding='utf-8'), bloco_jsonld(inicio, inicio))
    imagem = urlparse_caminho(meta_do_index(index_raiz, 'og:image'))
    imagem_alt = meta_do_index(index_raiz, 'og:image:alt')
    arquivos = {'index.html': index_raiz, 'app/public/index.html': index_app, 'robots.txt': robots(), 'sitemap.xml': mapa(paginas)}
    titulos = [re.search(r'<title>([^<]*)</title>', index_raiz).group(1)]
    for pagina in paginas:
        if pagina['tipo'] == 'cadastro':
            arquivos[pagina['endereco'].strip('/') + '/index.html'] = porta_do_cadastro(index_raiz, pagina, inicio)
        elif pagina['tipo'] in ('leitura', 'erro'):
            destino = '404.html' if pagina['tipo'] == 'erro' else pagina['endereco'].strip('/') + '/index.html'
            arquivos[destino] = pagina_de_leitura(pagina, paginas, inicio, molde, versao_estilo, imagem, imagem_alt, marcar, versoes_script)
        if pagina.get('titulo'):
            titulos.append(e(pagina['titulo']))
    if len(set(titulos)) != len(titulos):
        raise Recusa('título repetido entre páginas')
    saida = Path(saida)
    for nome, texto in arquivos.items():
        destino = saida / nome
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding='utf-8')
    return sorted(arquivos)


def urlparse_caminho(url):
    if not url.startswith(DOMINIO + '/'):
        raise Recusa(f'imagem de compartilhamento fora do domínio: {url}')
    return url[len(DOMINIO):]


def conferir():
    with tempfile.TemporaryDirectory() as temporaria:
        nomes = gerar(temporaria)
        diferentes = [n for n in nomes if not (RAIZ / n).is_file() or not filecmp.cmp(Path(temporaria) / n, RAIZ / n, shallow=False)]
    return diferentes


def principal():
    argumentos = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    argumentos.add_argument('--saida', default=str(RAIZ))
    argumentos.add_argument('--conferir', action='store_true')
    argumentos.add_argument('--marcar-a-confirmar', action='store_true')
    a = argumentos.parse_args()
    try:
        if a.conferir:
            diferentes = conferir()
            if diferentes:
                print('Desatualizado, rode python3 paginas/gerar.py: ' + ', '.join(diferentes))
                return 1
            print('Páginas em dia.')
            return 0
        nomes = gerar(a.saida, marcar=a.marcar_a_confirmar)
    except Recusa as erro:
        print('RECUSADO  ' + str(erro), file=sys.stderr)
        return 2
    print(f'{len(nomes)} arquivos gravados em {a.saida}: ' + ', '.join(nomes))
    return 0


if __name__ == '__main__':
    sys.exit(principal())
