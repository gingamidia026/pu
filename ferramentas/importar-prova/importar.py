#!/usr/bin/env python3
"""Importa uma prova do Enem para o cofre Vestibular.

Etapas:
  preparar <prova.pdf>   baixa o gabarito, recorta as questões e grava o trabalho.json
  taxonomia <área>       lista os conteúdos da área, com o código usado na classificação
  gravar <prova.pdf>     lê classificacao.txt e grava as notas das questões e as cartas
"""
import html
import argparse
import hashlib
import os
from datetime import datetime, timezone
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import fitz
except ImportError:
    interpretador = Path("/home/dominique/craft/Enem/.venv-extracao/bin/python")
    if interpretador.exists() and Path(sys.executable) != interpretador:
        os.execv(str(interpretador), [str(interpretador), str(Path(__file__).resolve()), *sys.argv[1:]])
    raise SystemExit("Extrator local indisponível; instale os requisitos da ferramenta no ambiente virtual")

from PIL import Image, ImageChops

COFRE = Path(os.environ.get("PU_COFRE_VESTIBULAR", "/home/dominique/backup/Estudos/Vestibular"))
PROVAS = COFRE / "Provas Enem"
ENTRADA = PROVAS / "Entrada"
QUESTOES = PROVAS / "Questões"
MATERIAS = COFRE / "Matérias"
FLASHCARDS = MATERIAS / "Flashcards"
# O plugin note-mover-shortcut leva todo .png para esta pasta; as imagens já nascem nela
IMAGENS = FLASHCARDS / "Imagens exercícios"
INEP = "https://download.inep.gov.br/enem/provas_e_gabaritos/"
DPI = 200

AREAS = {
    "LC": ("Linguagens", ["1- Português", "1- Literatura", "1- Artes", "1- Inglês", "1- Educação Física"]),
    "CH": ("Ciências Humanas", ["2- História", "2- Geografia", "2- Filosofia", "2- Sociologia"]),
    "CN": ("Ciências da Natureza", ["4- Biologia", "4- Física", "4- Química"]),
    "MT": ("Matemática", ["3- Matemática"]),
}
CODIGOS = {
    "1- Português": "POR", "1- Literatura": "LIT", "1- Artes": "ART", "1- Inglês": "ING", "1- Educação Física": "EDF",
    "2- História": "HIS", "2- Geografia": "GEO", "2- Filosofia": "FIL", "2- Sociologia": "SOC",
    "3- Matemática": "MAT", "4- Biologia": "BIO", "4- Física": "FIS", "4- Química": "QUI",
}
CORES = {1: "azul", 7: "azul", 2: "amarelo", 5: "amarelo", 3: "branco", 6: "cinza", 4: "rosa", 8: "rosa"}

MARCADOR = re.compile(r"^QUEST[ÃA]O\s*(\d{1,3})\b", re.I)
# "Texto para as questões de 06 a 10": texto comum a várias questões
TEXTO_COMUM = re.compile(r"^Texto para as quest(?:ões|ão)\s+(?:de\s+)?(\d+)\s+(?:a|e)\s+(\d+)", re.I)
# Linhas que encerram a questão anterior: títulos de área, opção de língua e redação
# Cabeçalho e rodapé sem faixa: "LC - 1° dia | Caderno 1 - AZUL", "–CH • 1º DIA • CADERNO 1 • AZUL–",
# código de barras "*010175AZ4*" e número de página (este só bem perto da borda).
BORDA = re.compile(r"(\bdia\b.*\bcaderno\b|^\*[0-9A-Z]+\*$|^\d{1,3}$)", re.I)
FIM = re.compile(r"^(Questões de \d|PROPOSTA DE REDAÇÃO|INSTRUÇÕES PARA A REDAÇÃO|"
                 r"(LINGUAGENS, CÓDIGOS|CIÊNCIAS HUMANAS|CIÊNCIAS DA NATUREZA|MATEMÁTICA) E SUAS TECNOLOGIAS$)", re.I)


def identificar(pdf):
    m = re.match(r"(\d{4})_PV_impresso_D(\d)_CD(\d+)\.pdf$", pdf.name)
    if not m:
        sys.exit(f"Nome fora do padrão do Inep: {pdf.name} (esperado: 2024_PV_impresso_D1_CD1.pdf)")
    ano, dia, caderno = map(int, m.groups())
    return ano, dia, caderno


def area_da_questao(ano, n):
    # Até 2016: 1º dia Humanas e Natureza, 2º dia Linguagens e Matemática
    if ano <= 2016:
        return "CH" if n <= 45 else "CN" if n <= 90 else "LC" if n <= 135 else "MT"
    return "LC" if n <= 45 else "CH" if n <= 90 else "CN" if n <= 135 else "MT"


def lingua_estrangeira(ano, n):
    return (ano <= 2016 and 91 <= n <= 95) or (ano > 2016 and 1 <= n <= 5)


# ---------- gabarito ----------

