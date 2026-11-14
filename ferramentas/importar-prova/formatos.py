"""O que é de cada banca no extrator único: Fuvest (USP), Unesp, Unicamp e Famerp.

O recorte, as mídias e a classificação continuam no `importar.py` e no `midias.py`; aqui fica só o formato
de cada caderno (marcador de questão, cabeçalho e rodapé, texto comum, letras das alternativas, páginas
fora do recorte), a leitura do gabarito oficial e a gravação das notas. Sem rede, sem modelo, sem tokens.

Arquivos na pasta `Provas <Banca>/` do cofre, todos com nome só de `[A-Za-z0-9_-]`:
  <banca>-<ano>-<caderno>.pdf             caderno oficial (ex.: fuvest-2026-V1.pdf, unicamp-2026-QX.pdf)
  <banca>-<ano>-<caderno>-gabarito.pdf    gabarito oficial
  <banca>-<ano>-<caderno>.json            endereços oficiais e gabarito do inventário (fonte_url, gabarito_url,
                                          gabarito {número: letra}, anuladas, questoes)
Etapas (as mesmas do Enem): `importar.py preparar <pdf>` e `importar.py gravar <pdf>`.
Dominique-Oliveira-Claude🤖🧡, 14/11/2026.
"""
import hashlib
import json
import re
import subprocess
from pathlib import Path

NOME_ARQUIVO = re.compile(r'^(fuvest|unesp|unicamp|famerp)-(\d{4})-([A-Za-z0-9]{1,6})\.pdf$')

# Rodapé de página com o número sozinho (todas as bancas) e cabeçalhos e rodapés de cada uma.
NUMERO_DE_PAGINA = re.compile(r'^\d{1,3}$')
ALTERNATIVA_PARENTESES = re.compile(r'^\(([A-E])\)\s*')
ALTERNATIVA_MINUSCULA = re.compile(r'^([a-d])\)\s*')
# "Texto para as questões 01 e 02", "Para responder às questões de 01 a 05, leia...", "Leia o texto a seguir
# para responder às questões 30, 31 e 32.", "Texto comum às questões 34, 35, 36 e 37."
FAIXA_TEXTO_COMUM = re.compile(r'quest(?:ões|ão)\s+(?:de\s+)?(\d{1,2})((?:\s*,\s*\d{1,2})*)\s*(?:,\s*)?(?:a|e|até)\s+(\d{1,2})\b', re.I)
QUADRO_DEPOIS = re.compile(r'^(Note e adote|Dados?\b.{0,30}:|Considere:)', re.I)
INICIO_TEXTO_COMUM = re.compile(r'^(Leia|Para responder|Textos?\b|O texto|Os textos|Examine|Observe|Considere)', re.I)


