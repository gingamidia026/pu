"""Fixtures locais: inclusão, remoção, identidade, atomicidade e HTTP com histórico."""
import base64
from contextlib import redirect_stdout
import http.cookiejar
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request

RAIZ=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('sincronizar',RAIZ/'scripts/sincronizar-questoes.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
class Testes(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.raiz=Path(self.tmp.name);self.cofre=self.raiz/'cofre';self.destino=self.raiz/'catalogo'
  (self.cofre/'Provas Enem/Questões/2025').mkdir(parents=True)
  (self.cofre/'Matérias/Flashcards/Imagens exercícios').mkdir(parents=True)
  (self.cofre/'Leia-me.md').write_text('Fixture')
  (self.cofre/'Matérias/Flashcards/Imagens exercícios/q.png').write_bytes(PNG)
  self.nota(1)
 def tearDown(self):self.tmp.cleanup()
 def nota(self,n,anulada=False):
  p=self.cofre/f'Provas Enem/Questões/2025/2025-Q{n:02d}.md'
  p.write_text(f'''---
ano: 2025
dia: 1
caderno: 1 (azul)
questão: {n}
área: Linguagens
matéria: Português
gabarito: C
anulada: {str(anulada).lower()}
revisar: false
---
# Questão
![[q.png]]
## Texto
A finalidade deste enunciado é testar a extração.
A primeira alternativa
B segunda alternativa
C terceira alternativa
D quarta alternativa
E quinta alternativa
''');return p
 def sync(self):
  with redirect_stdout(io.StringIO()):return mod.sincronizar(self.cofre,self.destino)
 def catalogo(self):return json.loads((self.destino/'atual.json').read_text())
 def test_adicionar_apagar_retornar_identidade(self):
  self.sync();self.assertEqual((self.destino/'atual.json').stat().st_mode & 0o777,0o644);id1=self.catalogo()['questoes'][0]['id'];self.nota(2);r=self.sync();self.assertEqual(r['adicionadas'],1)
  self.assertEqual(self.catalogo()['questoes'][0]['id'],id1)
  self.nota(1).unlink();r=self.sync();self.assertEqual(r['removidas'],1);self.assertEqual(r['total'],1)
  self.nota(1);self.sync();self.assertEqual(self.catalogo()['questoes'][0]['id'],id1)
  self.assertEqual(self.sync()['adicionadas'],0)
 def test_invalido_ou_cofre_ausente_preserva(self):
  self.sync();antes=(self.destino/'atual.json').read_bytes()
  self.nota(2).write_text('inválido')
  with self.assertRaises(ValueError):self.sync()
  self.assertEqual((self.destino/'atual.json').read_bytes(),antes)
  with self.assertRaises(ValueError):mod.sincronizar(self.raiz/'inexistente',self.destino)
  self.assertEqual((self.destino/'atual.json').read_bytes(),antes)
 def test_anuladas_e_catalogo_vazio(self):
  self.nota(2,True);r=self.sync();self.assertEqual((r['total'],r['anuladas']),(1,1))
  self.nota(1).unlink();self.nota(2).unlink();self.sync();self.assertEqual(self.catalogo()['questoes'],[])
  resultado=subprocess.check_output(['python3','-c','import questoes; print(len(questoes.QUESTOES))'],cwd=RAIZ/'app',env={**os.environ,'CATALOGO':str(self.destino/'atual.json')},text=True)
  self.assertEqual(resultado.strip(),'0')
 def test_imagem_fora_da_pasta_rejeitada(self):
  f=self.nota(1);f.write_text(f.read_text().replace('q.png','../segredo.png'))
  with self.assertRaises(ValueError):self.sync()
 def test_reinicio_automatico_com_docker_simulado(self):
  projeto=self.raiz/'projeto';(projeto/'scripts').mkdir(parents=True)
  shutil.copy(RAIZ/'vpt',projeto/'vpt');shutil.copy(RAIZ/'scripts/sincronizar-questoes.py',projeto/'scripts')
  (projeto/'scripts/corrigir-questoes.py').write_text("print('Separador simulado; extração real tem suíte própria.')\n")
  # Este teste isola a sincronização; o gerenciador real tem teste Docker próprio.
  (projeto/'gerenciador').mkdir()
  (projeto/'gerenciador/iniciar.py').write_text("print('Gerenciador simulado para teste de sincronização.')\n")
  fake=self.raiz/'bin';fake.mkdir();docker=fake/'docker';docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$PU_LOG_TESTE"\n');docker.chmod(0o755)
  registro=self.raiz/'docker.log';ambiente={**os.environ,'PATH':str(fake)+':'+os.environ['PATH'],'DOCKER_HOST':'fixture','PU_COFRE_VESTIBULAR':str(self.cofre),'PU_LOG_TESTE':str(registro)}
  subprocess.run(['bash',str(projeto/'vpt'),'reiniciar'],check=True,env=ambiente,stdout=subprocess.DEVNULL)
  self.assertEqual(len(json.loads((projeto/'.catalogo/atual.json').read_text())['questoes']),1)
  self.assertIn('--force-recreate',registro.read_text())
  self.nota(2).write_text('inválido');antes=registro.read_text();r=subprocess.run(['bash',str(projeto/'vpt'),'reiniciar'],env=ambiente,capture_output=True)
  self.assertNotEqual(r.returncode,0);self.assertEqual(registro.read_text(),antes+'info\n')
 def test_api_historico_e_remocao(self):
  self.nota(2);self.sync();ids=[q['id'] for q in self.catalogo()['questoes']]
  cliente=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
  def iniciar():
   with socket.socket() as s:s.bind(('127.0.0.1',0));porta=s.getsockname()[1]
   origem=f'http://127.0.0.1:{porta}'
   proc=subprocess.Popen(['python3',str(RAIZ/'app/servidor.py')],env={**os.environ,'DADOS':str(self.raiz/'dados'),'PORTA':str(porta),'ORIGEM':origem,'CATALOGO':str(self.destino/'atual.json')},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   for _ in range(100):
    try:urllib.request.urlopen(origem+'/api/saude',timeout=1).close();break
    except OSError:time.sleep(.05)
   return proc,origem
  def pedido(caminho,dados=None):
   req=urllib.request.Request(origem+caminho,data=None if dados is None else json.dumps(dados).encode(),headers={'Origin':origem,'Content-Type':'application/json'})
   try:r=cliente.open(req)
   except urllib.error.HTTPError as e:r=e
   with r:b=r.read();return r.status,json.loads(b),len(b)
  proc,origem=iniciar()
  try:
   status,r,_=pedido('/api/cadastro',{'nome':'Fixture','email':'fixture@example.com','senha':'Senha fixture longa 123!'});self.assertEqual(status,200);self.assertEqual(r['painel']['catalogo']['ativas'],2)
   # O painel não leva mais a lista do catálogo (14/11/2026); a questão inicial continua sem gabarito.
   self.assertEqual(r['painel']['questoes'],[]);self.assertNotIn('correta',r['painel']['inicial'])
   status,q,_=pedido('/api/questoes/'+str(ids[0]));self.assertEqual(status,200);self.assertNotIn('correta',q)
   status,img,tamanho=pedido('/api/questoes/'+str(ids[0]),{'acao':'imagem','indice':0,'parte':0});self.assertEqual(status,200);self.assertLess(tamanho,100000);self.assertEqual(base64.b64decode(img['bloco']),PNG)
   self.assertEqual(pedido('/api/questoes/'+str(ids[0]),{'acao':'imagem','indice':True,'parte':0})[0],400)
   self.assertEqual(pedido('/api/questoes/'+str(ids[0]),{'alternativa':2})[1]['acerto'],True)
   proc.terminate();proc.wait();self.nota(1).unlink();self.sync();proc,origem=iniciar()
   status,p,_=pedido('/api/painel');self.assertEqual(status,200);self.assertEqual(p['catalogo']['ativas'],1);self.assertEqual(p['progresso']['total'],1)
   self.assertEqual(pedido('/api/questoes/'+str(ids[0]))[0],404)
  finally:proc.terminate();proc.wait()
if __name__=='__main__':unittest.main(verbosity=2)