def gabarito(pdf):
    gb = pdf.with_name(pdf.name.replace("_PV_", "_GB_"))
    if not gb.exists():
        destino = PROVAS / gb.name
        if not destino.exists():
            print(f"Baixando o gabarito {gb.name} do Inep")
            urllib.request.urlretrieve(INEP + gb.name, destino)
        gb = destino
    texto = subprocess.run(["pdftotext", "-layout", str(gb), "-"], capture_output=True, text=True).stdout
    respostas = {}
    for linha in texto.splitlines():
        atual = None
        for tok in linha.split():
            if tok.isdigit() and 1 <= int(tok) <= 180:
                atual = int(tok)
                respostas.setdefault(atual, [])
            elif atual and (re.fullmatch(r"[A-E]", tok) or tok.lower().startswith("anulad")):
                respostas[atual].append("Anulada" if tok.lower().startswith("anulad") else tok)
    # Em questões de língua, a primeira resposta é a de inglês
    return {n: r[0] for n, r in respostas.items() if r}, gb


# ---------- leitura das páginas ----------

def ler_paginas(pdf):
    with tempfile.TemporaryDirectory() as tmp:
        saida = Path(tmp) / "bbox.html"
        subprocess.run(["pdftotext", "-bbox-layout", str(pdf), str(saida)], check=True)
        t = saida.read_text(encoding="utf-8", errors="replace")
    paginas = []
    for p in re.split(r"<page ", t)[1:]:
        w, h = map(float, re.search(r'width="([\d.]+)" height="([\d.]+)"', p).groups())
        linhas = []
        for lm in re.finditer(r'<line xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</line>', p, re.S):
            texto = " ".join(html.unescape(x) for x in re.findall(r"<word[^>]*>(.*?)</word>", lm.group(5)))
            linhas.append((*map(float, lm.groups()[:4]), texto))
        paginas.append({"w": w, "h": h, "linhas": linhas})
    return paginas


def preparar_pagina(pg):
    """Acha a área útil (entre as faixas ENEM do topo e do rodapé) e as colunas."""
    # Faixas horizontais "ENEM2024ENEM2024..." do topo e do rodapé (há também uma vertical na margem)
    eh_faixa = [bool(re.match(r"(ENEM\d{4}){3}", l[4].replace(" ", ""))) for l in pg["linhas"]]
    faixas = [l for l, f in zip(pg["linhas"], eh_faixa) if f and l[2] - l[0] > l[3] - l[1]]
    # Sem faixa no topo ou no rodapé (Enem 2021 a 2023: código de barras ou cabeçalho curto no topo,
    # "LC - 1° dia | Caderno 1" no rodapé), o limite são as linhas coladas na borda da página.
    h = pg["h"]
    cabecalho = [l[3] for l in pg["linhas"] if l[3] < h * 0.1 and BORDA.search(l[4])]
    rodape = [l[1] for l in pg["linhas"] if (l[1] > h * 0.9 and BORDA.search(l[4]) and not l[4].strip().isdigit())
              or (l[1] > h * 0.94 and l[4].strip().isdigit())]
    topo = max([l[3] for l in faixas if l[1] < pg["h"] * 0.3], default=max(cabecalho, default=28)) + 2
    base = min([l[1] for l in faixas if l[1] > pg["h"] * 0.7], default=min(rodape, default=pg["h"] - 28)) - 1
    corpo = [l for l, f in zip(pg["linhas"], eh_faixa) if not f and topo <= l[1] and l[3] <= base + 1]
    meio = pg["w"] / 2
    cruzam = [l for l in corpo if l[0] < meio - 20 and l[2] > meio + 20]
    duas = len(cruzam) <= max(2, len(corpo) * 0.08)
    if corpo:
        x0 = min(l[0] for l in corpo) - 4
        x1 = max(l[2] for l in corpo) + 4
    else:
        x0, x1 = 50, pg["w"] - 50
    colunas = [(x0, meio - 3), (meio + 3, x1)] if duas else [(x0, x1)]
    pg.update(topo=topo, base=base, corpo=juntar_mesma_linha(corpo, colunas), colunas=colunas)


LETRAS_SOLTAS = set("ABCDE")
PALAVRA = re.compile(r"^[^\W\d_]{2,}")  # pedaço que começa por palavra de duas letras ou mais