class Formato:
    prova = ''
    nome = ''
    letras = 'ABCDE'
    cabecalho = re.compile(r'(?!x)x')  # nunca casa
    rodape = re.compile(r'(?!x)x')
    margem = 15  # sem cabeçalho, a área útil começa logo abaixo da margem do papel
    fim = re.compile(r'^(FIM DA QUESTÃO)$')
    # Página inteira fora do recorte: rascunho, tabela periódica, redação, questões dissertativas.
    pagina_fora = re.compile(r'^(RASCUNHO|classificação periódica|PROVA DE REDAÇÃO|REDAÇÃO|QUESTÕES DISSERTATIVAS)$', re.I)

    def normalizar_linha(self, linha, pg):
        """Devolve o texto da linha no padrão do Enem ("QUESTÃO 04", "A texto") ou None para descartar."""
        texto = re.sub(r'\s+', ' ', linha[4].replace('¬', ' ')).strip()
        if not texto:
            return None
        if m := re.match(r'^QUEST[ÃA]O\s*(\d{1,3})$', texto, re.I):
            return f'QUESTÃO {int(m[1]):02d}'
        texto = ALTERNATIVA_PARENTESES.sub(lambda m: m[1] + ' ', texto).rstrip()
        return texto

    def texto_comum(self, linhas, i):
        """Faixa (a, b) se a linha i abre um texto comum a várias questões; lê até 4 linhas da mesma coluna."""
        if not INICIO_TEXTO_COMUM.match(linhas[i][4]):
            return None
        frase, y = '', linhas[i][1]
        for l in linhas[i:i + 4]:
            if l[1] - y > 30:  # outro bloco da coluna
                break
            frase = frase[:-1] + l[4] if frase.endswith('-') else (frase + ' ' + l[4]).strip()
            y = l[1]
            if re.search(r'[.:]\s*$', l[4]):
                break
        # Só a primeira frase: "Leia o texto para responder às questões 29 e 30."
        frase = re.split(r'(?<=[^\s.]{2})[.:](?=\s|$)', frase, maxsplit=1)[0]
        m = FAIXA_TEXTO_COMUM.search(frase)
        if not m:
            um = re.search(r'^Para responder\s+(?:(?:a|à)\s+)?questão\s+(\d{1,2})\b', frase, re.I)
            return (int(um[1]), int(um[1])) if um else None
        a, b = int(m[1]), int(m[3])
        if not 0 < b - a <= 10:
            # "Para responder à questão 19, leia o texto 2": texto só de uma questão
            um = re.search(r'\bquestão\s+(\d{1,2})\b', frase, re.I)
            return (int(um[1]), int(um[1])) if um and re.match(r'^Para responder', frase, re.I) else None
        return a, b

    def ajustar_texto(self, texto):
        """Leva para antes das alternativas o quadro que o caderno imprime depois delas ("Note e adote:" da
        Fuvest, "Dados:"), para a última alternativa não engolir o quadro e a letra de dentro dele."""
        linhas = texto.split('\n')
        # Letra sozinha seguida das figuras dela ("A" e a pintura na linha de baixo, Unesp 2022, questão 20):
        # a letra e as figuras viram uma alternativa só. Só quando todas as letras estão assim.
        sozinhas = [i for i, l in enumerate(linhas) if re.fullmatch('[' + self.letras + ']', l.strip())]
        if [linhas[i].strip() for i in sozinhas][-len(self.letras):] == list(self.letras):
            sozinhas = sozinhas[-len(self.letras):]
            if all(i + 1 < len(linhas) and linhas[i + 1].startswith('![[') for i in sozinhas):
                novas, i = [], 0
                while i < len(linhas):
                    if i in sozinhas:
                        figuras = []
                        while i + 1 < len(linhas) and linhas[i + 1].startswith('![[') and i + 1 not in sozinhas:
                            i += 1
                            figuras.append(linhas[i])
                        novas.append(linhas[i - len(figuras)].strip() + ' ' + ' '.join(figuras))
                    else:
                        novas.append(linhas[i])
                    i += 1
                linhas = novas
                texto = '\n'.join(linhas)
        ultima = self.letras[-1]
        fim = max((i for i, l in enumerate(linhas) if re.match('^' + ultima + r'(\s|$)', l)), default=None)
        if fim is None:
            return texto
        nota = next((i for i in range(fim + 1, len(linhas)) if QUADRO_DEPOIS.match(linhas[i])), None)
        inicio = max((i for i, l in enumerate(linhas[:fim]) if re.match(r'^A(\s|$)', l)), default=None)
        if nota is None or inicio is None:
            return texto
        return '\n'.join(linhas[:inicio] + linhas[nota:] + linhas[inicio:nota])

    def alternativas_visuais(self, documento, trechos, paginas, pasta, prefixo, letras):
        """Alternativas gráficas com a letra ao lado da figura, centrada nela (Fuvest 2026, questão 05).

        Cada figura (desenho ou imagem) vai para a letra mais próxima pelo centro, na mesma coluna; o recorte
        da alternativa cobre a figura inteira, e não só o que fica abaixo da letra. Alternativa sem figura (fórmula
        em texto) leva as linhas até a letra seguinte. Cada trecho é cortado no começo das próprias alternativas,
        para o enunciado não sumir quando as letras se dividem entre colunas."""
        import fitz
        from midias import alternativas_visuais, extrair
        padrao = re.compile(r'^[' + letras + r'](?:\s|$)')
        candidatas = []  # em ordem de leitura: trecho, subcoluna das letras (A B C | D E), altura
        for t in trechos:
            ip, x0, y0, x1, y1 = t
            achadas = [l for l in paginas[ip]['corpo'] if x0 - 6 <= l[0] < x1 and y0 - 1 <= l[1] < y1 and padrao.match(l[4])]
            xs = sorted({l[0] for l in achadas})
            cortes = [b for a, b in zip(xs, xs[1:]) if b - a > 60]
            for l in sorted(achadas, key=lambda l: (sum(l[0] >= c for c in cortes), l[1])):
                candidatas.append((l[4][0], (ip, l, t)))
        # A última sequência A, B, C... em ordem: um "A posição..." no quadro depois de E não vira alternativa
        ancoras, limite = {}, len(candidatas)
        for letra in reversed(letras):
            achada = next((i for i in range(limite - 1, -1, -1) if candidatas[i][0] == letra), None)
            if achada is None:
                break
            ancoras[letra], limite = candidatas[achada][1], achada
        if set(ancoras) != set(letras) or len({a[0] for a in ancoras.values()}) != 1:
            return alternativas_visuais(documento, trechos, paginas, pasta, prefixo, letras, True)
        ip = next(iter(ancoras.values()))[0]
        pagina = documento[ip]
        # Cada trecho da página vai até o começo do trecho seguinte: a coluna da direita pode ter só as letras
        # em texto e as figuras mais à direita delas (Fuvest 2024, questão 26).
        da_pagina = sorted([t for t in trechos if t[0] == ip], key=lambda t: t[1])
        meia = pagina.rect.width / 2
        largura = {t: min(da_pagina[i + 1][1] - 3 if i + 1 < len(da_pagina) else pagina.rect.width - 15,
                          meia - 3 if t[3] < meia + 10 else pagina.rect.width - 15) for i, t in enumerate(da_pagina)}
        centro = lambda r: (r[1] + r[3]) / 2
        celulas = {}
        for t in da_pagina:
            membros = sorted([(l, letra) for letra, (_, l, tt) in ancoras.items() if tt == t], key=lambda a: a[0][1])
            if not membros:
                continue
            xs = sorted({l[0] for l, _ in membros})
            meio = (xs[0] + xs[-1]) / 2 if xs[-1] - xs[0] > 60 else None
            for l, letra in membros:
                esquerda = meio is None or l[0] < meio
                direita = min((m[0][0] for m in membros if meio is not None and m[0][0] > meio), default=None)
                coluna = [m for m in membros if (meio is None or m[0][0] < meio) == esquerda]
                k = [m[1] for m in coluna].index(letra)
                celulas[letra] = {'linha': l, 'trecho': t, 'figuras': [],
                                  'x0': l[2] + 1 if len(l[4].strip()) == 1 else l[0] + 12,
                                  'x1': direita - 4 if (esquerda and direita) else max(t[3], largura[t]),
                                  'seguinte': coluna[k + 1][0] if k + 1 < len(coluna) else None}
        passos = [centro(c['seguinte']) - centro(c['linha']) for c in celulas.values() if c['seguinte']]
        passo = min(passos) if passos else 200
        regioes = [fitz.Rect(t[1], t[2], max(t[3], largura[t]), t[4]) for t in da_pagina]
        graficos = [fitz.Rect(i['bbox']) for i in pagina.get_image_info()]
        graficos += [d['rect'] for d in pagina.get_drawings() if max(d['rect'].width, d['rect'].height) > 5]
        graficos = [g for g in graficos if any(r.contains(g) for r in regioes) and not (g.height < 2 and g.width > 150) and not (g.width < 2 and g.height > 200)]
        # Junta só o que se toca (unir() do midias juntaria figuras vizinhas de alternativas lado a lado)
        blocos = []
        for g in sorted(graficos, key=lambda r: (r.y0, r.x0)):
            g = fitz.Rect(g)
            for outro in [o for o in blocos if (o + (-2, -2, 2, 2)).intersects(g)]:
                g |= outro
                blocos.remove(outro)
            blocos.append(g)
        for g in blocos:
            perto = [(abs((g.y0 + g.y1) / 2 - centro(c['linha'])), letra) for letra, c in celulas.items()
                     if c['linha'][0] - 4 <= g.x0 and g.x1 <= c['x1'] + 4]
            if perto:
                distancia, letra = min(perto)
                c = celulas[letra]
                # Figura acima da letra com texto do enunciado no meio não é da alternativa
                entre = g.y1 < c['linha'][1] and any(
                    o is not c['linha'] and c['x0'] - 20 <= o[0] < c['x1'] and g.y1 - 1 <= o[1] and o[3] <= c['linha'][1] + 1
                    for o in paginas[ip]['corpo'])
                if distancia <= passo * .75 and not entre:
                    c['figuras'].append(g)
        caixas = {}
        for letra, c in celulas.items():
            l = c['linha']
            caixa = fitz.Rect(c['x0'], l[1], max(c['x0'] + 10, l[2]), l[3])
            if c['figuras']:
                for g in c['figuras']:
                    caixa |= g
            else:
                # Alternativa em texto com fórmula: as linhas até a próxima letra da mesma coluna
                limite = c['seguinte'][1] - 1 if c['seguinte'] else c['trecho'][4]
                ultimo = l[3]
                for o in sorted(paginas[ip]['corpo'], key=lambda o: o[1]):
                    if o is l or not (c['x0'] - 14 <= o[0] < c['x1']) or not (l[1] < o[1] < limite):
                        continue
                    if c['seguinte'] is None and o[1] - ultimo > 12:
                        break
                    caixa |= fitz.Rect(max(o[0], c['x0']), o[1], o[2], o[3])
                    ultimo = o[3]
                for b in pagina.get_text('dict')['blocks']:  # expoentes e frações que o pdftotext não pôs na linha
                    for linha in b.get('lines', []):
                        r = fitz.Rect(linha['bbox'])
                        if caixa.intersects(r) and c['x0'] - 2 <= r.x0 and r.x1 <= c['x1'] + 4:
                            caixa |= r
            caixas[letra] = (caixa + (-2, -2, 2, 2)) & pagina.rect
        cortes = {}
        for letra, c in celulas.items():
            t = c['trecho']
            cortes[t] = min(cortes.get(t, t[4]), caixas[letra].y0, c['linha'][1] - 1)
        novos = [t for t in trechos if t[0] < ip]
        novos += [(t[0], t[1], t[2], t[3], cortes.get(t, t[4]) - 1) for t in trechos if t[0] == ip and t[2] < cortes.get(t, t[4])]
        corpo, nomes, evidencias = extrair(documento, novos, paginas, pasta, prefixo, True)
        # O que vem depois da última alternativa no mesmo trecho (quadro "Note e adote") vai antes delas
        depois = []
        for t in da_pagina:
            fins = [caixas[letra].y1 for letra, c in celulas.items() if c['trecho'] == t]
            if fins and max(fins) + 2 < t[4]:
                depois.append((t[0], t[1], max(fins) + 2, t[3], t[4]))
        if depois:
            resto, nomes_resto, evid_resto = extrair(documento, depois, paginas, pasta, prefixo, True)
            if resto.strip():
                corpo, nomes, evidencias = corpo + '\n' + resto, nomes + nomes_resto, evidencias + evid_resto
        for letra in letras:
            r = caixas[letra]
            dados = pagina.get_pixmap(matrix=fitz.Matrix(200 / 72, 200 / 72), clip=r, alpha=False).tobytes('png')
            nome = prefixo + '-' + letra + '-' + hashlib.sha256(dados).hexdigest()[:16] + '.png'
            (pasta / nome).write_bytes(dados)
            nomes.append(nome)
            evidencias.append({'arquivo': nome, 'pagina': ip + 1, 'caixa': list(r), 'alternativa': letra})
            corpo += '\n' + letra + ' ![[' + nome + ']]'
        return corpo, nomes, evidencias

    def normalizar(self, paginas):
        """Limpa as linhas de cada página e marca a área útil entre o cabeçalho e o rodapé da banca."""
        for pg in paginas:
            h = pg['h']
            originais = pg['linhas']
            textos = [re.sub(r'\s+', ' ', l[4].replace('¬', ' ')).strip() for l in originais]
            if any(self.pagina_fora.match(t) for t in textos) and not any(re.match(r'^QUEST[ÃA]O\s*\d', t, re.I) for t in textos):
                pg['linhas'], pg['limites'] = [], (self.margem, h - self.margem)
                continue
            topo, base, linhas = self.margem, h - self.margem, []
            for l, t in zip(originais, textos):
                if not t:
                    continue
                if (l[1] < h * .08 and self.cabecalho.search(t)):
                    topo = max(topo, l[3] + 2)
                    continue
                if (l[1] > h * .92 and (self.rodape.search(t) or NUMERO_DE_PAGINA.match(t))):
                    base = min(base, l[1] - 1)
                    continue
                novo = self.normalizar_linha(l, pg)
                if novo is not None:
                    linhas.append((l[0], l[1], l[2], l[3], novo))
            pg['linhas'], pg['limites'] = linhas, (topo, base)


