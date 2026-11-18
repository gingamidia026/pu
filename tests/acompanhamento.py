import sys,sqlite3,unittest,json
from pathlib import Path
from datetime import datetime,timezone,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from acompanhamento import preparar,ciclo,avancar,perfil,estudo,indice,ordem_intercalada,diagnostico,wilson_inferior,MINIMO_DIAGNOSTICO,FUSO
class Acompanhamento(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row
  self.c.executescript('CREATE TABLE contas(id INTEGER PRIMARY KEY,email TEXT);CREATE TABLE respostas(conta INTEGER,questao INTEGER,acerto INTEGER,criada REAL);')
  preparar(self.c)
  self.q=[{'id':1,'area':'Linguagens','materia':'Português','topico':'Texto'},{'id':2,'area':'Matemática','materia':'Matemática','topico':'Números'}]
 def test_ciclo_persistencia_sem_ordem_fixa_e_duplicacao(self):
  self.assertEqual(ciclo(self.c,1,self.q)['proxima'],1)
  # Foco por matéria: responder fora da ordem conta na densidade; repetir não conta duas vezes.
  self.assertFalse(avancar(self.c,1,2,self.q));self.assertFalse(avancar(self.c,1,2,self.q))
  self.assertEqual(ciclo(self.c,1,self.q)['feitas'],1)
  self.assertEqual(ciclo(self.c,1,self.q)['pendentes'],[1])
  self.assertEqual(ciclo(self.c,2,self.q)['feitas'],0)
  self.assertFalse(avancar(self.c,1,99,self.q))
  self.assertTrue(avancar(self.c,1,1,self.q))
  self.assertEqual(ciclo(self.c,1,self.q)['concluidas'],1)
  self.assertEqual(ciclo(self.c,1,self.q)['feitas'],0)
 def test_catalogo_removido_nao_completa(self):
  ciclo(self.c,1,self.q)
  restante=self.q[1:]
  self.assertEqual(ciclo(self.c,1,restante)['removidas'],1)
  self.assertFalse(ciclo(self.c,1,restante)['bloqueada'])
  self.assertFalse(avancar(self.c,1,2,restante))
  self.assertTrue(ciclo(self.c,1,restante)['bloqueada'])
  self.assertIsNone(ciclo(self.c,1,restante)['proxima'])
  self.assertEqual(ciclo(self.c,1,restante)['concluidas'],0)
 def test_ordem_intercalada_proporcional(self):
  q=[{'id':i,'area':'L','materia':'Português','topico':'T'} for i in range(1,5)]+[{'id':i,'area':'M','materia':'Matemática','topico':'N'} for i in range(5,13)]+[{'id':13,'area':'N','materia':'Física','topico':'F'}]
  ordem=ordem_intercalada(q)
  self.assertEqual(sorted(ordem),list(range(1,14)));self.assertEqual(ordem[0],1)
  materias=['P' if i<5 else 'M' if i<13 else 'F' for i in ordem]
  # Nenhuma matéria aparece em bloco: no máximo duas seguidas da matéria com mais questões.
  self.assertNotIn('MMM',''.join(materias));self.assertNotIn('PP',''.join(materias))
  self.assertEqual(ordem_intercalada([]),[])
  # Dentro da matéria os assuntos também se alternam, sem bloco de um assunto só.
  q=[{'id':i,'area':'M','materia':'Matemática','topico':'Álgebra' if i<=4 else 'Geometria'} for i in range(1,9)]
  assuntos=''.join('A' if i<=4 else 'G' for i in ordem_intercalada(q))
  self.assertNotIn('AA',assuntos);self.assertNotIn('GG',assuntos)
 def test_revisao_espacada_e_ritmo(self):
  agora=datetime(2026,11,12,15,0,tzinfo=FUSO)
  dia=lambda n,hora=10:(agora-timedelta(days=n)).replace(hour=hora).timestamp()
  por=lambda questao,acerto,quando,chute=0:self.c.execute('INSERT INTO respostas(conta,questao,acerto,criada,chute) VALUES(1,?,?,?,?)',(questao,acerto,quando,chute))
  por(1,0,dia(0))
  e=estudo(self.c,1,self.q,agora)
  self.assertEqual(e['hoje'],{'respostas':1,'acertos':0});self.assertEqual(e['revisao'],{'vencidas':[],'caderno':1,'intervalos':[1,3,7]})
  self.assertEqual(e['semana'][e['diaDaSemana']],1);self.assertEqual(sum(e['semana']),1)
  # No dia seguinte o erro vence; acerto seguro adia três dias; chute certo volta ao começo.
  amanha=agora+timedelta(days=1)
  self.assertEqual(estudo(self.c,1,self.q,amanha)['revisao']['vencidas'],[1])
  por(1,1,amanha.timestamp())
  self.assertEqual(estudo(self.c,1,self.q,amanha+timedelta(days=2))['revisao']['vencidas'],[])
  self.assertEqual(estudo(self.c,1,self.q,amanha+timedelta(days=3))['revisao']['vencidas'],[1])
  por(2,1,dia(2),1)
  e=estudo(self.c,1,self.q,agora)
  self.assertEqual(e['revisao']['vencidas'],[2]);self.assertEqual(e['revisao']['caderno'],2)
  # Três acertos seguros seguidos tiram a questão da revisão; quem nunca errou não entra.
  # Acerto adiantado (mesmo dia ou antes do prazo) não sobe de nível nem adia a revisão.
  vence=lambda dias:1 in estudo(self.c,1,self.q,amanha+timedelta(days=dias))['revisao']['vencidas']
  por(1,1,(amanha+timedelta(days=1)).timestamp());por(1,1,(amanha+timedelta(days=2)).timestamp())
  self.assertFalse(vence(2));self.assertTrue(vence(3))
  por(1,1,(amanha+timedelta(days=4)).timestamp())
  self.assertFalse(vence(10));self.assertTrue(vence(11))
  # Três acertos seguros no prazo tiram a questão do caderno; quem nunca errou não entra.
  por(1,1,(amanha+timedelta(days=11)).timestamp())
  self.assertFalse(vence(60));self.assertEqual(estudo(self.c,1,self.q,amanha+timedelta(days=60))['revisao']['caderno'],1)
  # Errar depois de dominar devolve a questão ao caderno.
  por(1,0,(amanha+timedelta(days=30)).timestamp())
  self.assertTrue(vence(31))
  self.assertEqual(estudo(self.c,2,self.q,agora)['revisao']['caderno'],0)
  # Questão fora do catálogo não aparece na revisão.
  self.assertEqual(estudo(self.c,1,self.q[:1],agora)['revisao']['vencidas'],[])
 def test_indice_sem_gabarito(self):
  q=[dict(self.q[0],enunciado='Curta',alternativas=['a','b'],correta=1,explicacao='x'),dict(self.q[1],enunciado='x'*2000,alternativas=['a'],correta=0)]
  i=indice(q);texto=json.dumps(i)
  self.assertEqual(i['curtas'],[1]);self.assertNotIn('correta',texto);self.assertNotIn('Curta',texto)
  self.assertEqual(i['materias'][0],{'nome':'Português','area':'Linguagens','topicos':[{'nome':'Texto','ids':[1]}]})
 def test_media_semanal_privacidade(self):
  for i in range(1,7):
   self.c.execute('INSERT INTO contas VALUES(?,?)',(i,'teste' if i==6 else str(i)))
   self.c.execute('INSERT INTO respostas(conta,questao,acerto,criada) VALUES(?,?,?,?)',(i,1,int(i!=1),1))
  p=perfil(self.c,1,self.q,datetime(2026,11,9,tzinfo=timezone.utc))
  self.assertEqual(p['mediaGeral'],80);self.assertEqual(p['assuntos'][0]['erros'],1)
  self.c.execute('INSERT INTO respostas(conta,questao,acerto,criada) VALUES(1,1,0,1)')
  self.assertEqual(perfil(self.c,1,self.q,datetime(2026,11,10,tzinfo=timezone.utc))['mediaGeral'],80)
  self.assertNotEqual(perfil(self.c,1,self.q,datetime(2026,11,16,tzinfo=timezone.utc))['atualizada'],p['atualizada'])
 def test_media_semanal_sem_amostra_e_grupo_pequeno(self):
  # Dominique-Oliveira-Claude🤖🧡, 18/11/2026: sem amostra não vira média fictícia; com menos de cinco usuários reais, nada sai.
  segunda=datetime(2026,11,16,tzinfo=timezone.utc); antes=segunda.timestamp()-3600
  self.c.execute("INSERT INTO contas VALUES(1,'1')")
  self.c.execute('INSERT INTO respostas(conta,questao,acerto,criada) VALUES(1,1,1,?)',(segunda.timestamp()+60,))
  p=perfil(self.c,1,self.q,segunda)
  self.assertIsNone(p['mediaGeral']);self.assertEqual([a['media'] for a in p['assuntos']],[None])
  # Quatro contas reais e a conta de teste, todas antes da segunda-feira: ainda abaixo do mínimo de cinco.
  for i in range(2,7):
   self.c.execute('INSERT INTO contas VALUES(?,?)',(i,'teste' if i==6 else str(i)))
  for i in [1,2,3,4,6]:
   self.c.execute('INSERT INTO respostas(conta,questao,acerto,criada) VALUES(?,1,1,?)',(i,antes))
  p=perfil(self.c,1,self.q,segunda+timedelta(weeks=1))
  self.assertIsNone(p['mediaGeral']);self.assertEqual([a['media'] for a in p['assuntos']],[None])
  # A quinta conta real libera a média na semana seguinte (a desta semana já ficou guardada).
  self.c.execute('INSERT INTO respostas(conta,questao,acerto,criada) VALUES(5,1,0,?)',(antes,))
  self.assertIsNone(perfil(self.c,1,self.q,segunda+timedelta(weeks=1,days=2))['mediaGeral'])
  p=perfil(self.c,1,self.q,segunda+timedelta(weeks=2))
  self.assertEqual(p['mediaGeral'],80);self.assertEqual(p['assuntos'][0]['media'],80)
  # O que sai para a conta: só os próprios números e a média; nem quantos usuários, nem contas.
  self.assertEqual(set(p),{'assuntos','atualizada','periodo','mediaGeral'})
  self.assertEqual(set(p['assuntos'][0]),{'materia','assunto','tentativas','acertos','erros','percentual','media'})
class Diagnostico(unittest.TestCase):
 """Diagnóstico de erros (docs/DIAGNOSTICO.md): ordem, mínimo de respostas, assunto em revisão, aluno sem respostas e isolamento."""
 AGORA=datetime(2026,11,18,12,tzinfo=timezone.utc)
 def setUp(self):
  self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row
  self.c.executescript('CREATE TABLE contas(id INTEGER PRIMARY KEY,email TEXT);CREATE TABLE respostas(conta INTEGER,questao INTEGER,alternativa INTEGER,acerto INTEGER,criada REAL);')
  preparar(self.c)
  self.q=[];self.relogio=0
  # Assuntos com 30 questões cada, para caber qualquer combinação de respostas.
  for n,(m,a) in enumerate([('Matemática','Funções'),('Matemática','Geometria'),('Física','Ondas'),('Química','Soluções'),('História','Brasil'),('Biologia','Células'),('Português','Leitura')]):
   for k in range(30): self.q.append({'id':100*n+k,'area':m,'materia':m,'topico':a})
  self.c.execute("INSERT INTO contas VALUES(1,'aluna@example.com')");self.c.execute("INSERT INTO contas VALUES(2,'outra@example.com')")
 def ids(self,assunto): return [q['id'] for q in self.q if q['topico']==assunto]
 def resp(self,conta,questao,acerto,chute=0,quando=None):
  self.relogio+=1
  self.c.execute('INSERT INTO respostas(conta,questao,alternativa,acerto,criada,chute) VALUES(?,?,0,?,?,?)',(conta,questao,acerto,quando if quando is not None else self.AGORA.timestamp()-100000+self.relogio,chute))
 def lote(self,conta,assunto,acertos,erros,chutes=0,quando=None):
  ids=iter(self.ids(assunto))
  for _ in range(acertos): self.resp(conta,next(ids),1,quando=quando)
  for _ in range(chutes): self.resp(conta,next(ids),1,1,quando=quando)
  for _ in range(erros): self.resp(conta,next(ids),0,quando=quando)
 def d(self,conta=1,questoes=None): return diagnostico(self.c,conta,questoes or self.q,self.AGORA)
 def test_sem_respostas(self):
  d=self.d()
  self.assertEqual(d['assuntos'],[]);self.assertEqual(d['respondidas'],0);self.assertEqual(d['foraEmRevisao'],0);self.assertEqual(d['minimo'],5)
 def test_ordem_pesada_pelo_numero_de_respostas(self):
  self.lote(1,'Funções',1,4)      # 80% de tropeço em 5: incerto
  self.lote(1,'Ondas',6,14)       # 70% em 20: mais certo, vem antes
  self.lote(1,'Soluções',4,6)     # 60% em 10
  self.lote(1,'Células',4,1)      # 80% de acerto: vai bem
  self.lote(1,'Brasil',0,3)       # só 3: ainda não dá para concluir
  d=self.d();nomes=[a['assunto'] for a in d['assuntos']]
  self.assertGreater(wilson_inferior(14,20),wilson_inferior(4,5))
  self.assertEqual(nomes,['Ondas','Funções','Soluções','Células','Brasil'])
  self.assertEqual([a['situacao'] for a in d['assuntos']],['treinar','treinar','treinar','bem','poucas'])
  ondas=d['assuntos'][0]
  self.assertEqual((ondas['respondidas'],ondas['acertos'],ondas['erros'],ondas['chutes'],ondas['acerto']),(20,6,14,0,30))
  brasil=d['assuntos'][-1]
  # Abaixo do mínimo, nada de porcentagem: só o número de respostas e quantas faltam.
  self.assertIsNone(brasil['acerto']);self.assertEqual((brasil['respondidas'],brasil['faltam']),(3,2));self.assertIsNone(brasil['media'])
  self.assertEqual(d['respondidas'],5+20+10+5+3)
 def test_minimo_exato_e_empate(self):
  self.lote(1,'Funções',1,3)
  self.assertEqual(self.d()['assuntos'][0]['situacao'],'poucas')
  self.lote(1,'Geometria',1,4);self.resp(1,self.ids('Funções')[4],0)
  d=self.d()
  self.assertEqual([(a['assunto'],a['situacao']) for a in d['assuntos']],[('Funções','treinar'),('Geometria','treinar')])
  self.assertEqual(MINIMO_DIAGNOSTICO,5)
 def test_primeira_tentativa_e_chute(self):
  ids=self.ids('Funções')
  for i in ids[:5]: self.resp(1,i,0)
  # Acertar de novo depois de ver a correção não apaga o erro da primeira vez.
  for i in ids[:5]: self.resp(1,i,1)
  a=self.d()['assuntos'][0]
  self.assertEqual((a['respondidas'],a['erros'],a['acerto']),(5,5,0))
  # Acerto no "chutei" não conta como acerto seguro.
  self.lote(1,'Leitura',3,0,chutes=2)
  leitura=[x for x in self.d()['assuntos'] if x['assunto']=='Leitura'][0]
  self.assertEqual((leitura['acertos'],leitura['chutes'],leitura['acerto'],leitura['situacao']),(3,2,60,'bem'))
  self.lote(1,'Células',2,0,chutes=3)
  celulas=[x for x in self.d()['assuntos'] if x['assunto']=='Células'][0]
  self.assertEqual((celulas['acerto'],celulas['situacao']),(40,'treinar'))
 def test_assunto_em_revisao_fica_de_fora(self):
  for q in self.q[:2]: q['revisar']=True
  self.lote(1,'Funções',0,7)
  d=self.d();a=d['assuntos'][0]
  self.assertEqual(d['foraEmRevisao'],2);self.assertEqual(a['respondidas'],5);self.assertEqual(a['erros'],5)
 def test_prova_desligada_e_questao_removida(self):
  self.lote(1,'Funções',0,5);self.lote(1,'Ondas',0,5);self.resp(1,99999,0)
  so_matematica=[q for q in self.q if q['materia']=='Matemática']
  self.assertEqual([a['assunto'] for a in self.d(questoes=so_matematica)['assuntos']],['Funções'])
 def test_isolamento_e_media_dos_outros(self):
  self.lote(2,'Funções',0,10)
  self.assertEqual(self.d(1)['assuntos'],[])
  self.lote(1,'Funções',2,3)
  d1=self.d(1);d2=self.d(2)
  self.assertEqual((d1['assuntos'][0]['respondidas'],d1['assuntos'][0]['erros']),(5,3))
  self.assertEqual((d2['assuntos'][0]['respondidas'],d2['assuntos'][0]['erros']),(10,10))
  self.assertIsNone(d1['assuntos'][0]['media'])
  # Média: só com cinco outros alunos que têm o mínimo no assunto, respostas até a segunda-feira, sem a conta de teste.
  antes=datetime(2026,11,10,tzinfo=timezone.utc).timestamp()
  for conta in range(3,9):
   self.c.execute('INSERT INTO contas VALUES(?,?)',(conta,'teste' if conta==8 else f'{conta}@example.com'))
   self.lote(conta,'Funções',5 if conta<8 else 0,0 if conta<8 else 5,quando=antes)
  self.lote(9,'Funções',5,0,quando=antes)   # conta sem cadastro em contas: fora
  self.c.execute('DELETE FROM medias')
  d1=self.d(1)
  # A conta 2 respondeu nesta semana e fica fora do cache; contam as contas 3 a 7, cinco alunos com 100%.
  self.assertEqual(d1['assuntos'][0]['media'],100)
  # Com a conta 10 (0%), o cache tem seis alunos; a conta 3 vê a média dos outros cinco, sem a dela.
  self.c.execute("INSERT INTO contas VALUES(10,'dez@example.com')");self.lote(10,'Funções',0,5,quando=antes);self.c.execute('DELETE FROM medias')
  self.assertEqual(self.d(1)['assuntos'][0]['media'],round(500/6))
  d3=self.d(3);self.assertEqual(d3['assuntos'][0]['media'],round(400/5))
  # A resposta leva só números agregados: nenhuma conta, e-mail ou questão de outro aluno.
  texto=json.dumps(d1)
  for proibido in ['example.com','conta','questao','"id"']: self.assertNotIn(proibido,texto)
  # Cache semanal: resposta nova de outro aluno só entra na média da semana seguinte.
  self.c.execute("INSERT INTO contas VALUES(11,'onze@example.com')");self.lote(11,'Funções',0,5,quando=antes)
  self.assertEqual(self.d(1)['assuntos'][0]['media'],round(500/6))
if __name__=='__main__':unittest.main()
