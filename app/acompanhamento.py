"""Ciclos, perfil, revisão espaçada e ritmo de estudo calculados exclusivamente no servidor.
Dominique-Oliveira-ChatGPT🤖💚; ordem intercalada, revisão e ritmo por Dominique-Oliveira-Claude🤖🧡 em 12/11/2026."""
import json
import time
import hashlib
from collections import defaultdict
from datetime import datetime, timezone, timedelta

def preparar(con):
    con.executescript('''
    CREATE TABLE IF NOT EXISTS ciclos(conta INTEGER PRIMARY KEY REFERENCES contas(id), concluidos INTEGER NOT NULL DEFAULT 0, ids TEXT NOT NULL, feitos TEXT NOT NULL DEFAULT '[]');
    CREATE TABLE IF NOT EXISTS envios(conta INTEGER REFERENCES contas(id), chave TEXT NOT NULL, questao INTEGER NOT NULL, alternativa INTEGER NOT NULL, resultado TEXT NOT NULL, PRIMARY KEY(conta,chave));
    CREATE TABLE IF NOT EXISTS medias(semana TEXT PRIMARY KEY, dados TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS respostas_conta ON respostas(conta);
    ''')
    # "Chutei": acerto sem certeza continua na revisão. Coluna criada sem apagar o histórico.
    if 'chute' not in [r[1] for r in con.execute('PRAGMA table_info(respostas)')]:
        con.execute('ALTER TABLE respostas ADD COLUMN chute INTEGER NOT NULL DEFAULT 0')

def materia(q):
    return q.get('materia') or q['area']

def assunto(q):
    return q.get('topico') or q.get('assunto') or 'Geral'

FUSO = timezone(timedelta(hours=-3))  # Horário de Brasília, sem horário de verão desde 2019.
INTERVALOS = [1, 3, 7]  # Dias até a próxima revisão, conforme os acertos seguros seguidos.
LIMITE_CURTA = 900  # Caracteres de enunciado e alternativas de uma questão de aquecimento.

def rodizio(filas, primeiro=None):
    """Junta várias filas alternando entre elas na proporção do tamanho de cada uma, sem blocos."""
    nomes = sorted(filas, key=lambda n: (n != primeiro, n))
    total = sum(len(f) for f in filas.values())
    saldo = {n: 0 for n in nomes}
    usados = {n: 0 for n in nomes}
    if primeiro in saldo:
        saldo[primeiro] = total  # garante a primeira posição; a proporção se acerta nas rodadas seguintes
    ordem = []
    while len(ordem) < total:
        ativos = [n for n in nomes if usados[n] < len(filas[n])]
        for n in ativos:
            saldo[n] += len(filas[n])
        escolhida = max(ativos, key=lambda n: (saldo[n], -nomes.index(n)))
        saldo[escolhida] -= total
        ordem.append(filas[escolhida][usados[escolhida]])
        usados[escolhida] += 1
    return ordem

def ordem_intercalada(questoes):
    """Rodízio proporcional em dois níveis: entre as matérias, começando em Português, e entre os assuntos de cada matéria."""
    materias = defaultdict(lambda: defaultdict(list))
    for q in sorted(questoes, key=lambda q: q['id']):
        materias[materia(q)][assunto(q)].append(q['id'])
    return rodizio({m: rodizio(dict(assuntos)) for m, assuntos in materias.items()}, 'Português')

_ORDENS = {}

def ordem_em_cache(questoes):
    """A ordem intercalada só muda com o conjunto de questões; com o catálogo grande, recalcular a cada pedido pesa."""
    chave = (len(questoes), hash(tuple(q['id'] for q in questoes)))
    if chave not in _ORDENS:
        if len(_ORDENS) > 64: _ORDENS.clear()
        _ORDENS[chave] = ordem_intercalada(questoes)
    return _ORDENS[chave]