class Fuvest(Formato):
    prova, nome = 'fuvest', 'Fuvest'
    cabecalho = re.compile(r'Concurso Vestibular FUVEST', re.I)
    fim = re.compile(r'^(FIM DA QUESTÃO)$')

    def normalizar_linha(self, linha, pg):
        t = re.sub(r'\s+', ' ', linha[4].replace('¬', ' ')).strip()
        if t in ('{', '}', '{}'):
            return None
        if re.fullmatch(r'#{3,}', t):
            return 'FIM DA QUESTÃO'
        # 2025 a 2027: "{ 04}" (a chave pode vir numa linha separada); 2023 e 2024: "04" em corpo grande,
        # na margem esquerda da coluna.
        if m := re.fullmatch(r'\{?\s*(\d{1,2})\s*\}', t):
            return f'QUESTÃO {int(m[1]):02d}'
        if re.fullmatch(r'\d{2}', t) and linha[3] - linha[1] > 14 and (linha[0] < 60 or abs(linha[0] - pg['w'] / 2 - 14) < 20):
            return f'QUESTÃO {int(t):02d}'
        return super().normalizar_linha(linha, pg)


class Vunesp(Formato):
    """Unesp e Famerp: o mesmo caderno da Vunesp."""
    rodape = re.compile(r'Confidencial até o momento|^(VNSP|FMRP)\d+', re.I)

    def normalizar_linha(self, linha, pg):
        t = re.sub(r'\s+', ' ', linha[4].replace('¬', ' ')).strip()
        # Hífen suave (U+00AD) que a Vunesp deixa no meio de palavras ("s­eguinte")
        linha = (*linha[:4], t.replace('­', ''))
        return super().normalizar_linha(linha, pg)


