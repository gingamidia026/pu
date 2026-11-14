"""Envio indivisível de perguntas com texto comum. Dominique-Oliveira-ChatGPT🤖💚."""
import hashlib
import json
import re
import time
from acompanhamento import avancar_conjunto, ciclo, perfil, estudo

def membros(questao, questoes):
    if not questao.get('grupo'): return [questao]
    return sorted([q for q in questoes if q.get('grupo')==questao['grupo']],key=lambda q:q.get('numero',q['id']))

def responder(con, conta, questao, questoes, dados, ativas=None):
    """`questoes` é o catálogo inteiro (para achar o conjunto); `ativas`, as das provas ativas da conta."""
    ativas = questoes if ativas is None else ativas
    grupo=membros(questao,questoes)
    respostas=dados.get('respostas'); envio=dados.get('envio')
    if not isinstance(envio,str) or not re.fullmatch(r'[a-zA-Z0-9-]{20,80}',envio):
        raise ValueError('Identificador de envio inválido.')
    if not isinstance(respostas,list) or len(respostas)!=len(grupo):
        raise ValueError('Responda a todas as perguntas do conjunto.')
    mapa={}
    for item in respostas:
        if not isinstance(item,dict) or type(item.get('id')) is not int or type(item.get('alternativa')) is not int:
            raise ValueError('Resposta inválida.')
        if item['id'] in mapa: raise ValueError('Pergunta repetida no envio.')
        mapa[item['id']]=item['alternativa']
    if set(mapa)!={q['id'] for q in grupo}: raise ValueError('Perguntas não correspondem ao conjunto.')
    if any(not 0 <= mapa[q['id']] < len(q['alternativas']) for q in grupo):
        raise ValueError('Alternativa inválida.')
    assinatura=hashlib.sha256(json.dumps([questao['grupo'],sorted(mapa.items())]).encode()).hexdigest()
    con.execute('CREATE TABLE IF NOT EXISTS envios_conjuntos(conta INTEGER NOT NULL, envio TEXT NOT NULL, assinatura TEXT NOT NULL, resultado TEXT NOT NULL, PRIMARY KEY(conta,envio))')
    con.execute('BEGIN IMMEDIATE')
    anterior=con.execute('SELECT assinatura,resultado FROM envios_conjuntos WHERE conta=? AND envio=?',(conta,envio)).fetchone()
    if anterior:
        if anterior['assinatura']!=assinatura: raise ValueError('Este envio já foi usado para outras respostas.')
        return json.loads(anterior['resultado'])
    resultados=[]
    for q in grupo:
        acerto=mapa[q['id']]==q['correta']
        con.execute('INSERT INTO respostas(conta,questao,alternativa,acerto,criada,chute) VALUES(?,?,?,?,?,?)',
                    (conta,q['id'],mapa[q['id']],acerto,time.time(),int(dados.get('chute') is True)))
        resultados.append({'id':q['id'],'acerto':acerto,'correta':q['correta'],'explicacao':q['explicacao']})
    terminou=avancar_conjunto(con,conta,list(mapa),ativas,questoes)
    resultado={'resultados':resultados,'densidadeConcluida':terminou,
               'acompanhamento':{'densidade':ciclo(con,conta,ativas,questoes),'perfil':perfil(con,conta,ativas,todas=questoes)},
               'progresso':dict(con.execute('SELECT COUNT(*) total,COALESCE(SUM(acerto),0) acertos FROM respostas WHERE conta=?',(conta,)).fetchone()),
               'estudo':estudo(con,conta,ativas)}
    con.execute('INSERT INTO envios_conjuntos VALUES(?,?,?,?)',(conta,envio,assinatura,json.dumps(resultado)))
    con.commit()
    return resultado