def juntar_mesma_linha(linhas, colunas, folga=25):
    """Junta pedaços de uma mesma linha dentro da coluna: a letra da alternativa separada do texto
    e um pouco mais baixa que ele (Enem 2022) e as palavras de linha justificada que o pdftotext
    parte em várias (Enem 2021). Agrupa por sobreposição vertical e junta da esquerda para a direita."""
    def mesma_altura(a, b):
        altura = min(a[3] - a[1], b[3] - b[1])
        return altura > 0 and min(a[3], b[3]) - max(a[1], b[1]) > altura * .6
    resultado, usadas = [], set()
    for cx0, cx1 in colunas:
        coluna = sorted([l for l in linhas if cx0 - 6 <= l[0] < cx1 and id(l) not in usadas], key=lambda l: (l[1], l[0]))
        usadas.update(id(l) for l in coluna)
        fileiras = []
        for l in coluna:
            fileira = next((f for f in reversed(fileiras[-3:]) if mesma_altura(f[0], l)), None)
            (fileira.append(l) if fileira is not None else fileiras.append([l]))
        for fileira in fileiras:
            atual, ultimo = None, None
            for l in sorted(fileira, key=lambda l: l[0]):
                # Só junta a letra da alternativa ao texto ou duas palavras da mesma altura. Pedaços de fórmula
                # (frações, parênteses, símbolos) ficam separados para o recorte de mídia continuar cobrindo-os.
                letra = atual is not None and atual[4] in LETRAS_SOLTAS and atual is ultimo and re.match(r"[^\W_]", l[4])
                palavras = ultimo is not None and PALAVRA.search(ultimo[4]) and PALAVRA.search(l[4]) \
                    and abs((ultimo[3] - ultimo[1]) - (l[3] - l[1])) < 1.5
                if atual and -2 <= l[0] - atual[2] < folga and (letra or palavras):
                    ultimo = l
                    atual = (atual[0], min(atual[1], l[1]), max(atual[2], l[2]), max(atual[3], l[3]), atual[4] + ' ' + l[4])
                    continue
                if atual:
                    resultado.append(atual)
                atual = ultimo = l
            resultado.append(atual)
    resultado += [l for l in linhas if id(l) not in usadas]
    return sorted(resultado, key=lambda l: (l[1], l[0]))


def alternativas_completas(linhas):
    letras = [l[4][0] for l in linhas if re.match(r"^[A-E](\s|$)", l[4])]
    return "E" in letras and "D" in letras


def fonte_legivel(pdf):
    """PDF com o texto que o pdftotext consegue ler. Fontes sem mapa Unicode completo (Enem 2021)
    são reparadas numa cópia em cache, fora do cofre; o original não muda."""
    from reparo_texto import reparar, precisa_reparo
    if not precisa_reparo(pdf):
        return pdf, {'reparo': False}
    cache = Path(os.environ.get('PU_CACHE_EXTRACAO', Path(tempfile.gettempdir()) / 'pu-extracao')) / hashlib.sha256(pdf.read_bytes()).hexdigest()[:20]
    return reparar(pdf, cache)


def recortar(pdf, ano, pasta_img, selecionadas=None):
    pdf, reparo = fonte_legivel(pdf)
    paginas = ler_paginas(pdf)
    for pg in paginas:
        preparar_pagina(pg)

    # Percorre as colunas em ordem de leitura, separando em trechos
    questoes, textos, aberta, espanhol = [], [], None, False
    for ip, pg in enumerate(paginas):
        for (cx0, cx1) in pg["colunas"]:
            linhas = sorted([l for l in pg["corpo"] if l[0] >= cx0 - 6 and l[0] < cx1], key=lambda l: (l[1], l[0]))
            cortes = []  # (y, tipo, número)
            for l in linhas:
                m = MARCADOR.match(l[4])
                if m:
                    cortes.append((l[1], "q", int(m.group(1))))
                elif t := TEXTO_COMUM.match(l[4]):
                    cortes.append((l[1], "texto", (int(t.group(1)), int(t.group(2)))))
                elif FIM.match(l[4]):
                    cortes.append((l[1], "fim", l[4]))
            ini, folga = pg["topo"] + 2, 0
            for (y, tipo, valor) in cortes + [(pg["base"], "base", None)]:
                if aberta is not None and y > ini + 3:
                    trecho = [l for l in linhas if ini - 1 <= l[1] < y - 1]
                    if trecho and not (aberta.get("continua") and alternativas_completas(aberta["linhas"])):
                        aberta["trechos"].append((ip, cx0, ini - folga, cx1, y - 3))
                        aberta["linhas"] += trecho
                if tipo == "q":
                    if not espanhol or valor > 5:
                        espanhol = False
                    aberta = {"n": valor, "es": espanhol, "trechos": [], "linhas": [], "continua": False}
                    questoes.append(aberta)
                elif tipo == "texto":
                    aberta = {"faixa": valor, "trechos": [], "linhas": [], "continua": False}
                    textos.append(aberta)
                elif tipo == "fim":
                    aberta = None
                    if "espanhol" in valor.lower():
                        espanhol = True
                ini, folga = y, 4
            if aberta is not None:
                aberta["continua"] = True

    # O mesmo mecanismo atende a importação e a correção de notas existentes.
    import fitz
    from midias import extrair, alternativas_visuais, VERSAO
    from reparo_texto import SUBSTITUTO
    pasta_img.mkdir(parents=True, exist_ok=True)
    documento = fitz.open(pdf)
    # pdftotext usa MediaBox; alinhar o renderizador evita perder figuras por CropBox.
    for pagina in documento:
        pagina.set_cropbox(pagina.mediabox)
    resultado = []
    try:
        for q in questoes:
            if q["es"] or (selecionadas is not None and q["n"] not in selecionadas):
                continue
            nome = f"{ano}-Q{q['n']:02d}"
            texto, imagens, evidencias = extrair(documento, q["trechos"], paginas, pasta_img, nome + "-midia")
            comum, grupo = "", ""
            for t in textos:
                a, b = t["faixa"]
                if a <= q["n"] <= b:
                    comum, imgs, evs = extrair(documento, t["trechos"], paginas, pasta_img, f"{ano}-Q{a:02d}a{b:02d}-midia")
                    imagens = imgs + imagens
                    evidencias = evs + evidencias
                    grupo = f"{pdf.stem}:Q{a:02d}a{b:02d}"
            marcas = re.findall(r"^([A-E])(?:\s|$)", texto, re.M)
            completa = marcas[-5:] == list("ABCDE")
            falha = ''
            if not completa or re.search(r'^[A-E][ \t]*$',texto,re.M):
                try:
                    texto, imgs, evs = alternativas_visuais(documento, q['trechos'], paginas, pasta_img, nome+'-midia')
                    imagens = list(dict.fromkeys(re.findall(r'!\[\[([^]]+)\]\]', comum))) + imgs
                    evidencias = [e for e in evidencias if e['arquivo'] in imagens] + evs
                    completa = True
                except ValueError as erro:
                    # Uma questão difícil não derruba a prova: fica fora do ar, marcada para revisão.
                    completa, falha = False, str(erro)
            if SUBSTITUTO in texto or SUBSTITUTO in comum:
                falha = (falha + '; ' if falha else '') + 'caractere sem mapa Unicode depois do reparo'
            resultado.append({"n": q["n"], "nome": nome, "imagens": imagens, "texto": texto,
                              "completa": completa, "texto_comum": comum, "grupo": grupo,
                              "midias": evidencias, "extrator": VERSAO, "falha": falha,
                              "reparo_texto": reparo.get('reparo', False)})
    finally:
        documento.close()
    return resultado