class Unesp(Vunesp):
    prova, nome = 'unesp', 'Unesp'


class Famerp(Vunesp):
    prova, nome = 'famerp', 'Famerp'


class Unicamp(Formato):
    prova, nome, letras = 'unicamp', 'Unicamp', 'ABCD'

    def normalizar_linha(self, linha, pg):
        t = re.sub(r'\s+', ' ', linha[4].replace('¬', ' ')).strip()
        t = ALTERNATIVA_MINUSCULA.sub(lambda m: m[1].upper() + ' ', t)
        return super().normalizar_linha((*linha[:4], t), pg)


FORMATOS = {f.prova: f for f in (Fuvest(), Unesp(), Unicamp(), Famerp())}


def identificar(pdf):
    """(banca, ano, caderno) para `fuvest-2026-V1.pdf` e semelhantes; None para outro nome."""
    m = NOME_ARQUIVO.match(Path(pdf).name)
    return (m[1], int(m[2]), m[3]) if m else None


def formato_de(pdf):
    ident = identificar(pdf)
    return FORMATOS[ident[0]] if ident else None


# ---------- gabarito oficial ----------

def gabarito_do_pdf(pdf, banca, caderno):
    """Lê o gabarito oficial com o pdftotext: {número: 'A'..'E', '*' (anulada) ou 'D E' (duas letras)}."""
    texto = subprocess.run(['pdftotext', '-layout', str(pdf), '-'], capture_output=True, text=True, check=True).stdout
    respostas = {}
    if banca == 'unicamp':
        # Uma página por par de cadernos: "PROVAS Q e Z". Fica só a do caderno.
        rotulo = ' e '.join(caderno)
        partes = re.split(r'PROVAS\s+([A-Z] e [A-Z])', texto)
        trecho = next((partes[i + 1] for i in range(1, len(partes) - 1, 2) if partes[i] == rotulo), None)
        if trecho is None:
            raise ValueError(f'Gabarito sem a página do caderno {rotulo}')
        for n, letra in re.findall(r'\b(\d{1,2})\s+([A-D*])(?=\s|$)', trecho):
            respostas.setdefault(int(n), letra)
    elif banca == 'fuvest':
        # Quatro ou cinco versões lado a lado; a primeira de cada linha é a do caderno V/V1.
        for linha in texto.splitlines():
            for n, letra in re.findall(r'(?<![\d/])(\d{1,2})\s+([A-E*](?:\s?[A-E])?)(?=\s+\d|\s*$)', linha):
                respostas.setdefault(int(n), re.sub(r'\s', '', letra))
    else:
        for n, letra in re.findall(r'\b(\d{1,2})\s*-\s*([A-E*])\b', texto):
            respostas.setdefault(int(n), letra)
    return {n: ('*' if r == '*' else r if len(r) == 1 else ' '.join(r)) for n, r in respostas.items()}


