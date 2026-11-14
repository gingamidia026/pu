#!/usr/bin/env python3
"""Corrige com o separador local, por lotes, antes de sincronizar. Sem IA/rede."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

RAIZ=Path(__file__).resolve().parents[1]
FERRAMENTA=RAIZ/'ferramentas/importar-prova'
try:
    import fitz
except ImportError:
    interpretador=RAIZ/'.venv-extracao/bin/python'
    if not interpretador.exists():sys.exit('Ambiente local de extração não instalado; nenhuma correção aplicada.')
    os.execv(str(interpretador),[str(interpretador),str(Path(__file__).resolve()),*sys.argv[1:]])
sys.path.insert(0,str(FERRAMENTA))
import importar

def carregar_sync():
    spec=importlib.util.spec_from_file_location('sincronizar',RAIZ/'scripts/sincronizar-questoes.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod

def executar(aplicar=False, forcar=False):
    base=RAIZ/'.extracao';base.mkdir(exist_ok=True)
    with (base/'correcao.lock').open('a') as trava:
        fcntl.flock(trava,fcntl.LOCK_EX)
        return executar_lote(aplicar,forcar)

def executar_lote(aplicar=False, forcar=False):
    cofre=importar.COFRE.resolve()
    if not (cofre/'Leia-me.md').is_file():raise ValueError('Cofre indisponível')
    fontes=sorted((cofre/'Provas Enem').glob('*_PV_impresso_D*_CD*.pdf'))
    if not fontes:raise ValueError('Nenhuma prova local encontrada; catálogo anterior preservado')
    base=RAIZ/'.extracao';base.mkdir(exist_ok=True)
    estado=base/'estado.json'
    # Todos os módulos do extrator (reparo de texto e formatos das bancas entraram em 14/11/2026).
    versao=hashlib.sha256(b''.join(p.read_bytes() for p in sorted(FERRAMENTA.glob('*.py')))).hexdigest()
    assinaturas={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in fontes}
    esperado={'ferramenta':versao,'fontes':assinaturas}
    notas=list(importar.QUESTOES.rglob('*.md'))
    if not notas:
        print('Não há notas para corrigir; a sincronização poderá exportar o catálogo vazio.')
        return
    textos=[p.read_text() for p in notas]
    atual=bool(notas) and all('\nextrator: 2\n' in t for t in textos)
    anterior_estado=json.loads(estado.read_text()) if estado.exists() else {}
    if not forcar and anterior_estado==esperado and atual:
        print('Separador: fontes já corrigidas nesta versão; sem reprocessamento.')
        return
    # Pasta isolada; somente os relatórios aprovados podem ser aplicados.
    pasta=Path(tempfile.mkdtemp(prefix='lote-',dir=base))
    (pasta/'Leia-me.md').write_text('Preparação isolada para validar o catálogo do PU.')
    shutil.copytree(importar.QUESTOES,pasta/'Provas Enem/Questões')
    problemas=[]
    escolhidas=fontes
    if not forcar and anterior_estado.get('ferramenta')==versao and atual:
        escolhidas=[p for p in fontes if anterior_estado.get('fontes',{}).get(p.name)!=assinaturas[p.name]]
    for fonte in escolhidas:
        resultado=importar.cmd_corrigir(fonte,pasta)
        problemas.extend(resultado['problemas'])
    if problemas:raise ValueError('Lote não aprovado; nenhuma nota aplicada. Consulte '+str(pasta))
    # Mantém as mídias das fontes não alteradas na preparação, sem copiá-las de novo.
    import re
    for nota in (pasta/'Provas Enem/Questões').rglob('*.md'):
        for nome in re.findall(r'!\[\[([^]|]+)',nota.read_text()):
            if not re.fullmatch(r'[A-Za-z0-9_-]+\.png',nome):raise ValueError('Referência de mídia inválida')
            destino=pasta/'Matérias/Flashcards/Imagens exercícios'/nome
            if not destino.exists():
                origem=importar.IMAGENS/nome
                destino.parent.mkdir(parents=True,exist_ok=True)
                try:os.link(origem,destino)
                except OSError:shutil.copy2(origem,destino)
    catalogo=pasta/'catalogo';catalogo.mkdir()
    anterior=RAIZ/'.catalogo/atual.json'
    if anterior.exists():shutil.copy2(anterior,catalogo/'atual.json')
    # Valida todas as referências, alternativas e conjuntos antes de tocar no cofre.
    carregar_sync().sincronizar(pasta,catalogo)
    if aplicar:
        importar.aplicar_correcao(pasta)
        carregar_sync().sincronizar(cofre,RAIZ/'.catalogo')
        temporario=estado.with_suffix('.tmp');temporario.write_text(json.dumps(esperado));os.replace(temporario,estado)
        print('Correção aplicada; IDs e histórico preservados. Relatório: '+str(pasta))
    else:
        print('Preparação validada, sem alterar o cofre. Pasta: '+str(pasta))
    return pasta

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aplicar',action='store_true')
    parser.add_argument('--forcar',action='store_true')
    args=parser.parse_args()
    try:executar(args.aplicar,args.forcar)
    except (ValueError,OSError,KeyError) as e:sys.exit(str(e))
