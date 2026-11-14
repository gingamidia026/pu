"""Extrai mídias locais, sem rede ou modelos. Dominique-Oliveira-ChatGPT🤖💚."""
import hashlib
import re
from pathlib import Path
import fitz

VERSAO = 2

def alternativas_visuais(documento, trechos, paginas, pasta, prefixo, letras='ABCDE', linhas_inteiras=False):
    """Usa as letras da fonte para separar opções gráficas ou fórmulas em células (Unicamp: A a D)."""
    ancoras=[]
    for ip,x0,y0,x1,y1 in trechos:
        for l in paginas[ip]['corpo']:
            if x0-6 <= l[0] < x1 and y0-1 <= l[1] < y1 and re.match(r'^['+letras+r'](?:\s|$)',l[4]):
                ancoras.append((l[4][0],ip,l,x0,y0,x1,y1))
    # Evita confundir letras citadas no enunciado com as opções finais.
    por_letra={a[0]:a for a in ancoras}
    if set(por_letra)!=set(letras): raise ValueError(f'Não foi possível localizar as {len(letras)} alternativas na fonte')
    ancoras=list(por_letra.values())
    if len({a[1] for a in ancoras})!=1: raise ValueError('Alternativas entre páginas exigem revisão')
    ip=ancoras[0][1]; pagina=documento[ip]
    xs=sorted({a[2][0] for a in ancoras}); dividido=max(xs)-min(xs)>60
    meio=(min(xs)+max(xs))/2 if dividido else None
    imagens=[fitz.Rect(i['bbox']) for i in pagina.get_image_info()]
    marcadas=[r for r in imagens if any(r.contains(fitz.Point(a[2][0]+16,(a[2][1]+a[2][3])/2)) for a in ancoras)]
    inicio=min([a[2][1]-1 for a in ancoras]+[r.y0 for r in marcadas])
    inicio_direita=min((a[2][0] for a in ancoras if dividido and a[2][0]>meio),default=None)
    novos=[]
    for t in trechos:
        if t[0]==ip and t[2]<inicio: novos.append((t[0],t[1],t[2],t[3],inicio-1))
        elif t[0]<ip: novos.append(t)
    corpo,nomes,evidencias=extrair(documento,novos,paginas,pasta,prefixo,linhas_inteiras)
    def linha_em_branco(y,esquerda,direita):
        caixa=fitz.Rect(esquerda,y-5,direita,y+5) & pagina.rect
        pix=pagina.get_pixmap(matrix=fitz.Matrix(2,2),clip=caixa,colorspace=fitz.csGRAY,alpha=False)
        dados=pix.samples
        scores=[sum(v<225 for v in dados[i*pix.stride:i*pix.stride+pix.width]) for i in range(pix.height)]
        linha=min(range(len(scores)),key=lambda i:(scores[i],abs(i-pix.height/2)))
        return caixa.y0+linha/2
    for letra,_,l,x0,y0,x1,y1 in sorted(ancoras):
        esquerda=not dividido or l[0]<meio
        coluna=sorted([a for a in ancoras if (not dividido or a[2][0]<meio)==esquerda],key=lambda a:a[2][1])
        k=next(i for i,a in enumerate(coluna) if a[0]==letra)
        centro=lambda a:(a[2][1]+a[2][3])/2
        topo=inicio if k==0 else (centro(coluna[k-1])+centro(coluna[k]))/2
        base=y1 if k==len(coluna)-1 else (centro(coluna[k])+centro(coluna[k+1]))/2
        direita=(inicio_direita-4 if dividido and esquerda else x1)
        if k>0:topo=linha_em_branco(topo,l[0]+12,direita)
        if k<len(coluna)-1:base=linha_em_branco(base,l[0]+12,direita)
        if k==len(coluna)-1 and not marcadas:
            finais=[linha[3] for linha in paginas[ip]['corpo'] if l[0] <= linha[0] < direita
                    and topo <= linha[1] and linha[3] <= base
                    and not re.match(r'^QUEST[ÃA]O',linha[4],re.I)]
            if finais: base=min(base,max(finais)+1)
        r=fitz.Rect(l[0]+12,topo,direita,base) & pagina.rect
        if r.is_empty: raise ValueError('Recorte de alternativa vazio')
        dados=pagina.get_pixmap(matrix=fitz.Matrix(200/72,200/72),clip=r,alpha=False).tobytes('png')
        nome=prefixo+'-'+letra+'-'+hashlib.sha256(dados).hexdigest()[:16]+'.png'
        (pasta/nome).write_bytes(dados);nomes.append(nome)
        evidencias.append({'arquivo':nome,'pagina':ip+1,'caixa':list(r),'alternativa':letra})
        corpo+='\n'+letra+' ![['+nome+']]'
    return corpo,nomes,evidencias