def conferir_gabarito(info, pdf_gabarito, banca, caderno, letras):
    """Gabarito do inventário conferido contra o PDF oficial. Devolve {n: resposta} e {n: motivo de dúvida}."""
    oficial = gabarito_do_pdf(pdf_gabarito, banca, caderno)
    inventario = {int(k): v for k, v in info['gabarito'].items()}
    anuladas = set(info.get('anuladas', []))
    respostas, duvidas = {}, {}
    for n in range(1, info['questoes'] + 1):
        inv, pdf = inventario.get(n), oficial.get(n)
        if n in anuladas or inv == '*' or pdf == '*':
            respostas[n] = 'Anulada'
            if not (n in anuladas and inv == '*' and pdf == '*'):
                duvidas[n] = f'anulação diverge entre o inventário ({inv}) e o PDF oficial ({pdf})'
            continue
        if pdf is None or inv is None:
            duvidas[n] = 'questão sem resposta no gabarito oficial'
        elif len(pdf) != 1 or pdf not in letras:
            duvidas[n] = f'gabarito oficial traz "{pdf}" sem legenda; não há como saber qual letra vale'
        elif inv != pdf:
            duvidas[n] = f'gabarito do inventário ({inv}) diferente do PDF oficial ({pdf})'
        respostas[n] = pdf if pdf and len(pdf) == 1 and pdf in letras else None
    return respostas, duvidas