def ciclo(con, conta, questoes, todas=None):
    """Volta pelo banco. `questoes` são as das provas ativas da conta; `todas`, o catálogo inteiro.
    Questão nova no catálogo (ou de prova reativada) entra na volta em andamento; a de prova desativada
    continua registrada, mas fica fora da conta e da fila até a prova voltar."""
    todas = questoes if todas is None else todas
    ordem = ordem_em_cache(questoes)
    con.execute('INSERT OR IGNORE INTO ciclos(conta,ids) VALUES(?,?)',(conta,json.dumps(ordem)))
    r=con.execute('SELECT * FROM ciclos WHERE conta=?',(conta,)).fetchone()
    previstos=json.loads(r['ids']); feitos=set(json.loads(r['feitos'])); mapa={q['id']:q for q in questoes}
    registrados=set(previstos)
    novos=[i for i in ordem if i not in registrados]
    if novos:
        previstos+=novos
        con.execute('UPDATE ciclos SET ids=? WHERE conta=?',(json.dumps(previstos),conta))
    existentes={q['id'] for q in todas}
    posicao={i:n for n,i in enumerate(ordem)}
    pendentes=[i for i in previstos if i not in feitos and (i in mapa or i not in existentes)]
    # A ordem de estudo é a intercalada atual; o registro guarda quais questões pertencem à densidade.
    disponiveis=sorted((i for i in pendentes if i in mapa),key=lambda i:posicao[i])
    removidas=len(pendentes)-len(disponiveis)
    grupos=defaultdict(lambda: {'total':0,'feitas':0})
    contados=[i for i in previstos if i in mapa or i not in existentes]
    for i in contados:
        nome=materia(mapa[i]) if i in mapa else 'Questão removida do catálogo'
        grupos[nome]['total']+=1; grupos[nome]['feitas']+=int(i in feitos)
    return {'concluidas':r['concluidos'],'feitas':sum(1 for i in contados if i in feitos),'total':len(contados),'proxima':disponiveis[0] if disponiveis else None,
            'bloqueada':bool(removidas and not disponiveis),'removidas':removidas,'pendentes':disponiveis,
            'materias':[dict(materia=m,**v) for m,v in grupos.items()],
            'base':'Distribuição das questões das provas ativas no catálogo; classificações em revisão. Não é uma média histórica validada de nenhuma prova.'}

def avancar(con, conta, questao, questoes, todas=None):
    return avancar_conjunto(con, conta, [questao], questoes, todas)

def avancar_conjunto(con, conta, ids, questoes, todas=None):
    """Conta qualquer questão pendente da densidade, em qualquer ordem. Repetição não conta duas vezes.
    A volta termina quando todas as questões das provas ativas foram feitas."""
    ciclo(con,conta,questoes,todas)
    r=con.execute('SELECT * FROM ciclos WHERE conta=?',(conta,)).fetchone()
    previstos=json.loads(r['ids']); feitos=set(json.loads(r['feitos']))
    novos=[i for i in ids if i in previstos and i not in feitos]
    if not novos: return False
    feitos.update(novos)
    # Questão removida do catálogo segura a volta (fica "bloqueada"); a de prova desativada, não.
    ativas={q['id'] for q in questoes}; existentes={q['id'] for q in (questoes if todas is None else todas)}
    contados=[i for i in previstos if i in ativas or i not in existentes]
    terminou=bool(contados) and all(i in feitos for i in contados)
    con.execute('UPDATE ciclos SET feitos=?,concluidos=concluidos+? WHERE conta=?',
                (json.dumps([] if terminou else sorted(feitos)),int(terminou),conta))
    if terminou:
        con.execute('UPDATE ciclos SET ids=? WHERE conta=?',(json.dumps(ordem_em_cache(questoes)),conta))
    return terminou

def indice(questoes):
    """Mapa fixo do catálogo para a interface montar foco por matéria e assunto. Sem enunciado nem gabarito."""
    materias={}
    for q in sorted(questoes,key=lambda q:(materia(q)!='Português',materia(q),assunto(q),q['id'])):
        m=materias.setdefault(materia(q),{'nome':materia(q),'area':q['area'],'topicos':{}})
        m['topicos'].setdefault(assunto(q),[]).append(q['id'])
    curtas=[q['id'] for q in questoes if not q.get('imagens') and not q.get('grupo') and not q.get('textoParcial')
            and len(q.get('enunciado',''))+sum(len(a) for a in q.get('alternativas',[]))<=LIMITE_CURTA]
    return {'materias':[{'nome':m['nome'],'area':m['area'],'topicos':[{'nome':t,'ids':ids} for t,ids in m['topicos'].items()]} for m in materias.values()],
            'curtas':curtas,'conjuntos':[q['id'] for q in questoes if q.get('grupo')]}

