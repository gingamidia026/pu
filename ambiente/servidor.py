"""Site individual: só recebe painel já filtrado, sem acesso à central ou a gabaritos."""
import json
import os
import re
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
DADOS=Path('/dados')
PUBLICO=Path('/site')
# Mesma expressão de app/servidor.py (RECURSO_ESTATICO) e de gerenciador/servidor.py.
RECURSO=re.compile(r'/(?:fontes/[a-z0-9][a-z0-9-]{0,60}\.woff2|ilustracoes/[a-z0-9][a-z0-9-]{0,60}\.(?:webp|png))')
class Site(BaseHTTPRequestHandler):
    def setup(self):
        super().setup();self.connection.settimeout(10)
    def log_message(self,*args):pass
    def responder(self,status,corpo,tipo='application/json'):
        self.send_response(status);self.send_header('Content-Type',tipo);self.send_header('Content-Length',str(len(corpo)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(corpo)
    def do_POST(self):
        if self.path!='/painel':return self.responder(404,b'{}')
        try:
            tamanho=int(self.headers.get('Content-Length','0'))
            if not 0<tamanho<4000000:return self.responder(413,b'{}')
            corpo=self.rfile.read(tamanho);dados=json.loads(corpo)
            if not isinstance(dados,dict):raise ValueError()
            temporario=DADOS/'painel.novo';temporario.write_bytes(corpo);temporario.chmod(0o600);temporario.replace(DADOS/'painel.json')
            self.responder(200,corpo)
        except (ValueError,OSError):self.responder(400,b'{}')
    def do_GET(self):
        if self.path=='/saude':return self.responder(200,b'{"ok":true}')
        arquivos={'/':'index.html','/app.js':'app.js','/tema-inicial.js':'tema-inicial.js','/simulador.js':'simulador.js','/estilo.css':'estilo.css','/textura.svg':'textura.svg'}
        caminho=self.path.split('?')[0]
        nome=arquivos.get(caminho) or (caminho[1:] if RECURSO.fullmatch(caminho) and (PUBLICO/caminho[1:]).is_file() else None)
        if not nome:return self.responder(404,b'{}')
        tipos={'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.woff2':'font/woff2','.webp':'image/webp','.png':'image/png'}
        self.responder(200,(PUBLICO/nome).read_bytes(),tipos[Path(nome).suffix])
os.umask(0o077)
HTTPServer(('0.0.0.0',8000),Site).serve_forever()