# ---------- etapas ----------

def pasta_da_prova(banca):
    import importar
    return importar.COFRE / f'Provas {FORMATOS[banca].nome}'


def trabalho_de(pdf):
    banca = identificar(pdf)[0]
    return pasta_da_prova(banca) / 'Entrada' / '.trabalho' / Path(pdf).stem


def cmd_preparar(pdf):
    import importar
    banca, ano, caderno = identificar(pdf)
    formato = FORMATOS[banca]
    meta = json.loads(pdf.with_suffix('.json').read_text(encoding='utf-8'))
    gabarito_pdf = pdf.with_name(pdf.stem + '-gabarito.pdf')
    respostas, duvidas = conferir_gabarito(meta, gabarito_pdf, banca, caderno, formato.letras)
    questoes = importar.recortar(pdf, f'{banca}-{ano}', importar.IMAGENS)
    esperado = list(range(1, meta['questoes'] + 1))
    numeros = [q['n'] for q in questoes]
    problemas = []
    if numeros != esperado:
        faltam = sorted(set(esperado) - set(numeros))
        repetidas = sorted({n for n in numeros if numeros.count(n) > 1})
        sobram = sorted(set(numeros) - set(esperado))
        problemas.append(f'numeração diferente do esperado: faltam {faltam}, repetidas {repetidas}, sobram {sobram}')
    for q in questoes:
        q['area'], q['lingua'] = '?', False
        q['gabarito'] = respostas.get(q['n'])
        if q['n'] in duvidas:
            q['duvida_gabarito'] = duvidas[q['n']]
            problemas.append(f"Q{q['n']}: {duvidas[q['n']]}")
        if not q['completa']:
            problemas.append(f"Q{q['n']} sem as alternativas {formato.letras[0]}–{formato.letras[-1]} no texto")
        if q.get('falha'):
            problemas.append(f"Q{q['n']}: {q['falha']}")
    pasta = trabalho_de(pdf)
    pasta.mkdir(parents=True, exist_ok=True)
    info = {'prova': str(pdf), 'banca': banca, 'gabarito': str(gabarito_pdf), 'ano': ano, 'dia': 1, 'caderno': caderno,
            'fonte_url': meta['fonte_url'], 'gabarito_url': meta['gabarito_url'], 'questoes': questoes, 'problemas': problemas}
    (pasta / 'trabalho.json').write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding='utf-8')
    escrever_resumo(pasta, questoes)
    print(f'{len(questoes)} questões recortadas de {pdf.name} ({formato.nome} {ano}, caderno {caderno})')
    print(f'Para classificar: {pasta / "para_classificar.txt"}')
    print('Problemas:' if problemas else 'Sem problemas.')
    for p in problemas:
        print(' -', p)