def aparar(img, margem=12):
    fundo = Image.new("RGB", img.size, (255, 255, 255))
    dif = ImageChops.difference(img, fundo).convert("L").point(lambda v: 255 if v > 30 else 0)
    caixa = dif.getbbox()
    if not caixa:
        return img
    x0, y0, x1, y1 = caixa
    img = img.crop((max(0, x0 - margem), max(0, y0 - margem), min(img.width, x1 + margem), min(img.height, y1 + margem)))
    return img


# ---------- taxonomia das matérias ----------

def limpar(nome):
    nome = nome.replace("~~", "").replace("≈", "").strip()
    nome = re.sub(r"\s*\((\d+|–|-)\)\s*$", "", nome)
    nome = re.sub(r"\s*\([A-Z]=\d+[^)]*\)\s*$", "", nome)
    return nome.replace("/", "-").strip()


def taxonomia(materia):
    texto = (MATERIAS / f"{materia}.md").read_text(encoding="utf-8")
    texto = texto.split("# Conteúdos", 1)[-1]
    itens, topico, assunto, cod_assunto, k = [], None, None, None, 0
    for linha in texto.splitlines():
        if m := re.match(r"^## \d+\.\s*(.+)", linha):
            topico = limpar(m.group(1))
        elif m := re.match(r"^### (\d+\.\d+)\s*(.+)", linha):
            cod_assunto, assunto, k = m.group(1), limpar(m.group(2)), 0
        elif linha.startswith("#"):
            # Outra seção (como a lista de flashcards): acabou a lista de conteúdos
            topico = assunto = None
        elif linha.startswith("- ") and assunto:
            nome = linha[2:].replace("~~", "").split("\t")[0]
            k += 1
            itens.append({"codigo": f"{CODIGOS[materia]}-{cod_assunto}-{k}", "materia": materia,
                          "topico": topico, "assunto": assunto, "conteudo": limpar(nome)})
    return itens


def todas_taxonomias():
    return {i["codigo"]: i for m in CODIGOS for i in taxonomia(m)}


# ---------- etapas ----------

def trabalho_de(pdf):
    return ENTRADA / ".trabalho" / pdf.stem