def estudo(con, conta, questoes, agora=None):
    """Dia, semana e revisão espaçada, calculados só com o histórico de respostas da própria conta."""
    hoje=(agora or datetime.now(FUSO)).astimezone(FUSO).date()
    mapa={q['id'] for q in questoes}
    historico=defaultdict(list); dias=defaultdict(lambda:[0,0])
    for r in con.execute('SELECT questao,acerto,chute,criada FROM respostas WHERE conta=? ORDER BY criada,rowid',(conta,)):
        dia=datetime.fromtimestamp(r['criada'],FUSO).date()
        dias[dia][0]+=1; dias[dia][1]+=int(r['acerto'])
        historico[r['questao']].append((bool(r['acerto']) and not r['chute'],dia))
    vencidas=[]; caderno=0
    for questao,tentativas in historico.items():
        if questao not in mapa: continue
        # nivel None: nunca errou nem chutou. Depois do primeiro tropeço, só sobe de nível o acerto seguro
        # feito no dia do vencimento ou depois; acerto adiantado (acabou de ver o gabarito) não conta nem atrasa.
        nivel=None; marco=None
        for seguro,dia in tentativas:
            if not seguro: nivel=0; marco=dia
            elif nivel is not None and nivel<len(INTERVALOS) and (dia-marco).days>=INTERVALOS[nivel]: nivel+=1; marco=dia
        if nivel is None or nivel>=len(INTERVALOS): continue
        caderno+=1
        if (hoje-marco).days>=INTERVALOS[nivel]: vencidas.append((marco.isoformat(),questao))
    segunda=hoje-timedelta(days=hoje.weekday())
    semana=[dias[segunda+timedelta(days=n)][0] if segunda+timedelta(days=n) in dias else 0 for n in range(7)]
    feitas_hoje=dias[hoje] if hoje in dias else [0,0]
    return {'data':hoje.isoformat(),'hoje':{'respostas':feitas_hoje[0],'acertos':feitas_hoje[1]},'semana':semana,'diaDaSemana':hoje.weekday(),
            'revisao':{'vencidas':[q for _,q in sorted(vencidas)],'caderno':caderno,'intervalos':INTERVALOS}}

def perfil(con,conta,questoes,agora=None,todas=None):
    """Desempenho da conta nas provas ativas. A média semanal dos usuários usa o catálogo inteiro,
    porque fica em cache para todas as contas."""
    agora=agora or datetime.now(timezone.utc)
    inicio=(agora-timedelta(days=agora.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
    semana=inicio.isoformat(); mapa={q['id']:q for q in (questoes if todas is None else todas)}
    cache=con.execute('SELECT dados FROM medias WHERE semana=?',(semana,)).fetchone()
    if cache: medias=json.loads(cache[0])
    else:
        # Média de percentuais individuais, com todos os usuários reais com respostas.
        por_usuario=defaultdict(lambda:[0,0])
        for r in con.execute("SELECT r.conta,r.questao,r.acerto FROM respostas r JOIN contas c ON c.id=r.conta WHERE r.criada<? AND c.email!='teste'",(inicio.timestamp(),)):
            if r['questao'] not in mapa: continue
            q=mapa[r['questao']]
            for chave in [(materia(q),assunto(q)),('*','*')]:
                v=por_usuario[(r['conta'],*chave)];v[0]+=1;v[1]+=r['acerto']
        totais=defaultdict(list)
        for (_,m,a),(n,s) in por_usuario.items(): totais[m+'\n'+a].append(100*s/n)
        medias={k:{'usuarios':len(v),'percentual':round(sum(v)/len(v),1) if len(v)>=5 else None} for k,v in totais.items()}
        con.execute('INSERT OR IGNORE INTO medias VALUES(?,?)',(semana,json.dumps(medias)))
    grupos=defaultdict(lambda:[0,0]); mapa={q['id']:q for q in questoes}
    for r in con.execute('SELECT questao,acerto FROM respostas WHERE conta=?',(conta,)):
        if r['questao'] in mapa:
            q=mapa[r['questao']];v=grupos[(materia(q),assunto(q))];v[0]+=1;v[1]+=r['acerto']
    itens=[]
    for (m,a),(n,s) in grupos.items():
        media=medias.get(m+'\n'+a,{}).get('percentual')
        itens.append({'materia':m,'assunto':a,'tentativas':n,'acertos':s,'erros':n-s,'percentual':round(100*s/n,1),'media':media})
    return {'assuntos':sorted(itens,key=lambda x:(x['percentual'],x['materia'],x['assunto'])),'atualizada':semana,'periodo':'Histórico anterior à segunda-feira desta semana, em UTC. Média dos percentuais por usuário; mínimo de cinco usuários. Conta de teste excluída.','mediaGeral':medias.get('*\n*',{}).get('percentual')}
