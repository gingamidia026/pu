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
    return paginas


def problemas_de_fonte(pagina, hoje):
    """Lista os dados sem fonte oficial ou sem data de conferência válida."""
    problemas = []
    for bloco in pagina.get('blocos', []):
        if bloco.get('tipo') != 'dados':
            continue
        for n, linha in enumerate(bloco.get('linhas', []), 1):
            onde = f"{pagina['_arquivo']}, bloco {bloco.get('id')}, linha {n}"
            fonte, conferido = linha.get('fonte', ''), linha.get('conferido_em', '')
            if not fonte.startswith('https://'):
                problemas.append(f'{onde}: sem fonte https')
            if not DATA.fullmatch(conferido):
                problemas.append(f'{onde}: sem data de conferência (AAAA-MM-DD)')
            elif datetime.date.fromisoformat(conferido) > hoje:
                problemas.append(f'{onde}: data de conferência no futuro')
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
def html_bloco(bloco, paginas, marcar, pagina):
    tipo = bloco.get('tipo')
    titulo_id = 't-' + bloco.get('id', re.sub(r'[^a-z0-9]+', '-', bloco.get('titulo', 'bloco').lower()).strip('-'))
    cabeca = f'<h2 id="{titulo_id}">{e(bloco["titulo"])}</h2>\n'
    if tipo == 'texto':
        corpo = ''.join(f'<p>{texto_com_links(p)}</p>\n' for p in bloco['paragrafos'])
        return f'<div class="faixa"><section class="miolo bloco" aria-labelledby="{titulo_id}">\n{cabeca}{corpo}</section></div>'
    if tipo == 'links':
        itens = ''.join(f'<li><a href="{e(p["endereco"])}">{e(p["migalha"])}</a></li>' for p in paginas if p.get('menu'))
        return f'<div class="faixa"><section class="miolo bloco" aria-labelledby="{titulo_id}">\n{cabeca}<ul class="lista-links">{itens}<li><a href="/#privacidade">Dados e segurança</a></li></ul>\n</section></div>'
    if tipo == 'dados':
        colunas = bloco['colunas'] + [bloco.get('coluna_fonte', 'Fonte')]
        topo = ''.join(f'<th scope="col">{e(c)}</th>' for c in colunas)
        linhas = []
        hoje = datetime.date.today()
        for linha in bloco['linhas']:
            valores = linha['valores']
            if len(valores) != len(bloco['colunas']):
                raise Recusa(f"{pagina['_arquivo']}, bloco {bloco.get('id')}: linha com {len(valores)} valores para {len(bloco['colunas'])} colunas")
            celulas = ''.join(f'<td data-rotulo="{e(c)}">{e(v)}</td>' for c, v in zip(bloco['colunas'], valores))
            fonte, conferido = linha.get('fonte', ''), linha.get('conferido_em', '')
            valido = fonte.startswith('https://') and DATA.fullmatch(conferido) and datetime.date.fromisoformat(conferido) <= hoje
            if valido:
                celula_fonte = f'<a href="{e(fonte)}">{e(linha.get("texto_fonte", bloco.get("texto_fonte", "Fonte oficial")))}</a> <small>conferido em {data_br(conferido)}</small>'
                atributos = f' data-dado data-fonte="{e(fonte)}" data-conferido="{conferido}"'
            elif marcar:
                celula_fonte = '<strong class="a-confirmar">Dado a confirmar</strong>'
                atributos = ' data-dado data-a-confirmar'
            else:
                raise Recusa('dado sem fonte')  # já barrado antes; segurança extra
            linhas.append(f'<tr{atributos}>{celulas}<td data-rotulo="{e(colunas[-1])}">{celula_fonte}</td></tr>')
        nota = f'<p class="nota">{texto_com_links(bloco["nota"])}</p>\n' if bloco.get('nota') else ''
        return (f'<div class="faixa"><section class="miolo bloco dados" id="{e(bloco.get("id", titulo_id))}" aria-labelledby="{titulo_id}">\n{cabeca}{nota}'
                f'<table><thead><tr>{topo}</tr></thead><tbody>\n' + '\n'.join(linhas) + '\n</tbody></table>\n</section></div>')
    raise Recusa(f"{pagina['_arquivo']}: bloco de tipo desconhecido {tipo}")


def chamada_de(pagina):
    c = pagina.get('chamada') or {'titulo': 'Treine no PU', 'texto': 'Questões oficiais, uma por vez, com revisão do que você errar. É gratuito.'}
    return (f'<div class="faixa faixa-chamada"><section class="miolo chamada" aria-labelledby="t-chamada">\n<h2 id="t-chamada">{e(c["titulo"])}</h2>\n'
            f'<p>{texto_com_links(c["texto"])}</p>\n<p class="acoes"><a class="botao" href="/criar-conta/">Criar minha conta</a> <a class="entrar" href="/#entrar">Já tenho conta</a></p>\n</section></div>')


def pagina_de_leitura(pagina, paginas, inicio, molde, versao_estilo, imagem, imagem_alt, marcar):
    erro = pagina['tipo'] == 'erro'
    trilha = migalhas_de(pagina, inicio)
    itens = ''.join(f'<li><a href="{e(p["endereco"])}">{e(p["migalha"])}</a></li>' for p in trilha[:-1])
    migalhas = f'<nav class="migalhas" aria-label="Você está em"><ol>{itens}<li aria-current="page">{e(trilha[-1]["migalha"])}</li></ol></nav>\n'
    dados = [b for b in pagina.get('blocos', []) if b.get('tipo') == 'dados']
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
        'chamada': chamada_de(pagina), 'menu': menu,
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
            arquivos[destino] = pagina_de_leitura(pagina, paginas, inicio, molde, versao_estilo, imagem, imagem_alt, marcar)
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