def cmd_preparar(pdf):
    ano, dia, caderno = identificar(pdf)
    respostas, gb = gabarito(pdf)
    pasta_img = IMAGENS
    questoes = recortar(pdf, ano, pasta_img)
    esperado = list(range(1, 91)) if dia == 1 else list(range(91, 181))
    numeros = [q["n"] for q in questoes]
    problemas = []
    if numeros != esperado:
        faltam = sorted(set(esperado) - set(numeros))
        repetidas = sorted({n for n in numeros if numeros.count(n) > 1})
        problemas.append(f"numeração diferente do esperado: faltam {faltam}, repetidas {repetidas}")
    for q in questoes:
        q["area"] = area_da_questao(ano, q["n"])
        q["lingua"] = lingua_estrangeira(ano, q["n"])
        q["gabarito"] = respostas.get(q["n"])
        if not q["gabarito"]:
            problemas.append(f"Q{q['n']} sem gabarito")
        if not q["completa"]:
            problemas.append(f"Q{q['n']} sem as alternativas A–E no texto (confira a imagem)")
        if q.get("falha"):
            problemas.append(f"Q{q['n']}: {q['falha']}")
    pasta = trabalho_de(pdf)
    pasta.mkdir(parents=True, exist_ok=True)
    info = {"prova": str(pdf), "gabarito": str(gb), "ano": ano, "dia": dia, "caderno": caderno,
            "questoes": questoes, "problemas": problemas}
    (pasta / "trabalho.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    escrever_resumo(pasta, questoes)
    print(f"{len(questoes)} questões recortadas de {pdf.name} ({ano}, {dia}º dia, caderno {caderno})")
    print(f"Imagens em: {pasta_img}")
    print(f"Para classificar: {pasta / 'para_classificar.txt'}")
    print(f"Classificação esperada em: {pasta / 'classificacao.txt'}")
    print("Problemas:" if problemas else "Sem problemas.")
    for p in problemas:
        print(" -", p)


def escrever_resumo(pasta, questoes):
    """Resumo curto de cada questão (início do texto e o comando), sem as fontes, para a classificação."""
    with open(pasta / "para_classificar.txt", "w", encoding="utf-8") as f:
        for q in questoes:
            if q["gabarito"] == "Anulada":
                continue
            linhas = [l for l in q["texto"].splitlines() if not re.search(r"Disponível em|Acesso em|\(adaptado\)", l)]
            # Corta nas alternativas: a última linha "A ..." que vem antes de uma "B ..."
            inicio_alt = len(linhas)
            for i in range(len(linhas) - 1, -1, -1):
                if re.match(r"^A(\s|$)", linhas[i]) and any(re.match(r"^B(\s|$)", x) for x in linhas[i + 1:]):
                    inicio_alt = i
                    break
            corpo = re.sub(r"\s+", " ", " ".join(linhas[:inicio_alt]))
            resumo = corpo if len(corpo) <= 450 else corpo[:150] + " […] " + corpo[-300:]
            f.write(f"Q{q['n']} [{q['area']}{' língua' if q['lingua'] else ''}] {resumo}\n")


def cmd_taxonomia(area):
    for m in AREAS[area][1]:
        for i in taxonomia(m):
            print(f"{i['codigo']}\t{i['topico']} › {i['assunto']} › {i['conteudo']}")


def arquivo_da_carta(item):
    return FLASHCARDS / item["materia"] / item["topico"] / item["assunto"] / f"{item['conteudo']}.md"


def link_da_carta(item):
    # Caminho completo: há conteúdos com o mesmo nome em matérias diferentes (Gases, Circunferência)
    caminho = arquivo_da_carta(item).relative_to(COFRE).with_suffix("")
    return f"[[{caminho}|{item['conteudo']}]]"


def gravar_carta(item, nome, linha_nova):
    """Cria, atualiza ou move a carta da questão. O histórico do plugin (linha <!--SR:...-->) vai junto."""
    alvo = arquivo_da_carta(item)
    chave = f"![[{nome}-1.png]]"
    historico, movida = None, False
    for f in FLASHCARDS.rglob("*.md"):
        linhas = f.read_text(encoding="utf-8").split("\n")
        for i, l in enumerate(linhas):
            if (chave in l or f"[[Provas Enem/Questões/{nome[:4]}/{nome}|" in l) and "::" in l:
                if f == alvo:
                    if l == linha_nova:
                        return "igual"
                    linhas[i] = linha_nova
                    f.write_text("\n".join(linhas), encoding="utf-8")
                    return "atualizada"
                fim = i + 2 if i + 1 < len(linhas) and linhas[i + 1].startswith("<!--SR:") else i + 1
                historico = linhas[i + 1] if fim == i + 2 else None
                del linhas[i:fim]
                f.write_text("\n".join(linhas), encoding="utf-8")
                movida = True
                break
        if movida:
            break
    alvo.parent.mkdir(parents=True, exist_ok=True)
    if not alvo.exists():
        tag = "#" + item["materia"].split("- ", 1)[1].replace(" ", "-")
        alvo.write_text(f'---\ntags:\n  - "{tag}"\n---\n', encoding="utf-8")
    atual = alvo.read_text(encoding="utf-8").rstrip("\n")
    alvo.write_text(f"{atual}\n\n{linha_nova}\n" + (f"{historico}\n" if historico else ""), encoding="utf-8")
    return "movida" if movida else "nova"


def ler_classificacao(pasta):
    """Lê classificacao.txt, uma linha por questão: `Q12 POR-4.1-1`, com `?` para revisar e `# observação`."""
    classif = {}
    for linha in (pasta / "classificacao.txt").read_text(encoding="utf-8").splitlines():
        linha, _, obs = linha.partition("#")
        partes = linha.split()
        if not partes:
            continue
        codigo = next((p for p in partes[1:] if p != "?"), None)
        classif[partes[0]] = {"codigo": codigo, "revisar": "?" in partes[1:], "obs": obs.strip()}
    return classif


def cmd_gravar(pdf):
    pasta = trabalho_de(pdf)
    info = json.loads((pasta / "trabalho.json").read_text(encoding="utf-8"))
    if any(q.get("extrator") != 2 for q in info["questoes"]):
        raise ValueError("Reprepare a prova com o extrator atual antes de gravar")
    # Extração incompleta, caractere sem mapa ou gabarito em dúvida: a nota é gravada com `fora_do_ar: true`
    # e o motivo, e a sincronização a deixa fora do catálogo. Nada entra no ar com dúvida.
    fora = {q["n"]: (q.get("falha") or "alternativas incompletas") for q in info["questoes"]
            if not q.get("completa") or q.get("falha")}
    classif = ler_classificacao(pasta)
    tax = todas_taxonomias()
    ano, dia, caderno = info["ano"], info["dia"], info["caderno"]
    pasta_notas = QUESTOES / str(ano)
    contagem, revisar, sem_carta = {}, [], []
    assinatura = hashlib.sha256(Path(info["prova"]).read_bytes()).hexdigest()
    for q in info["questoes"]:
        c = classif.get(f"Q{q['n']}", {})
        item = tax.get(c.get("codigo"))
        anulada = q["gabarito"] == "Anulada"
        if c.get("revisar") or (not item and not anulada):
            revisar.append(q["nome"])
        if c.get("codigo") and not item:
            print(f"Aviso: código desconhecido {c.get('codigo')} em Q{q['n']}")
        motivo_fora = fora.get(q["n"]) or ("" if anulada or q["gabarito"] in list("ABCDE") else "gabarito ausente ou incerto")
        # Nota da questão
        materia = item["materia"].split("- ", 1)[1] if item else ""
        fm = [
            "---",
            f"ano: {ano}", f"dia: {dia}", f"caderno: {caderno} ({CORES.get(caderno, '')})",
            f"questão: {q['n']}", f"área: {AREAS[q['area']][0]}",
            f"matéria: {materia}",
            f"tópico: {json.dumps(item['topico'], ensure_ascii=False) if item else ''}",
            f"assunto: {json.dumps(item['assunto'], ensure_ascii=False) if item else ''}",
            f"conteúdo: {json.dumps(item['conteudo'], ensure_ascii=False) if item else ''}",
            f"código: {c.get('codigo', '')}",
            f"gabarito: {q['gabarito'] or ''}", f"anulada: {str(anulada).lower()}",
            f"revisar: {str(q['nome'] in revisar or bool(motivo_fora)).lower()}",
            f"fora_do_ar: {str(bool(motivo_fora)).lower()}",
            "autores:", "  - Dominique-Oliveira-ChatGPT🤖💚", "  - Dominique-Oliveira-Claude🤖🧡",
            f"origem_arquivo: {json.dumps(Path(info['prova']).name)}", f"origem_sha256: {assinatura}",
            "extrator: 2", "tags:", "  - enem", f"  - enem-{ano}",
            "---",
        ]
        corpo = [f"# Enem {ano} · Questão {q['n']:02d}", "",
                 f"**Gabarito:** {q['gabarito'] or '—'}"]
        if item:
            corpo.append(f"**Carta em:** {link_da_carta(item)}")
        if c.get("obs"):
            corpo.append(f"**Observação:** {c['obs']}")
        if motivo_fora:
            corpo.append(f"**Fora do ar até revisão:** {motivo_fora}")
        if q.get("grupo"):
            fm.insert(fm.index("tags:"), "grupo: " + json.dumps(q["grupo"]))
            corpo += ["", "## Texto comum", "", q["texto_comum"]]
        corpo += ["", "## Texto", "", q["texto"]]
        (pasta_notas / f"{q['nome']}.md").write_text("\n".join(fm + corpo) + "\n", encoding="utf-8")
        # Carta
        if anulada or not item or motivo_fora:
            if not anulada:
                sem_carta.append(q["nome"])
            continue
        frente = frente_da_carta(q["nome"], q.get("texto_comum", ""), q["texto"])
        situacao = gravar_carta(item, q["nome"], f"{frente} :: {q['gabarito']}")
        contagem[situacao] = contagem.get(situacao, 0) + 1
    # A prova sai da Entrada e vai para a pasta das provas
    for chave in ("prova", "gabarito"):
        p = Path(info[chave])
        if p.parent == ENTRADA:
            shutil.move(str(p), PROVAS / p.name)
    print(f"Notas gravadas em {pasta_notas}: {len(info['questoes'])}")
    print("Cartas: " + " · ".join(f"{k}: {v}" for k, v in sorted(contagem.items())) + f" · sem carta: {len(sem_carta)} {sem_carta}")
    print(f"Para revisar ({len(revisar)}): {', '.join(revisar)}")


def frente_da_carta(nome, comum, texto):
    frente = re.sub(r'\s+', ' ', (comum + ' ' + texto)).strip().replace('::', ': :')
    return f"[[Provas Enem/Questões/{nome[:4]}/{nome}|{nome}]] · {frente}"


def aplicar_correcao(saida):
    """Aplica somente relatórios completos, com conferência de origem e reversão."""
    from midias import VERSAO
    relatorios = sorted(saida.glob('*-relatorio.json'))
    if not relatorios: raise ValueError('Nenhum relatório de correção')
    alteracoes = {}
    midias = {}
    cartas = {}
    for relatorio in relatorios:
        r = json.loads(relatorio.read_text())
        if r.get('formato') != VERSAO or r['problemas']:
            raise ValueError('Resolva as pendências antes de aplicar: ' + relatorio.name)
        fonte = Path(r['origem'])
        if not fonte.resolve().is_relative_to(PROVAS.resolve()) or hashlib.sha256(fonte.read_bytes()).hexdigest() != r['sha256']:
            raise ValueError('Fonte mudou ou está fora da pasta de provas')
        for q in r['questoes']:
            if q['n'] in r.get('preservadas', []): continue
            if q['n'] not in r['aprovadas']: raise ValueError('Questão não aprovada no relatório')
            nome = q['nome'] + '.md'
            alvo = QUESTOES / str(r['ano'] if 'ano' in r else identificar(fonte)[0]) / nome
            if hashlib.sha256(alvo.read_bytes()).hexdigest() != r['originais'][nome]:
                raise ValueError('Nota alterada depois da preparação: ' + nome)
            nova = saida / alvo.relative_to(COFRE)
            if not nova.is_file(): raise ValueError('Nota corrigida ausente')
            alteracoes[alvo] = nova.read_bytes()
            cartas[q['nome']] = (frente_da_carta(q['nome'],q.get('texto_comum',''),q['texto']), q['imagens'])
            for nome_midia in q['imagens']:
                if not re.fullmatch(r'[A-Za-z0-9_-]+\.png',nome_midia): raise ValueError('Mídia inválida')
                f = saida / IMAGENS.relative_to(COFRE) / nome_midia
                dados=f.read_bytes()
                if not dados.startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError('PNG inválido')
                midias[IMAGENS/nome_midia]=dados
    # Atualiza as cartas no lugar; mantém linhas de revisão e classificações existentes.
    for f in FLASHCARDS.rglob('*.md'):
        linhas=f.read_text().splitlines(keepends=True);mudou=False
        for i,linha in enumerate(linhas):
            if '::' not in linha: continue
            for nome,(frente,_) in cartas.items():
                if f'![[{nome}-1.png]]' in linha or f'[[Provas Enem/Questões/{nome[:4]}/{nome}|' in linha:
                    resposta=linha.rsplit(' :: ',1)[-1].rstrip('\n')
                    if ' :: ' not in linha: raise ValueError('Formato inesperado de carta em '+str(f))
                    linhas[i]=frente+' :: '+resposta+'\n';mudou=True;break
        if mudou: alteracoes[f]=''.join(linhas).encode()
    alteracoes={p:d for p,d in alteracoes.items() if p.read_bytes()!=d}
    copia=COFRE/'.backups'/('correcao-pu-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    copia.mkdir(parents=True)
    anteriores={p:p.read_bytes() for p in alteracoes}
    for p,dados in anteriores.items():
        b=copia/p.relative_to(COFRE);b.parent.mkdir(parents=True,exist_ok=True);b.write_bytes(dados)
    manifesto={'autor':'Dominique-Oliveira-ChatGPT🤖💚','arquivos':[str(p.relative_to(COFRE)) for p in alteracoes],
               'relatorios':[str(p) for p in relatorios], 'questoes':len(cartas)}
    (copia/'manifesto.json').write_text(json.dumps(manifesto,ensure_ascii=False,indent=2))
    novos=[]
    def atomico(p,dados):
        p.parent.mkdir(parents=True,exist_ok=True)
        fd,nome=tempfile.mkstemp(dir=p.parent,prefix='.correcao-')
        try:
            with os.fdopen(fd,'wb') as f: f.write(dados);f.flush();os.fsync(f.fileno())
            os.replace(nome,p)
        finally:
            if os.path.exists(nome): os.unlink(nome)
    try:
        for p,dados in midias.items():
            if p.exists():
                if p.read_bytes()!=dados: raise ValueError('Colisão de mídia: '+p.name)
            else: atomico(p,dados);novos.append(p)
        for p,dados in alteracoes.items(): atomico(p,dados)
    except Exception:
        for p,dados in anteriores.items(): atomico(p,dados)
        for p in novos:p.unlink()
        raise
    print(json.dumps({'questoes':len(cartas),'arquivos_atualizados':len(alteracoes),'copia':str(copia)},ensure_ascii=False))
    return copia


def cmd_corrigir(pdf, saida, selecionadas=None):
    """Reprocessa a fonte; prepara somente notas completas, sem tocar no cofre."""
    from midias import VERSAO
    ano, dia, caderno = identificar(pdf)
    saida = saida.resolve()
    if saida == COFRE.resolve() or saida.is_relative_to(COFRE.resolve()):
        raise ValueError("Use saída de preparação fora do cofre; aplicação é etapa separada")
    saida.mkdir(parents=True, exist_ok=True)
    pasta_img = saida / "Matérias/Flashcards/Imagens exercícios"
    questoes = recortar(pdf, ano, pasta_img, selecionadas)
    notas = saida / "Provas Enem/Questões" / str(ano)
    notas.mkdir(parents=True, exist_ok=True)
    problemas, aprovadas, originais, preservadas = [], [], {}, []
    esperadas = selecionadas if selecionadas is not None else set(range(1,91) if dia==1 else range(91,181))
    numeros=[q['n'] for q in questoes]
    for n in sorted(esperadas-set(numeros)):
        problemas.append({'questao':n,'motivo':'Questão não localizada na fonte'})
    if len(numeros)!=len(set(numeros)):
        raise ValueError('Questões repetidas na fonte; aplicação impedida')
    assinatura = hashlib.sha256(pdf.read_bytes()).hexdigest()
    for q in questoes:
        origem = QUESTOES / str(ano) / (q['nome'] + '.md')
        if not origem.exists():
            problemas.append({'questao':q['n'], 'motivo':'Nota original ausente; não inventar classificação/gabarito'})
            continue
        antiga = origem.read_text()
        originais[origem.name] = hashlib.sha256(origem.read_bytes()).hexdigest()
        # Nota já fora do ar (dúvida registrada na gravação): continua como está, sem travar o lote.
        if re.search(r'^fora_do_ar: true$', antiga.split('---', 2)[1], re.M) and (not q['completa'] or q.get('falha')):
            preservadas.append(q['n'])
            continue
        if not q['completa'] or q.get('falha'):
            problemas.append({'questao':q['n'], 'motivo':(q.get('falha') or 'Alternativas incompletas') + '; versão anterior preservada'})
            continue
        cabecalho, corpo = antiga.split('---', 2)[1:]
        if not re.search(rf'^dia: {dia}$',cabecalho,re.M) or not re.search(rf'^caderno: {caderno}\b',cabecalho,re.M):
            raise ValueError('A origem não corresponde à nota ' + origem.name)
        for campo in ('origem_arquivo','origem_sha256','extrator','grupo'):
            cabecalho = re.sub(r'^'+campo+r':.*\n', '', cabecalho, flags=re.M)
        if 'Dominique-Oliveira-ChatGPT🤖💚' not in cabecalho:
            if re.search(r'^autores:',cabecalho,re.M):
                cabecalho = re.sub(r'^autores:\s*\n', 'autores:\n  - Dominique-Oliveira-ChatGPT🤖💚\n',cabecalho,flags=re.M)
            else: cabecalho += 'autores:\n  - Dominique-Oliveira-ChatGPT🤖💚\n'
        cabecalho += f'origem_arquivo: {json.dumps(pdf.name)}\norigem_sha256: {assinatura}\nextrator: {VERSAO}\ngrupo: {json.dumps(q["grupo"])}\n'
        corpo = corpo.split('\n## Texto',1)[0]
        corpo = re.sub(r'!\[\[[^]]+\]\]', '', corpo).rstrip()
        corpo += ('\n\n## Texto comum\n\n' + q['texto_comum']) if q['texto_comum'] else ''
        corpo += '\n\n## Texto\n\n' + q['texto'] + '\n'
        (notas / origem.name).write_text('---' + cabecalho + '---' + corpo)
        aprovadas.append(q['n'])
    resultado={'formato':VERSAO, 'origem':str(pdf), 'sha256':assinatura, 'ano':ano,
               'gerado':datetime.now(timezone.utc).isoformat(), 'aprovadas':aprovadas, 'preservadas':preservadas,
               'problemas':problemas, 'questoes':questoes, 'originais':originais}
    (saida / (pdf.stem + '-relatorio.json')).write_text(json.dumps(resultado,ensure_ascii=False,indent=2))
    print(json.dumps({'origem':pdf.name,'aprovadas':len(aprovadas),'problemas':problemas},ensure_ascii=False))
    return resultado


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == 'aplicar':
        aplicar_correcao(Path(sys.argv[2]).resolve())
        sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == 'corrigir':
        parser = argparse.ArgumentParser(description='Corrige por reextração local, em pasta de preparação')
        parser.add_argument('etapa'); parser.add_argument('pdf', type=Path)
        parser.add_argument('--saida', type=Path, required=True)
        parser.add_argument('--questoes', help='Números separados por vírgula; omitir processa tudo')
        args=parser.parse_args()
        cmd_corrigir(args.pdf.resolve(), args.saida, set(map(int,args.questoes.split(','))) if args.questoes else None)
        sys.exit(0)

    if len(sys.argv) < 3:
        sys.exit(__doc__)
    etapa, alvo = sys.argv[1], sys.argv[2]
    if etapa == "taxonomia":
        cmd_taxonomia(alvo)
    else:
        pdf = Path(alvo).resolve()
        {"preparar": cmd_preparar, "gravar": cmd_gravar}[etapa](pdf)
