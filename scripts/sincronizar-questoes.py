#!/usr/bin/env python3
"""Exporta questões do cofre sem IA, rede, execução de Markdown ou acesso às contas."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

RAIZ = Path(__file__).resolve().parents[1]
PADRAO_COFRE = '/home/dominique/backup/Estudos/Vestibular'
# Uma pasta por prova no cofre. Só a do Enem é obrigatória; as outras entram quando existirem.
# Dominique-Oliveira-Claude🤖🧡, 14/11/2026: Fuvest (USP), Unesp, Unicamp e Famerp.
PROVAS = {
    'enem': {'nome': 'Enem', 'pasta': 'Provas Enem/Questões', 'letras': 'ABCDE', 'dias': (1, 2), 'maximo': 180, 'fonte': 'Inep'},
    'fuvest': {'nome': 'Fuvest', 'pasta': 'Provas Fuvest/Questões', 'letras': 'ABCDE', 'dias': (1,), 'maximo': 90, 'fonte': 'Fuvest'},
    'unesp': {'nome': 'Unesp', 'pasta': 'Provas Unesp/Questões', 'letras': 'ABCDE', 'dias': (1,), 'maximo': 90, 'fonte': 'Vunesp'},
    'unicamp': {'nome': 'Unicamp', 'pasta': 'Provas Unicamp/Questões', 'letras': 'ABCD', 'dias': (1,), 'maximo': 72, 'fonte': 'Comvest'},
    'famerp': {'nome': 'Famerp', 'pasta': 'Provas Famerp/Questões', 'letras': 'ABCDE', 'dias': (1,), 'maximo': 80, 'fonte': 'Vunesp'},
}
# Endereços oficiais aceitos no campo fonte_url das provas que não são do Enem.
HOSTS_OFICIAIS = ('https://www.fuvest.br/', 'https://www.comvest.unicamp.br/', 'https://documento.vunesp.com.br/')

def atomico(caminho, dados):
    fd, nome = tempfile.mkstemp(dir=caminho.parent, prefix='.temporario-')
    try:
        with os.fdopen(fd, 'wb') as f:
            os.fchmod(f.fileno(), 0o644)
            f.write(dados); f.flush(); os.fsync(f.fileno())
        os.replace(nome, caminho)
    finally:
        if os.path.exists(nome): os.unlink(nome)

def texto_meta(texto):
    if not texto.startswith('---\n'): raise ValueError('Cabeçalho YAML ausente')
    partes = texto.split('---', 2)
    if len(partes) < 3: raise ValueError('Cabeçalho incompleto')
    meta = {}
    for linha in partes[1].splitlines():
        achado = re.match(r'^([^\s:][^:]*):\s*(.*?)\s*$', linha)
        if achado:
            k,v = achado.groups()
            if v.startswith('"'):
                v = json.loads(v)
            elif v.startswith("'") and v.endswith("'"): v = v[1:-1].replace("''", "'")
            meta[k] = str(v)
    return meta, partes[2]

AREAS = ('Linguagens', 'Ciências Humanas', 'Ciências da Natureza', 'Matemática')

def sincronizar(cofre, destino):
    cofre = cofre.resolve()
    questoes = cofre / PROVAS['enem']['pasta']
    imagens = cofre / 'Matérias/Flashcards/Imagens exercícios'
    if not questoes.is_dir() or not (cofre/'Leia-me.md').is_file():
        raise ValueError('Cofre indisponível ou raiz incorreta. Catálogo anterior preservado.')
    destino.mkdir(parents=True, exist_ok=True)
    with (destino/'sincronizacao.lock').open('a') as trava:
        fcntl.flock(trava, fcntl.LOCK_EX)
        anterior = json.loads((destino/'atual.json').read_text()) if (destino/'atual.json').exists() else {}
        registro = dict(anterior.get('registro', {}))
        proximo = max([999, *registro.values()])+1
        itens=[]; chaves=set(); arquivos={}; anuladas=0; revisao=0; fora=0; por_prova={}
        notas=[]
        for sigla,info in PROVAS.items():
            pasta=cofre/info['pasta']
            if pasta.is_dir():
                notas+=[(sigla,pasta,n) for n in sorted(pasta.rglob('*.md'))]
        for prova,pasta,nota in notas:
            regra=PROVAS[prova]
            if nota.is_symlink() or not nota.resolve().is_relative_to(pasta.resolve()):
                raise ValueError(f'Questão fora da pasta autorizada: {nota.name}')
            if nota.stat().st_size > 200000: raise ValueError(f'Nota muito grande: {nota.name}')
            try:
                meta, corpo = texto_meta(nota.read_text())
                ano=int(meta['ano']);dia=int(meta['dia']);numero=int(meta['questão'])
                if meta.get('prova',prova)!=prova: raise ValueError('Prova da nota diferente da pasta')
                if prova=='enem':
                    caderno=re.match(r'^([0-9]+)(?:\s|$)',meta['caderno'])
                    caderno=int(caderno[1]) if caderno else None
                else:
                    caderno=meta.get('caderno','') if re.fullmatch(r'[A-Za-z0-9]{1,6}',meta.get('caderno','')) else None
                if caderno is None or not 2000 <= ano <= 2999 or dia not in regra['dias'] or not 1 <= numero <= regra['maximo']:
                    raise ValueError('Identificação inválida')
                # A chave do Enem não muda: os IDs já gravados nas respostas dependem dela.
                chave=f'{prova}:{ano}:{dia}:{caderno}:{numero}'
                if chave in chaves: raise ValueError('Identificação duplicada')
                chaves.add(chave)
                for campo in ('anulada','revisar','fora_do_ar'):
                    if meta.get(campo,'false') not in ('true','false'): raise ValueError(campo+' deve ser true ou false')
                if meta.get('anulada')=='true': anuladas+=1;continue
                # Dúvida de extração ou de gabarito: a nota fica no cofre, marcada, e não entra no ar.
                if meta.get('fora_do_ar')=='true': fora+=1;continue
                letras=regra['letras']
                gabarito=meta.get('gabarito','')
                if gabarito not in list(letras): raise ValueError('Gabarito ausente ou inválido')
                if prova=='enem':
                    fonte=f'https://download.inep.gov.br/enem/provas_e_gabaritos/{ano}_PV_impresso_D{dia}_CD{caderno}.pdf'
                else:
                    fonte=meta.get('fonte_url','')
                    if not fonte.startswith(HOSTS_OFICIAIS) or not re.fullmatch(r'https://[A-Za-z0-9._~:/?#@!$&()*+,;=%-]+',fonte):
                        raise ValueError('fonte_url ausente ou fora dos endereços oficiais')
                if '\n## Texto\n' not in corpo: raise ValueError('Seção Texto ausente')
                texto=corpo.split('\n## Texto\n',1)[1].strip()
                comum=corpo.split('\n## Texto comum\n',1)[1].split('\n## Texto\n',1)[0].strip() if '\n## Texto comum\n' in corpo else ''
                n=len(letras)
                marcas=list(re.finditer(r'^(['+letras+r'])(?:[ \t]+|(?=\n|$))',texto,re.M))[-n:]
                texto_parcial = [m[1] for m in marcas] != list(letras)
                if (meta.get('extrator') == '2' or prova!='enem') and texto_parcial:
                    raise ValueError('Questão corrigida sem alternativas completas')
                alternativas = [f'Alternativa {letra} (veja a imagem original)' for letra in letras] if texto_parcial else [texto[m.end():marcas[i+1].start() if i<n-1 else len(texto)].strip() for i,m in enumerate(marcas)]
                if not all(alternativas): raise ValueError('Alternativa vazia')
                enunciado=texto.strip() if texto_parcial else texto[:marcas[0].start()].strip()
                enunciado=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', enunciado)
                if not enunciado: raise ValueError('Enunciado vazio')
                refs=[]
                nomes=list(dict.fromkeys(re.findall(r'!\[\[([^]|]+)',corpo)))
                for imagem in nomes:
                    if not re.fullmatch(r'[A-Za-z0-9_-]+\.png',imagem): raise ValueError('Nome de imagem inválido')
                    f=imagens/imagem
                    if f.is_symlink() or not f.resolve().is_relative_to(imagens.resolve()) or not f.is_file(): raise ValueError('Imagem ausente ou fora da pasta autorizada')
                    dados=f.read_bytes()
                    if not dados.startswith(b'\x89PNG\r\n\x1a\n') or len(dados)>8*1024*1024: raise ValueError('PNG inválido ou acima de 8 MB')
                    sha=hashlib.sha256(dados).hexdigest();arquivos[sha]=dados
                    refs.append({'hash':sha,'tipo':'image/png','partes':(len(dados)+49151)//49152})
                def midias_embutidas(t):
                    return re.sub(r'!\[\[([^]|]+)(?:\|[^]]*)?\]\]',lambda m:'[[midia:'+str(nomes.index(m[1]))+']]',t)
                enunciado=midias_embutidas(enunciado)
                alternativas=[midias_embutidas(a) for a in alternativas]
                comum=midias_embutidas(comum)
                if texto_parcial and not refs: raise ValueError('Extração parcial sem imagem original')
                if chave not in registro:
                    if proximo > 999999: raise ValueError('Limite de identificadores atingido')
                    registro[chave]=proximo;proximo+=1
                revisar=meta.get('revisar')=='true';revisao+=int(revisar)
                if meta.get('área') not in AREAS: raise ValueError('Área fora das quatro do catálogo')
                por_prova[prova]=por_prova.get(prova,0)+1
                itens.append({'id':registro[chave],'chave':chave,'prova':prova,'edicao':f"{regra['nome']} {ano}",'fonteNome':regra['fonte'],
                    'area':meta['área'],'titulo':f"{regra['nome']} {ano} · Questão {numero:02d}",
                    'ano':ano,'dia':dia,'numero':numero,'caderno':caderno,'materia':meta.get('matéria',''),
                    'topico':meta.get('tópico',''),'assunto':meta.get('assunto',''),'conteudo':meta.get('conteúdo',''),
                    'revisar':revisar,'oficial':True,'enunciado':enunciado,'alternativas':alternativas,'correta':ord(gabarito)-65,
                    'explicacao':'Gabarito registrado no cofre a partir do caderno oficial. Ainda não há solução comentada para esta questão.',
                    'imagens':refs,'textoParcial':texto_parcial,'textoComum':comum,'grupo':meta.get('grupo',''),
                    'extrator':int(meta.get('extrator','1')),'origemArquivo':meta.get('origem_arquivo',''),
                    'fonte':fonte})
            except (KeyError, ValueError, TypeError, OSError) as e:
                raise ValueError(f'{nota.name}: {e}. Catálogo anterior preservado.') from e
        grupos={}
        for q in itens:
            if q['grupo']:
                if not q['textoComum']: raise ValueError('Grupo sem texto comum')
                grupos.setdefault(q['grupo'],[]).append(q)
        for grupo, membros in grupos.items():
            textos={q['textoComum'] for q in membros}
            if len(textos)!=1: raise ValueError('Texto compartilhado inconsistente: '+grupo)
            faixa=re.search(r':Q(\d+)a(\d+)$',grupo)
            if not faixa or not set(range(int(faixa[1]),int(faixa[2])+1)).issubset({q['numero'] for q in membros}):
                raise ValueError('Grupo incompleto: '+grupo)
            ids=[q['id'] for q in sorted(membros,key=lambda q:q['numero'])]
            for q in membros: q['grupoIds']=ids
        velho={q['chave'] for q in anterior.get('questoes',[])};novo={q['chave'] for q in itens}
        catalogo={'formato':1,'registro':registro,'questoes':itens,'anuladas':anuladas,'revisar':revisao,'foraDoAr':fora,
                  'provas':[{'id':s,'nome':PROVAS[s]['nome'],'questoes':por_prova[s],
                             'edicoes':sorted({q['ano'] for q in itens if q['prova']==s},reverse=True)} for s in PROVAS if s in por_prova]}
        assinatura=json.dumps(catalogo,ensure_ascii=False,sort_keys=True).encode();catalogo['versao']=hashlib.sha256(assinatura).hexdigest()
        # Imagens imutáveis e registro completo são publicados antes da troca atômica do índice.
        (destino/'imagens').mkdir(exist_ok=True)
        for sha,dados in arquivos.items():
            arquivo=destino/'imagens'/f'{sha}.png'
            if not arquivo.exists(): atomico(arquivo,dados)
            arquivo.chmod(0o644)
        atomico(destino/'atual.json',json.dumps(catalogo,ensure_ascii=False).encode())
        resumo={'total':len(itens),'adicionadas':len(novo-velho),'removidas':len(velho-novo),'anuladas':anuladas,'revisar':revisao,'foraDoAr':fora,'porProva':por_prova,'versao':catalogo['versao'][:12]}
        print('Questões sincronizadas, sem IA: '+json.dumps(resumo,ensure_ascii=False))
        return resumo

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cofre',type=Path,default=Path(os.environ.get('PU_COFRE_VESTIBULAR',PADRAO_COFRE)))
    parser.add_argument('--destino',type=Path,default=RAIZ/'.catalogo')
    args=parser.parse_args()
    try: sincronizar(args.cofre,args.destino)
    except (ValueError,OSError,json.JSONDecodeError) as erro:
        print('Não foi possível sincronizar: '+str(erro),file=sys.stderr);sys.exit(1)