def unir(retangulos):
    resultado = []
    for r in retangulos:
        r = fitz.Rect(r)
        mudou = True
        while mudou:
            mudou = False
            for antigo in resultado[:]:
                margem = antigo + (-4, -4, 4, 4)
                intervalo_y=min(antigo.y1,r.y1)-max(antigo.y0,r.y0)
                distancia_x=max(0,max(antigo.x0,r.x0)-min(antigo.x1,r.x1))
                if margem.intersects(r) or (intervalo_y>2 and distancia_x<45):
                    r |= antigo
                    resultado.remove(antigo)
                    mudou = True
        resultado.append(r)
    return resultado

# Outras bancas (Fuvest 2026): símbolos de legenda em fontes de desenho, sem mapa Unicode.
FONTES_DE_SIMBOLO = re.compile(r'Wingdings|Webdings|Dingbat', re.I)


def faixa_do_marcador(r, marcadores):
    """Tarja desenhada em volta de "QUESTÃO 02" (Vunesp): enfeite do caderno, não mídia da questão."""
    return any(m[1] - 8 <= r.y0 and r.y1 <= m[3] + 8 for m in marcadores)


def tabela_de_verdade(tabela):
    """Texto corrido numa moldura também vira "tabela" no find_tables, com uma célula cheia por linha.
    Tabela de verdade tem pelo menos duas células com texto na maioria das linhas."""
    linhas = [l for l in tabela.extract() if any(c and c.strip() for c in l)]
    if len(linhas) < 2 or any(re.match(r'\s*quest[ãa]o\b', c or '', re.I) for l in linhas for c in l):
        return False  # uma linha só, ou a tarja "questão 09" com o traço de baixo
    return sum(1 for l in linhas if sum(1 for c in l if c and c.strip()) >= 2) >= len(linhas) * .5


def moldura_de_texto(r, texto, pagina):
    """Caixa ou fundo desenhado atrás de um bloco de texto corrido (quadro "Note e adote", enunciado em
    moldura): o texto continua texto. Tabelas são achadas à parte pelo find_tables."""
    dentro = [l for l in texto if r.contains(fitz.Rect(*l[:4]))]
    if len(dentro) < 2 or any(r.intersects(fitz.Rect(i['bbox'])) for i in pagina.get_image_info()):
        return False
    return sum((l[2] - l[0]) * (l[3] - l[1]) for l in dentro) > r.get_area() * .3


