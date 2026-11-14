"""Controlador local de ambientes. Protocolo fechado; nunca recebe comandos Docker."""
import json, os, re, socketserver, subprocess, threading, time
from pathlib import Path
SOCKET=Path(os.environ.get('PU_SOCKET','/tmp/pu-gerenciador/controle.sock'))
REDE='enem_individuais'; IMAGEM='pu-individual:local'
PREFIXO=os.environ.get('PU_PREFIXO','pu-pessoa')
if not re.fullmatch(r'pu-[a-z-]{1,40}',PREFIXO):raise ValueError('Prefixo inválido.')
TRAVA=threading.Lock();USO={}
LIMITE=int(os.environ.get('PU_LIMITE_AMBIENTES','10'));OCIOSO=int(os.environ.get('PU_OCIOSO','900'))
def docker(*args):
    r=subprocess.run(['docker',*args],capture_output=True,text=True,timeout=30)
    if r.returncode:raise RuntimeError('Operação indisponível.')
    return r.stdout.strip()
def nome(conta):return PREFIXO+'-'+conta
def verificar(conta):
    return json.loads(docker('inspect',nome(conta)))[0]
def iniciar(conta):
    with TRAVA:
        try:info=verificar(conta)
        except RuntimeError:info=None
        if info and info['Config']['Labels'].get('pu.conta')!=conta:raise RuntimeError('Ambiente inválido.')
        atual=docker('image','inspect',IMAGEM,'--format','{{.Id}}')
        if info and info['Image']!=atual:
            docker('rm','-f',nome(conta)) # Só ambiente desta conta; volume permanece.
            info=None
        ativos=docker('ps','-q','--filter','label=pu.gerenciador='+PREFIXO).splitlines()
        if not info or not info['State']['Running']:
            if len(ativos)>=LIMITE:raise RuntimeError('Capacidade temporariamente atingida. Tente novamente.')
            if info:docker('start',nome(conta))
            else:
                docker('run','-d','--name',nome(conta),'--label','pu.individual=1','--label','pu.conta='+conta,'--label','pu.gerenciador='+PREFIXO,
                       '--network','none','--read-only','--cap-drop=ALL','--security-opt','no-new-privileges',
                       '--memory','64m','--cpus','0.25','--pids-limit','32','--log-driver','json-file',
                       '--log-opt','max-size=1m','--log-opt','max-file=2','--mount',
                       'type=volume,src='+PREFIXO+'-'+conta+',dst=/dados',IMAGEM)
        for tentativa in range(25):
            try:
                docker('exec',nome(conta),'python','-c',"import urllib.request;urllib.request.urlopen('http://localhost:8000/saude',timeout=1)")
                break
            except RuntimeError:
                if tentativa==24:raise
                time.sleep(.1)
        USO[conta]=time.monotonic()
        info=verificar(conta)
        return {'estado':'pronto'}
def parar_todos():
    with TRAVA:
        for id_ in docker('ps','-q','--filter','label=pu.gerenciador='+PREFIXO).splitlines():docker('stop','--time','3',id_)
        USO.clear()
def vigiar():
    while True:
        time.sleep(15)
        with TRAVA:
            for conta,ultima in list(USO.items()):
                if time.monotonic()-ultima>OCIOSO:
                    try:docker('stop','--time','3',nome(conta));USO.pop(conta,None)
                    except RuntimeError:pass
class Controle(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(5)
        try:
            linha=self.rfile.readline(4000001)
            if not linha:return
            if len(linha)>4000000:raise ValueError()
            pedido=json.loads(linha);conta=str(pedido.get('conta',''))
            if pedido.get('acao') not in ['iniciar','painel','site'] or not re.fullmatch(r'[1-9][0-9]{0,9}',conta):raise ValueError()
            resposta=iniciar(conta)
            if pedido['acao'] in ['painel','site']:
                corpo=pedido.get('painel')
                if pedido['acao']=='painel' and (not isinstance(corpo,dict) or str(corpo.get('conta',{}).get('id'))!=conta):raise ValueError()
                caminho=pedido.get('caminho','/')
                if caminho not in ['/','/app.js','/tema-inicial.js','/simulador.js','/estilo.css','/textura.svg'] and not re.fullmatch(r'/(?:fontes/[a-z0-9][a-z0-9-]{0,60}\.woff2|ilustracoes/[a-z0-9][a-z0-9-]{0,60}\.(?:webp|png))',caminho):raise ValueError()
                codigo="import sys,json,urllib.request,base64; p=json.load(sys.stdin); b=json.dumps(p['painel']).encode() if p['acao']=='painel' else None; r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000'+('/painel' if b else p['caminho']),data=b,headers={'Content-Type':'application/json'}),timeout=10); print(json.dumps({'corpo':base64.b64encode(r.read()).decode(),'tipo':r.headers.get('Content-Type')}))"
                r=subprocess.run(['docker','exec','-i',nome(conta),'python','-c',codigo],input=json.dumps({'acao':pedido['acao'],'painel':corpo,'caminho':caminho}),capture_output=True,text=True,timeout=15)
                if r.returncode:raise RuntimeError()
                resposta=json.loads(r.stdout)
        except Exception:resposta={'erro':'Não foi possível iniciar seu ambiente. Tente novamente em instantes.'}
        self.wfile.write(json.dumps(resposta).encode()+b'\n')
class Servidor(socketserver.ThreadingUnixStreamServer):daemon_threads=True
if __name__=='__main__':
    SOCKET.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if SOCKET.exists():
        # Não substitui um controlador ainda ativo.
        import socket
        with socket.socket(socket.AF_UNIX) as teste:
            if teste.connect_ex(str(SOCKET))==0:raise SystemExit('Controlador já está ativo.')
        SOCKET.unlink()
    # Recupera ambientes existentes após reinício, com prazo de inatividade novo.
    for conta in docker('ps','--filter','label=pu.gerenciador='+PREFIXO,'--format','{{.Label "pu.conta"}}').splitlines():
        if re.fullmatch(r'[1-9][0-9]{0,9}',conta):USO[conta]=time.monotonic()
    with Servidor(str(SOCKET),Controle) as servidor:
        SOCKET.chmod(0o666) # Diretório do host é 0700; só a central recebe montagem do socket.
        threading.Thread(target=vigiar,daemon=True).start()
        servidor.serve_forever()