def escrever_resumo(pasta, questoes):
    """O resumo do Enem, com o começo do texto comum na frente (sem ele, "De acordo com o texto, ..." não diz
    a matéria) e sem os nomes das imagens."""
    import importar
    copias = []
    for q in questoes:
        texto = re.sub(r'!\[\[[^]]+\]\]', ' ', q['texto'])
        comum = re.sub(r'\s+', ' ', re.sub(r'!\[\[[^]]+\]\]', ' ', q.get('texto_comum', ''))).strip()
        if comum:
            texto = f'(Texto comum: {comum[:140]}) ' + texto
        copias.append({**q, 'texto': texto})
    importar.escrever_resumo(pasta, copias)


AREA_DA_MATERIA = {'POR': 'Linguagens', 'LIT': 'Linguagens', 'ART': 'Linguagens', 'ING': 'Linguagens', 'EDF': 'Linguagens',
                   'HIS': 'Ciências Humanas', 'GEO': 'Ciências Humanas', 'FIL': 'Ciências Humanas', 'SOC': 'Ciências Humanas',
                   'BIO': 'Ciências da Natureza', 'FIS': 'Ciências da Natureza', 'QUI': 'Ciências da Natureza', 'MAT': 'Matemática'}


def grupos_no_ar(questoes, fora):
    """Grupo de texto comum de cada questão, só com as questões que entram no ar.

    A sincronização exige que todas as questões da faixa `:Qaa a bb` estejam no catálogo. Se uma delas é
    anulada ou fica fora do ar, a faixa vira o trecho contínuo das que entram; questão sozinha fica sem grupo,
    com o texto comum na própria nota."""
    resultado = {}
    for q in questoes:
        if not q.get('grupo') or q['n'] in fora:
            continue
        base, faixa = q['grupo'].rsplit(':Q', 1)
        a, b = map(int, faixa.split('a'))
        ini = q['n']
        while ini - 1 >= a and ini - 1 not in fora:
            ini -= 1
        fim = q['n']
        while fim + 1 <= b and fim + 1 not in fora:
            fim += 1
        if fim > ini:
            resultado[q['n']] = f'{base}:Q{ini:02d}a{fim:02d}'
    return resultado