def extrair(documento, trechos, paginas, pasta, prefixo, linhas_inteiras=False):
    """Mantém texto em ordem; recorta objetos gráficos, nunca a questão inteira.

    Com `linhas_inteiras` (outras bancas), a fórmula no meio de uma linha de texto e o símbolo sem mapa
    Unicode levam a linha inteira para o recorte, para nenhum pedaço da frase ficar de fora."""
    partes, nomes, evidencias = [], [], []
    for ip, x0, y0, x1, y1 in trechos:
        pagina = documento[ip]
        area = fitz.Rect(x0, y0, x1, y1) & pagina.rect
        marcadores = [l for l in paginas[ip]['corpo'] if x0-6 <= l[0] < x1 and y0-1 <= l[1] < y1
                      and re.match(r'^QUEST[ÃA]O\s*\d', l[4], re.I)]
        limite_grafico = max((l[3]+2 for l in marcadores), default=area.y0)
        texto = [l for l in paginas[ip]["corpo"] if x0-6 <= l[0] < x1 and y0-1 <= l[1] < y1+2
                 and not re.match(r'^QUEST[ÃA]O\s*\d|^Texto para as quest', l[4], re.I)]
        candidatos = []
        for tabela in pagina.find_tables(clip=area).tables:
            if linhas_inteiras and not tabela_de_verdade(tabela): continue
            candidatos.append(fitz.Rect(tabela.bbox))
        for info in pagina.get_image_info():
            r = fitz.Rect(info['bbox'])
            if r.height < 8 and r.width > area.width * .65: continue
            if r.y1 < limite_grafico: continue
            if linhas_inteiras and faixa_do_marcador(r, marcadores): continue
            if r.intersects(area) and (r & area).get_area() > r.get_area() * .9:
                candidatos.append(r)
        # Linhas compridas de moldura e separadores de questão não são conteúdo.
        for desenho in pagina.get_drawings():
            r = desenho['rect']
            if not area.contains(r): continue
            if r.y0 < limite_grafico: continue
            if linhas_inteiras and faixa_do_marcador(r, marcadores): continue
            if r.height < 2 and r.width > area.width * .9: continue
            # Fundo branco sem contorno (sombreamento de parágrafo do Word) não aparece no papel
            if linhas_inteiras and desenho.get('color') is None and desenho.get('fill') in ((1.0, 1.0, 1.0), (1, 1, 1)): continue
            if linhas_inteiras and moldura_de_texto(r, texto, pagina): continue
            if linhas_inteiras and r.height < 2:
                # Sublinhado ("a oração sublinhada"): a linha de texto inteira vai junto, para o traço ter sentido
                acima = [l for l in texto if -5 <= r.y0 - l[3] <= 4 and r.y0 > (l[1] + l[3]) / 2 and l[0] < r.x1 and r.x0 < l[2]]
                for l in acima:
                    r = r | fitz.Rect(l[0], l[1], l[2], l[3])
            if max(r.width, r.height) > 5:
                candidatos.append(r + (-.5, -.5, .5, .5))
        # Fórmulas com fontes matemáticas preservam expoentes, raízes e frações.
        for bloco in pagina.get_text('dict')['blocks']:
            for linha in bloco.get('lines', []):
                for span in linha['spans']:
                    if re.search(r'Symbol|Math|Cambria|CMSY|CMMI|MTExtra', span['font'], re.I) or \
                            (linhas_inteiras and FONTES_DE_SIMBOLO.search(span['font'])):
                        r = fitz.Rect(linha['bbox'])
                        if linhas_inteiras and area.contains(r):
                            for l in texto:
                                altura = min(l[3] - l[1], r.height)
                                if altura > 0 and min(l[3], r.y1) - max(l[1], r.y0) > altura * .5:
                                    r |= fitz.Rect(l[0], l[1], l[2], l[3])
                            r &= area
                        if area.contains(r): candidatos.append(r)
        regioes = unir(candidatos)
        # Incorpora rótulos internos e tabelas; o texto fora da mídia permanece texto.
        eventos = []
        for r in regioes:
            if r.get_area() < 45: continue
            if linhas_inteiras and faixa_do_marcador(r, marcadores): continue
            if r.height < 8 and r.width > area.width * .65: continue
            # Não acrescentar linhas vizinhas a recortes baixos de fórmulas.
            folga = 0 if r.height < 20 else 2
            r = (r + (-folga, -folga, folga, folga)) & area
            if r.get_area() > area.get_area() * .94:
                raise ValueError('Objeto ocupa a questão inteira; exige OCR/revisão, sem aceitar print integral')
            dados = pagina.get_pixmap(matrix=fitz.Matrix(200/72, 200/72), clip=r, alpha=False).tobytes('png')
            nome = prefixo + '-' + hashlib.sha256(dados).hexdigest()[:16] + '.png'
            (pasta / nome).write_bytes(dados)
            nomes.append(nome)
            eventos.append((r.y0, r.x0, '![[%s]]' % nome))
            evidencias.append({'arquivo': nome, 'pagina': ip+1, 'caixa':list(r)})
        for l in texto:
            caixa = fitz.Rect(*l[:4])
            if any((caixa & r).get_area() > caixa.get_area() * .6 for r in regioes):
                continue
            eventos.append((l[1], l[0], l[4]))
        partes.extend(e[2] for e in sorted(eventos))
    return '\n'.join(partes), list(dict.fromkeys(nomes)), evidencias
