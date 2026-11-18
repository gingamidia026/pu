#!/usr/bin/env python3
"""Teste das páginas públicas geradas por paginas/gerar.py, sem tokens, sem rede e sem navegador.

Confere em cada página: título único, descrição, endereço canônico, JSON-LD (Organization, WebSite, BreadcrumbList),
imagem de compartilhamento de 1200 x 630, links internos que resolvem, fonte e data de cada dado, nenhuma chamada ao
intermediário e nenhum recurso de terceiros; e também sitemap.xml, robots.txt, 404.html, a porta /criar-conta/ e a recusa
de dado sem fonte. Uso: python3 tests/paginas.py

Dominique-Oliveira-Claude🤖🧡, 17/11/2026.
"""
import datetime
import importlib.util
import json
import re
import shutil
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

RAIZ = Path(__file__).resolve().parent.parent
especificacao = importlib.util.spec_from_file_location('gerar', RAIZ / 'paginas/gerar.py')
gerar = importlib.util.module_from_spec(especificacao)
especificacao.loader.exec_module(gerar)
DOMINIO = gerar.DOMINIO
INTERMEDIARIO = re.compile(r'chatgpt\.site|configuracao-publica\.js|/api/', re.I)


class Leitor(HTMLParser):
    """Junta o que o teste precisa de uma página: metas, links, recursos, JSON-LD e linhas de dado."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.titulo, self.metas, self.links, self.recursos, self.jsonld, self.dados = '', {}, [], [], [], []
        self.lang, self.canonico, self._em, self._buffer, self._linha = '', '', None, '', None

    def handle_starttag(self, tag, atributos):
        a = dict(atributos)
        if tag == 'html':
            self.lang = a.get('lang', '')
        if tag == 'title':
            self._em, self._buffer = 'title', ''
        if tag == 'meta' and a.get('content') is not None:
            self.metas[a.get('name') or a.get('property') or a.get('http-equiv')] = a['content']
        if tag == 'link':
            if a.get('rel') == 'canonical':
                self.canonico = a['href']
            else:
                self.recursos.append(a['href'])
        if tag in ('script', 'img', 'iframe', 'source', 'video', 'audio', 'embed') and a.get('src'):
            self.recursos.append(a['src'])
        if tag == 'script' and a.get('type') == 'application/ld+json':
            self._em, self._buffer = 'jsonld', ''
        if tag == 'a' and a.get('href'):
            self.links.append(a['href'])
            if self._linha is not None:
                self._linha['links'].append(a['href'])
        if tag == 'tr' and 'data-dado' in a:
            self._linha = {'atributos': a, 'links': [], 'texto': ''}

    def handle_endtag(self, tag):
        if tag == 'title' and self._em == 'title':
            self.titulo, self._em = self._buffer.strip(), None
        if tag == 'script' and self._em == 'jsonld':
            self.jsonld.append(json.loads(self._buffer)); self._em = None
        if tag == 'tr' and self._linha is not None:
            self.dados.append(self._linha); self._linha = None

    def handle_data(self, dados):
        if self._em:
            self._buffer += dados
        if self._linha is not None:
            self._linha['texto'] += dados


def ler(arquivo):
    leitor = Leitor()
    texto = arquivo.read_text(encoding='utf-8')
    leitor.feed(texto)
    leitor.texto = texto
    return leitor


def arquivo_do_caminho(caminho):
    """Como o GitHub Pages resolve um caminho do site para um arquivo do repositório."""
    caminho = urlsplit(caminho).path
    alvo = RAIZ / caminho.lstrip('/')
    if caminho.endswith('/') or alvo.is_dir():
        alvo = alvo / 'index.html'
    return alvo


def tamanho_png(arquivo):
    cabeca = arquivo.read_bytes()[:24]
    assert cabeca[:8] == b'\x89PNG\r\n\x1a\n', f'{arquivo} não é PNG'
    return struct.unpack('>II', cabeca[16:24])


PAGINAS = gerar.carregar(RAIZ / 'paginas/conteudo')
LEITURA = [p for p in PAGINAS if p['tipo'] == 'leitura']
ARQUIVO = {p['endereco']: arquivo_do_caminho(p['endereco']) if p['tipo'] != 'erro' else RAIZ / '404.html' for p in PAGINAS}


class Paginas(unittest.TestCase):
    def test_gerado_em_dia(self):
        self.assertEqual(gerar.conferir(), [], 'rode python3 paginas/gerar.py e registre as saídas')

    def test_titulos_descricoes_e_canonicos(self):
        titulos = []
        for pagina in PAGINAS:
            with self.subTest(pagina=pagina['endereco']):
                lida = ler(ARQUIVO[pagina['endereco']])
                titulos.append(lida.titulo)
                self.assertEqual(lida.lang, 'pt-BR')
                self.assertTrue(10 <= len(lida.titulo) <= 90, lida.titulo)
                self.assertTrue(50 <= len(lida.metas.get('description', '')) <= 200, lida.metas.get('description'))
                self.assertEqual(lida.metas.get('og:title'), lida.titulo)
                if pagina['tipo'] == 'erro':
                    self.assertEqual(lida.metas.get('robots'), 'noindex')
                    self.assertEqual(lida.canonico, '')
                elif pagina['tipo'] == 'cadastro':
                    self.assertEqual(lida.canonico, DOMINIO + '/', 'a porta é a mesma entrada: canônico na raiz')
                else:
                    self.assertEqual(lida.canonico, DOMINIO + pagina['endereco'])
                    self.assertEqual(lida.metas.get('og:url'), lida.canonico)
        self.assertEqual(len(titulos), len(set(titulos)), 'título repetido')

    def test_dados_estruturados(self):
        for pagina in PAGINAS:
            with self.subTest(pagina=pagina['endereco']):
                lida = ler(ARQUIVO[pagina['endereco']])
                self.assertEqual(len(lida.jsonld), 1)
                grafico = {item['@type']: item for item in lida.jsonld[0]['@graph']}
                self.assertEqual(lida.jsonld[0]['@context'], 'https://schema.org')
                self.assertEqual(set(grafico), {'Organization', 'WebSite', 'BreadcrumbList'})
                self.assertEqual(grafico['Organization']['url'], DOMINIO + '/')
                self.assertTrue(arquivo_do_caminho(urlsplit(grafico['Organization']['logo']).path).is_file())
                self.assertEqual(grafico['WebSite']['inLanguage'], 'pt-BR')
                itens = grafico['BreadcrumbList']['itemListElement']
                self.assertEqual([i['position'] for i in itens], list(range(1, len(itens) + 1)))
                self.assertEqual(itens[-1]['name'], pagina['migalha'])
                if pagina['tipo'] == 'leitura':
                    self.assertEqual(itens[0]['item'], DOMINIO + '/')
                    self.assertEqual(itens[-1]['item'], DOMINIO + pagina['endereco'])

    def test_imagem_de_compartilhamento(self):
        for pagina in PAGINAS:
            with self.subTest(pagina=pagina['endereco']):
                lida = ler(ARQUIVO[pagina['endereco']])
                imagem = lida.metas['og:image']
                self.assertTrue(imagem.startswith(DOMINIO + '/'))
                arquivo = arquivo_do_caminho(urlsplit(imagem).path)
                self.assertTrue(arquivo.is_file(), arquivo)
                self.assertEqual(tamanho_png(arquivo), (1200, 630))
                self.assertEqual((lida.metas['og:image:width'], lida.metas['og:image:height']), ('1200', '630'))
                self.assertTrue(lida.metas.get('og:image:alt'))
                self.assertEqual(lida.metas.get('twitter:card'), 'summary_large_image')

    def test_links_internos_resolvem(self):
        for pagina in PAGINAS:
            with self.subTest(pagina=pagina['endereco']):
                lida = ler(ARQUIVO[pagina['endereco']])
                ids = set(re.findall(r'\sid="([^"]+)"', lida.texto))
                aplicativo = pagina['tipo'] in ('entrada', 'cadastro')
                for link in lida.links + lida.recursos:
                    if link.startswith('https://'):
                        continue
                    if aplicativo and link.startswith('./'):  # a entrada da raiz usa caminhos relativos à raiz
                        link = link[1:]
                    if link.startswith('#'):
                        if not aplicativo:  # na entrada, #estudar e os outros são telas do app.js
                            self.assertIn(link[1:], ids, f'âncora sem destino: {link}')
                        continue
                    self.assertTrue(link.startswith('/'), f'caminho relativo numa página gerada: {link}')
                    self.assertTrue(arquivo_do_caminho(link).is_file(), f'link quebrado: {link}')

    def test_nada_de_fora_nem_intermediario(self):
        for pagina in PAGINAS:
            if pagina['tipo'] not in ('leitura', 'erro'):
                continue
            with self.subTest(pagina=pagina['endereco']):
                lida = ler(ARQUIVO[pagina['endereco']])
                self.assertEqual([r for r in lida.recursos if not r.startswith('/') or r.startswith('//')], [], 'recurso de terceiros')
                self.assertNotRegex(lida.texto, INTERMEDIARIO)
                politica = lida.metas['Content-Security-Policy']
                for trecho in ("default-src 'self'", "connect-src 'none'", "form-action 'none'"):
                    self.assertIn(trecho, politica)
                scripts = re.findall(r'<script\b([^>]*)>', lida.texto)
                externos = [a for a in scripts if 'application/ld+json' not in a]
                if pagina.get('script'):
                    # Só o arquivo que a página declara, do próprio site, e a política passa a 'self' (nada embutido).
                    self.assertIn("script-src 'self'", politica)
                    self.assertNotIn('unsafe-inline', politica)
                    self.assertEqual(len(externos), 1, externos)
                    self.assertRegex(externos[0], r'^ src="/paginas/' + re.escape(pagina['script']) + r'\?v=[0-9a-f]{10}" defer$')
                else:
                    self.assertIn("script-src 'none'", politica)
                    self.assertEqual(externos, [], 'script numa página que não declara')
                # Nenhum script embutido executável: só o bloco de dados estruturados.
                self.assertEqual(len(re.findall(r'<script type="application/ld\+json">', lida.texto)), 1)
                self.assertNotRegex(lida.texto, r'\son[a-z]+="', 'atributo de evento embutido')
        estilo = (RAIZ / 'paginas/estilo.css').read_text(encoding='utf-8')
        self.assertNotRegex(estilo, r'url\(["\']?(https?:)?//', 'estilo com recurso de terceiros')
        self.assertNotIn('@import', estilo)
        for fonte in re.findall(r'url\("(/[^"]+\.woff2)"\)', estilo):
            self.assertTrue(arquivo_do_caminho(fonte).is_file(), fonte)

    def test_cada_dado_tem_fonte_e_data(self):
        hoje = datetime.date.today()
        for pagina in LEITURA:
            esperadas = sum(1 for b in gerar.blocos_de_dados(pagina) for l in b['linhas'] if not l.get('aviso'))
            with self.subTest(pagina=pagina['endereco']):
                lida = ler(ARQUIVO[pagina['endereco']])
                self.assertEqual(len(lida.dados), esperadas, 'cada linha de dado vira uma linha marcada')
                self.assertNotIn('Dado a confirmar', lida.texto)
                for linha in lida.dados:
                    fonte, conferido = linha['atributos'].get('data-fonte', ''), linha['atributos'].get('data-conferido', '')
                    self.assertTrue(fonte.startswith('https://'), linha)
                    self.assertIn(fonte, linha['links'], 'a fonte aparece como link na própria linha')
                    data = datetime.date.fromisoformat(conferido)
                    self.assertLessEqual(data, hoje)
                    self.assertIn('conferido em ' + data.strftime('%d/%m/%Y'), linha['texto'])

    def test_mapa_e_robots(self):
        mapa = ET.parse(RAIZ / 'sitemap.xml').getroot()
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        enderecos = [u.find('s:loc', ns).text for u in mapa.findall('s:url', ns)]
        esperados = [DOMINIO + p['endereco'] for p in PAGINAS if not p.get('no_mapa')]
        self.assertEqual(enderecos, esperados)
        self.assertIn(DOMINIO + '/', enderecos)
        for pagina in LEITURA:
            self.assertIn(DOMINIO + pagina['endereco'], enderecos)
        for url in mapa.findall('s:url', ns):
            datetime.date.fromisoformat(url.find('s:lastmod', ns).text)
            self.assertTrue(arquivo_do_caminho(urlsplit(url.find('s:loc', ns).text).path).is_file())
        robots = (RAIZ / 'robots.txt').read_text(encoding='utf-8')
        self.assertIn(f'Sitemap: {DOMINIO}/sitemap.xml', robots)
        self.assertNotRegex(robots, r'(?m)^Disallow:\s*/\s*$')

    def test_pagina_404(self):
        lida = ler(RAIZ / '404.html')
        self.assertIn('/', lida.links)
        for pagina in LEITURA:
            self.assertIn(pagina['endereco'], lida.links)
        self.assertIn('/criar-conta/', lida.links)

    def test_porta_do_cadastro(self):
        raiz = (RAIZ / 'index.html').read_text(encoding='utf-8')
        porta = (RAIZ / 'criar-conta/index.html').read_text(encoding='utf-8')
        self.assertIn('data-abrir="criar-conta"', porta)
        self.assertIn("document.documentElement.dataset.abrir === 'criar-conta'", (RAIZ / 'app/public/app.js').read_text(encoding='utf-8'))
        bloco = lambda t: t[t.index('<!-- entrada:inicio'):t.index('<!-- entrada:fim -->')]
        self.assertEqual(bloco(porta), bloco(raiz), 'a porta tem a mesma entrada da raiz')
        for padrao in (r'(?:src|href)="\./',):
            self.assertNotRegex(porta, padrao)
        scripts = lambda t: [re.sub(r'^\./', '/', s) for s in re.findall(r'<script src="([^"]+)"', t)]
        self.assertEqual(scripts(porta), scripts(raiz), 'mesmos scripts e versões da raiz')
        # A entrada da raiz também leva o bloco de dados estruturados, igual ao do app/public/index.html.
        for arquivo in ('index.html', 'app/public/index.html'):
            texto = (RAIZ / arquivo).read_text(encoding='utf-8')
            self.assertEqual(texto.count(gerar.MARCA_INICIO), 1, arquivo)
        # Todas as chamadas para treinar levam à porta do cadastro.
        for pagina in PAGINAS:
            if pagina['tipo'] in ('leitura', 'erro'):
                self.assertIn('href="/criar-conta/"', ARQUIVO[pagina['endereco']].read_text(encoding='utf-8'))


class PaginasUteis(unittest.TestCase):
    """Calendário, notas de corte, obras e temas de redação (paginas/importar-coleta.py)."""
    NOVAS = ['/calendario-vestibulares/', '/notas-de-corte/fuvest/', '/notas-de-corte/unicamp/', '/obras-obrigatorias/', '/temas-de-redacao-enem/']

    def pagina(self, endereco):
        return next(p for p in PAGINAS if p['endereco'] == endereco), ler(ARQUIVO[endereco])

    def test_cinco_paginas_no_mapa_no_menu_e_na_404(self):
        mapa = (RAIZ / 'sitemap.xml').read_text(encoding='utf-8')
        erro = ler(RAIZ / '404.html')
        for endereco in self.NOVAS:
            self.assertIn(f'<loc>{DOMINIO}{endereco}</loc>', mapa)
            self.assertIn(endereco, erro.links)
            for outra in self.NOVAS:  # menu comum no rodapé de todas
                self.assertIn(outra, ler(ARQUIVO[endereco]).links)

    def test_script_so_nas_paginas_que_declaram(self):
        com_script = {p['endereco']: p['script'] for p in PAGINAS if p.get('script')}
        self.assertEqual(com_script, {'/calendario-vestibulares/': 'calendario.js', '/notas-de-corte/fuvest/': 'notas-de-corte.js',
                                      '/notas-de-corte/unicamp/': 'notas-de-corte.js'})
        for nome in set(com_script.values()):
            codigo = (RAIZ / 'paginas' / nome).read_text(encoding='utf-8')
            self.assertNotRegex(codigo, r'fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon|import\(|https?://|innerHTML|eval\(|new Function',
                                'o script não fala com a rede nem monta HTML')

    def test_avisos_no_lugar_de_data_inventada(self):
        pagina, lida = self.pagina('/calendario-vestibulares/')
        avisos = [l for b in gerar.blocos_de_dados(pagina) for l in b['linhas'] if l.get('aviso')]
        self.assertEqual(lida.texto.count('Data ainda não encontrada em fonte oficial'), len(avisos))
        etapas = {(l['valores'][0], l['valores'][1]) for l in avisos}
        for esperado in [('Enem 2026', 'Resultado: notas individuais'), ('Enem 2026', 'Chamadas do Sisu'), ('Unesp 2027', 'Inscrição'),
                         ('Unesp 2027', 'Resultado'), ('Unesp 2027', 'Chamadas'), ('Famerp 2027', 'Resultado da 1ª fase')]:
            self.assertIn(esperado, etapas)
        self.assertEqual(lida.texto.count('<tr data-aviso'), len(avisos))
        # Isenção do Enem: a prorrogação do MEC, citando as duas fontes.
        linha = next(l for b in gerar.blocos_de_dados(pagina) for l in b['linhas'] if l['valores'][0] == 'Enem 2026' and 'isenção da taxa' in str(l['valores'][1]))
        self.assertEqual(linha['valores'][2], '13/04 a 30/04/2026')
        self.assertIn('/mec/', linha['fonte'])
        self.assertTrue(any('/inep/' in u for u in linha['outras_fontes']))
        self.assertIn('class="datas-de-prova"', lida.texto)

    def test_notas_de_corte(self):
        fuvest, lida = self.pagina('/notas-de-corte/fuvest/')
        self.assertEqual(len(next(gerar.blocos_de_dados(fuvest))['linhas']), 77)
        self.assertIn('data-filtro="cortes" hidden', lida.texto)
        unicamp, lida = self.pagina('/notas-de-corte/unicamp/')
        blocos = {b['id']: b for b in gerar.blocos_de_dados(unicamp)}
        self.assertEqual(len(blocos['cortes']['colunas']), 9)
        self.assertEqual(len(blocos['cortes']['linhas']), 64)  # 63 lidas e 1 com aviso
        self.assertIn('Não lido no PDF, ver o documento oficial', lida.texto)
        self.assertEqual(len(blocos['musica']['linhas']), 22)
        self.assertIn('VU2027-Manual-do-Ingresso.pdf', lida.texto, 'legenda do PAAIS com a fonte oficial')
        for texto in (ler(ARQUIVO['/notas-de-corte/fuvest/']).texto, lida.texto):
            self.assertRegex(texto, r'não diz (qual é a nota máxima|quantas questões)')

    def test_obras(self):
        _, lida = self.pagina('/obras-obrigatorias/')
        for recusado in ('archive.org', 'biblioteca.torres.rs.gov.br'):
            self.assertNotIn(recusado, lida.texto)
        for link in ('machado.mec.gov.br', 'digital.bbm.usp.br/bitstream/bbm/4800', 'Mem%C3%B3rias_de_Martha', 'bbm/7743'):
            self.assertIn(link, lida.texto)
        self.assertIn('lista não encontrada em fonte oficial', lida.texto)
        self.assertIn('Vários Escritos', lida.texto)
        self.assertIn('cálculo', lida.texto)
        self.assertEqual(lida.texto.count('class="par-grade"'), 2)

    def test_temas(self):
        pagina, lida = self.pagina('/temas-de-redacao-enem/')
        anos = [l['valores'][0] for b in gerar.blocos_de_dados(pagina) for l in b['linhas']]
        self.assertEqual(anos, [str(a) for a in range(2026, 1997, -1)])
        self.assertIn('O PU não corrige redação', lida.texto)
        self.assertIn('Em 2008 a prova não deu título ao tema', lida.texto)
        self.assertIn('ainda não publicou o caderno', lida.texto)
        self.assertNotIn('O MOVIMENTO IMIGRATÓRIO', lida.texto)
        self.assertIn('O movimento imigratório para o Brasil no século XXI', lida.texto)


class Recusa(unittest.TestCase):
    """O gerador recusa dado sem fonte; com --marcar-a-confirmar, grava com o aviso visível."""
    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp(prefix='pu-paginas-'))
        self.conteudo = self.pasta / 'conteudo'
        shutil.copytree(RAIZ / 'paginas/conteudo', self.conteudo)
        dados = json.loads((self.conteudo / 'provas-anteriores.json').read_text(encoding='utf-8'))
        bloco = next(b for b in dados['blocos'] if b['tipo'] == 'dados')
        del bloco['linhas'][0]['fonte']
        bloco['linhas'][1]['conferido_em'] = '2999-01-01'
        (self.conteudo / 'provas-anteriores.json').write_text(json.dumps(dados, ensure_ascii=False), encoding='utf-8')
        self.saida = self.pasta / 'saida'

    def tearDown(self):
        shutil.rmtree(self.pasta, ignore_errors=True)

    def test_recusa_e_nao_grava(self):
        with self.assertRaises(gerar.Recusa) as erro:
            gerar.gerar(self.saida, conteudo=self.conteudo)
        self.assertIn('sem fonte https', str(erro.exception))
        self.assertIn('no futuro', str(erro.exception))
        self.assertFalse(self.saida.exists(), 'nada gravado quando recusa')

    def test_marca_dado_a_confirmar(self):
        gerar.gerar(self.saida, marcar=True, conteudo=self.conteudo)
        texto = (self.saida / 'provas-anteriores/index.html').read_text(encoding='utf-8')
        self.assertEqual(texto.count('Dado a confirmar'), 2)
        self.assertEqual(texto.count('data-a-confirmar'), 2)

    def test_link_fora_do_padrao(self):
        dados = json.loads((self.conteudo / '404.json').read_text(encoding='utf-8'))
        dados['apoio'] = 'Veja [isto](javascript:alert(1)).'
        (self.conteudo / '404.json').write_text(json.dumps(dados, ensure_ascii=False), encoding='utf-8')
        with self.assertRaises(gerar.Recusa):
            gerar.gerar(self.saida, marcar=True, conteudo=self.conteudo)

    def test_script_fora_da_pasta_recusado(self):
        dados = json.loads((self.conteudo / 'provas-anteriores.json').read_text(encoding='utf-8'))
        dados['script'] = '../app/public/app.js'
        (self.conteudo / 'provas-anteriores.json').write_text(json.dumps(dados, ensure_ascii=False), encoding='utf-8')
        with self.assertRaises(gerar.Recusa):
            gerar.gerar(self.saida, marcar=True, conteudo=self.conteudo)

    def test_link_de_celula_sem_https_recusado(self):
        dados = json.loads((self.conteudo / 'obras-obrigatorias.json').read_text(encoding='utf-8'))
        linha = dados['blocos'][1]['blocos'][0]['linhas'][0]
        linha['valores'][-1] = {'texto': 'PDF', 'link': 'http://exemplo.org/a.pdf'}
        (self.conteudo / 'obras-obrigatorias.json').write_text(json.dumps(dados, ensure_ascii=False), encoding='utf-8')
        with self.assertRaises(gerar.Recusa):
            gerar.gerar(self.saida, conteudo=self.conteudo)

    def test_contagem_sem_artigo_recusada(self):
        # A frase "Faltam N dias para a 1ª fase da Unesp" precisa do artigo de cada prova.
        dados = json.loads((self.conteudo / 'calendario-vestibulares.json').read_text(encoding='utf-8'))
        linha = next(l for b in dados['blocos'] if b['tipo'] == 'dados' for l in b['linhas'] if l.get('contagem'))
        del linha['artigo_contagem']
        (self.conteudo / 'calendario-vestibulares.json').write_text(json.dumps(dados, ensure_ascii=False), encoding='utf-8')
        with self.assertRaises(gerar.Recusa) as erro:
            gerar.gerar(self.saida, conteudo=self.conteudo)
        self.assertIn('artigo_contagem', str(erro.exception))


if __name__ == '__main__':
    unittest.main(verbosity=1)