def cmd_gravar(pdf):
    import importar
    banca, ano, caderno = identificar(pdf)
    formato = FORMATOS[banca]
    pasta = trabalho_de(pdf)
    info = json.loads((pasta / 'trabalho.json').read_text(encoding='utf-8'))
    if any(q.get('extrator') != 2 for q in info['questoes']):
        raise ValueError('Reprepare a prova com o extrator atual antes de gravar')
    classif = importar.ler_classificacao(pasta)
    tax = importar.todas_taxonomias()
    fora = {}
    for q in info['questoes']:
        motivo = []
        if not q.get('completa'):
            motivo.append(q.get('falha') or 'alternativas incompletas')
        elif q.get('falha'):
            motivo.append(q['falha'])
        if q.get('duvida_gabarito') and q['gabarito'] != 'Anulada':
            motivo.append(q['duvida_gabarito'])
        elif q['gabarito'] != 'Anulada' and q['gabarito'] not in list(formato.letras):
            motivo.append('gabarito ausente ou incerto')
        if motivo:
            fora[q['n']] = '; '.join(motivo)
    anuladas = {q['n'] for q in info['questoes'] if q['gabarito'] == 'Anulada'}
    grupos = grupos_no_ar(info['questoes'], set(fora) | anuladas)
    pasta_notas = pasta_da_prova(banca) / 'Questões' / str(ano)
    pasta_notas.mkdir(parents=True, exist_ok=True)
    assinatura = hashlib.sha256(Path(info['prova']).read_bytes()).hexdigest()
    revisar, sem_codigo = [], []
    for q in info['questoes']:
        c = classif.get(f"Q{q['n']}", {})
        item = tax.get(c.get('codigo'))
        anulada = q['n'] in anuladas
        if c.get('codigo') and not item:
            print(f"Aviso: código desconhecido {c.get('codigo')} em Q{q['n']}")
        if not item and not anulada:
            sem_codigo.append(q['n'])
        marcar = bool(c.get('revisar') or (not item and not anulada))
        if marcar:
            revisar.append(q['n'])
        area = AREA_DA_MATERIA.get(c.get('codigo', '').split('-')[0], '') if item else ''
        if not area and not anulada and q['n'] not in fora:
            fora[q['n']] = 'sem classificação de matéria; área desconhecida'
        motivo_fora = fora.get(q['n'], '')
        titulo = f"{formato.nome} {ano} · Questão {q['n']:02d}"
        fm = ['---', f'prova: {banca}', f'ano: {ano}', 'dia: 1', f'caderno: {caderno}', f"questão: {q['n']}",
              f'área: {area}', f"matéria: {item['materia'].split('- ', 1)[1] if item else ''}",
              f"tópico: {json.dumps(item['topico'], ensure_ascii=False) if item else ''}",
              f"assunto: {json.dumps(item['assunto'], ensure_ascii=False) if item else ''}",
              f"conteúdo: {json.dumps(item['conteudo'], ensure_ascii=False) if item else ''}",
              f"código: {c.get('codigo') or ''}", f"gabarito: {'' if anulada else q['gabarito'] or ''}",
              f'anulada: {str(anulada).lower()}', f'revisar: {str(marcar).lower()}',
              f'fora_do_ar: {str(bool(motivo_fora)).lower()}',
              f"fonte_url: {json.dumps(info['fonte_url'])}", f"gabarito_url: {json.dumps(info['gabarito_url'])}",
              f"origem_arquivo: {json.dumps(Path(info['prova']).name)}", f'origem_sha256: {assinatura}', 'extrator: 2']
        if q['n'] in grupos:
            fm.append('grupo: ' + json.dumps(grupos[q['n']]))
        fm += ['autores:', '  - Dominique-Oliveira-Claude🤖🧡', 'tags:', f'  - {banca}', f'  - {banca}-{ano}', '---']
        corpo = [f'# {titulo}', '', f"**Gabarito:** {'Anulada' if anulada else q['gabarito'] or '—'}"]
        if c.get('obs'):
            corpo.append(f"**Observação:** {c['obs']}")
        if motivo_fora:
            corpo.append(f'**Fora do ar até revisão:** {motivo_fora}')
        if q.get('texto_comum'):
            corpo += ['', '## Texto comum', '', q['texto_comum']]
        corpo += ['', '## Texto', '', q['texto']]
        (pasta_notas / f"{q['nome']}.md").write_text('\n'.join(fm + corpo) + '\n', encoding='utf-8')
    print(f"Notas gravadas em {pasta_notas}: {len(info['questoes'])}")
    print(f'Fora do ar ({len(fora)}): ' + '; '.join(f'Q{n}: {m}' for n, m in sorted(fora.items())))
    print(f'Anuladas: {sorted(anuladas)} · para revisar ({len(revisar)}): {revisar} · sem código: {sem_codigo}')
