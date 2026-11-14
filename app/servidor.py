"""API restrita: nenhum caminho ou comando fornecido pelo navegador é executado."""
import hashlib
import hmac
import json
import ipaddress
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from questoes import QUESTOES, CATALOGO, ARQUIVO_CATALOGO
import base64
from ambientes import AmbienteIndisponivel, ATIVO as INDIVIDUAIS, solicitar as ambiente, painel_individual
from acompanhamento import preparar, ciclo, avancar, perfil, estudo, indice
from conjuntos import membros as membros_conjunto, responder as responder_conjunto

DADOS = Path(os.environ.get('DADOS', '/dados'))
DADOS.mkdir(parents=True, exist_ok=True)
os.chmod(DADOS, 0o700)
BANCO = DADOS / 'estudos.sqlite3'
ORIGEM = os.environ.get('ORIGEM', 'http://localhost:8088')
PERFIL_TESTE = os.environ.get('PERFIL_TESTE', '0') == '1'
SEGURO = os.environ.get('COOKIE_SEGURO', '0') == '1'
PRODUCAO = os.environ.get('PRODUCAO', '0') == '1'
PROXY_CONFIAVEL = os.environ.get('PROXY_CONFIAVEL', '0') == '1'
COOKIE = '__Host-sessao' if SEGURO else 'sessao'
VAGAS_SENHA = threading.BoundedSemaphore(2)
# Entradas e cadastros por origem em 15 minutos. Pela fila pública todo pedido chega do conector (uma origem só),
# então o compose.publico.yaml sobe este teto: com 30, uma pessoa insistente bloqueava a entrada de todas as outras.
# O limite por conta (10) e o do intermediário (60 por minuto por IP) continuam valendo. Revisão de 13/11/2026.
LIMITE_ORIGEM = max(30, int(os.environ.get('LIMITE_ENTRADAS_ORIGEM', '30')))
if PRODUCAO and (not SEGURO or PERFIL_TESTE or not ORIGEM.startswith('https://')):
    raise RuntimeError('Produção exige HTTPS, cookie seguro e perfil de teste desligado.')
PUBLICO = Path(__file__).parent / 'public'
# Fontes (woff2) e ilustrações (webp, png) da identidade: nome simples, sem subpasta e sem "..". SVG fica de fora: no mesmo
# domínio ele pode levar script. A mesma expressão está em ambiente/servidor.py e gerenciador/servidor.py (processos separados);
# tests/fluida-navegador.mjs confere que as três são iguais.
RECURSO_ESTATICO = re.compile(r'/(?:fontes/[a-z0-9][a-z0-9-]{0,60}\.woff2|ilustracoes/[a-z0-9][a-z0-9-]{0,60}\.(?:webp|png))')
TIPOS_ESTATICOS = {'woff2': 'font/woff2', 'webp': 'image/webp', 'png': 'image/png'}
INDICE = indice(QUESTOES)
MAPA = {q['id']: q for q in QUESTOES}

def publica(questao):
    """Questão sem gabarito, explicação ou estatística; conjuntos levam as perguntas irmãs."""
    limpa = lambda q: {k: v for k, v in q.items() if k not in ['correta', 'explicacao', 'estatisticaOriginal']}
    item = limpa(questao)
    if questao.get('grupo'):
        item['grupoQuestoes'] = [{k: v for k, v in limpa(q).items() if k != 'textoComum'} for q in membros_conjunto(questao, QUESTOES)]
    return item

def sugerida(densidade, ritmo):
    """Primeira questão do dia: curta e sem figura, para começar sem esforço. Depois, revisão vencida ou a fila."""
    pendentes = densidade['pendentes']
    if ritmo['hoje']['respostas'] == 0:
        curtas = set(INDICE['curtas'])
        for i in pendentes:
            if i in curtas:
                return i
    vencidas = ritmo['revisao']['vencidas']
    return vencidas[0] if vencidas else (pendentes[0] if pendentes else None)

def anexar_proxima(resultado, dados):
    """Entrega a próxima questão na mesma resposta, para poupar uma viagem. Nunca inclui gabarito."""
    proxima = dados.get('proxima')
    if type(proxima) is int and proxima in MAPA:
        resultado = dict(resultado, proximaQuestao=publica(MAPA[proxima]))
    return resultado

@contextmanager
def banco():
    con = sqlite3.connect(BANCO, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    try:
        with con:
            yield con
    finally:
        con.close()

with banco() as con:
    con.executescript('''
    CREATE TABLE IF NOT EXISTS contas(id INTEGER PRIMARY KEY, nome TEXT NOT NULL, email TEXT UNIQUE NOT NULL, sal TEXT NOT NULL, senha TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sessoes(token TEXT PRIMARY KEY, conta INTEGER REFERENCES contas(id), expira REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS respostas(id INTEGER PRIMARY KEY, conta INTEGER REFERENCES contas(id), questao INTEGER NOT NULL, alternativa INTEGER NOT NULL, acerto INTEGER NOT NULL, criada REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS limites(chave TEXT PRIMARY KEY, inicio REAL NOT NULL, total INTEGER NOT NULL);
    ''')
with banco() as con:
    con.execute('CREATE TABLE IF NOT EXISTS dispositivos(id TEXT PRIMARY KEY, conta INTEGER REFERENCES contas(id), nome TEXT NOT NULL, criado REAL NOT NULL, ultimo REAL NOT NULL, revogado INTEGER NOT NULL DEFAULT 0)')
    if 'dispositivo' not in [r[1] for r in con.execute('PRAGMA table_info(sessoes)')]:
        con.execute('ALTER TABLE sessoes ADD COLUMN dispositivo TEXT')
    preparar(con)
os.chmod(BANCO, 0o600)

def resumo(senha, sal, legado=False):
    if not VAGAS_SENHA.acquire(blocking=False):
        raise Erro(429, 'Muitas solicitações de entrada. Tente novamente em instantes.')
    try:
        # Parâmetros registrados junto ao hash; mantém leitura das contas antigas.
        n, p = (16384, 1) if legado else (32768, 3)
        valor = hashlib.scrypt(senha.encode(), salt=bytes.fromhex(sal), n=n, r=8, p=p, maxmem=64*1024*1024).hex()
        return valor if legado else 'scrypt$32768$8$3$' + valor
    finally:
        VAGAS_SENHA.release()

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

# Perfil local explícito; não redefine senha ou histórico a cada reinício.
if PERFIL_TESTE:
    with banco() as con:
        if not con.execute('SELECT 1 FROM contas WHERE email=?', ('teste',)).fetchone():
            sal = secrets.token_hex(16)
            con.execute('INSERT INTO contas(nome,email,sal,senha) VALUES(?,?,?,?)',
                        ('Teste', 'teste', sal, resumo('123', sal)))

class Erro(Exception):
    def __init__(self, status, mensagem):
        self.status, self.mensagem = status, mensagem

class Servidor(ThreadingHTTPServer):
    daemon_threads = True
    vagas = threading.BoundedSemaphore(32)
    def process_request(self, request, client_address):
        self.vagas.acquire()
        try:
            super().process_request(request, client_address)
        except Exception:
            self.vagas.release()
            raise
    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.vagas.release()

class API(BaseHTTPRequestHandler):
    server_version = 'Estudos'
    sys_version = ''
    def setup(self):
        super().setup()
        self.connection.settimeout(15)
    def log_message(self, formato, *args):
        # Não registrar corpo, cookies, nomes ou e-mails.
        pass
    def registrar(self, evento, status):
        # Somente categorias fixas; sem URL, IP, e-mail, senha, sessão ou corpo.
        print(json.dumps({'tempo': int(time.time()), 'evento': evento, 'status': status}), flush=True)
    def cliente(self):
        endereco = self.headers.get('X-ENEM-Cliente', '') if PROXY_CONFIAVEL else self.client_address[0]
        try:
            return digest(str(ipaddress.ip_address(endereco)))
        except ValueError:
            raise Erro(400, 'Identificação de conexão inválida.')
    def enviar(self, status, dado, tipo='application/json; charset=utf-8', cookie=None):
        corpo = json.dumps(dado, ensure_ascii=False).encode() if tipo.startswith('application/json') else dado
        self.send_response(status)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(corpo)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if SEGURO:
            self.send_header('Strict-Transport-Security', 'max-age=31536000')
        if cookie:
            self.send_header('Set-Cookie', cookie)
        if status == 429:
            self.send_header('Retry-After', '900')
        self.end_headers()
        self.wfile.write(corpo)
    def painel(self, con, conta):
        totais = con.execute('SELECT COUNT(*) total,COALESCE(SUM(acerto),0) acertos FROM respostas WHERE conta=?', (conta['id'],)).fetchone()
        # Somente enunciados; gabarito e explicação continuam exclusivos da correção.
        densidade = ciclo(con, conta['id'], QUESTOES)
        ritmo = estudo(con, conta['id'], QUESTOES)
        primeira = sugerida(densidade, ritmo)
        painel = {'densidade': densidade, 'estudo': ritmo, 'indice': INDICE, 'inicial': publica(MAPA[primeira]) if primeira in MAPA else None,
            'perfil': perfil(con, conta['id'], QUESTOES), 'conta': conta, 'progresso': dict(totais), 'questoes': [
            {k: q[k] for k in (['id','area','titulo'] if q.get('oficial') else ['id', 'area', 'titulo', 'enunciado', 'alternativas'])} for q in QUESTOES],
            'catalogo': {'origem':'cofre','total':len(QUESTOES),'anuladas':CATALOGO['anuladas'],'revisar':CATALOGO['revisar'],'versao':CATALOGO['versao']} if CATALOGO is not None else {'origem':'vazio','total':0}}

        return painel_individual(conta['id'], painel)

    def token(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            return cookie[COOKIE].value if COOKIE in cookie else ''
        except Exception:
            return ''
    def conta(self, con):
        conta = con.execute('SELECT c.id,c.nome FROM contas c JOIN sessoes s ON s.conta=c.id WHERE s.token=? AND s.expira>? AND (c.email!=? OR ?)', (digest(self.token()), time.time(), 'teste', PERFIL_TESTE)).fetchone()
        sessao = con.execute('SELECT dispositivo FROM sessoes WHERE token=?',(digest(self.token()),)).fetchone()
        if sessao and sessao['dispositivo']:
            dispositivo=con.execute('SELECT revogado FROM dispositivos WHERE id=? AND conta=?',(sessao['dispositivo'],conta['id'] if conta else -1)).fetchone()
            if not dispositivo or dispositivo['revogado']:conta=None
        elif INDIVIDUAIS:
            conta=None
        if not conta:
            raise Erro(401, 'Entre na sua conta para continuar.')
        return dict(conta)
    def limitar(self, con, chave, limite):
        agora = time.time()
        con.execute('DELETE FROM limites WHERE inicio<?', (agora - 900,))
        con.execute('INSERT INTO limites VALUES(?,?,1) ON CONFLICT(chave) DO UPDATE SET total=total+1', (chave, agora))
        total = con.execute('SELECT total FROM limites WHERE chave=?', (chave,)).fetchone()[0]
        con.commit()
        if total > limite:
            raise Erro(429, 'Muitas tentativas. Aguarde 15 minutos.')
    def executar(self, metodo):
        try:
            self.rota(metodo)
        except Erro as erro:
            if erro.status in [401,403,413,429]:
                self.registrar('solicitacao_recusada', erro.status)
            self.enviar(erro.status, {'erro': erro.mensagem})
        except AmbienteIndisponivel:
            self.enviar(503, {'erro':'Seu ambiente está indisponível no momento. Tente novamente em instantes.'})
        except (ValueError, TypeError, KeyError, UnicodeDecodeError):
            self.enviar(400, {'erro': 'Dados inválidos. Confira os campos.'})
        except Exception:
            self.registrar('falha_interna', 500)
            self.enviar(500, {'erro': 'Não foi possível concluir. Tente novamente.'})
    def do_GET(self):
        self.executar('GET')
    def do_POST(self):
        self.executar('POST')
    def rota(self, metodo):
        caminho = self.path.split('?')[0]
        if caminho.startswith('/api/') and '?' in self.path:
            raise Erro(400, 'Parâmetros de consulta não permitidos.')
        if metodo == 'GET' and caminho in ['/', '/app.js', '/tema-inicial.js', '/simulador.js', '/estilo.css', '/textura.svg']:
            arquivo = PUBLICO / {'/': 'index.html', '/app.js': 'app.js', '/tema-inicial.js': 'tema-inicial.js', '/simulador.js': 'simulador.js', '/estilo.css': 'estilo.css', '/textura.svg': 'textura.svg'}[caminho]
            tipo = {'/': 'text/html; charset=utf-8', '/app.js': 'text/javascript; charset=utf-8', '/tema-inicial.js': 'text/javascript; charset=utf-8', '/simulador.js': 'text/javascript; charset=utf-8', '/estilo.css': 'text/css; charset=utf-8', '/textura.svg': 'image/svg+xml'}[caminho]
            return self.enviar(200, arquivo.read_bytes(), tipo)
        if metodo == 'GET' and RECURSO_ESTATICO.fullmatch(caminho) and (PUBLICO / caminho[1:]).is_file():
            return self.enviar(200, (PUBLICO / caminho[1:]).read_bytes(), TIPOS_ESTATICOS[caminho.rsplit('.', 1)[1]])
        if metodo == 'GET' and caminho == '/api/saude':
            return self.enviar(200, {'estado': 'ok'})
        if metodo == 'GET' and caminho == '/api/configuracao':
            return self.enviar(200, {'perfilTeste': PERFIL_TESTE})
        dados = {}
        if metodo == 'POST':
            if self.headers.get('Origin') != ORIGEM:
                raise Erro(403, 'Origem não autorizada.')
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise Erro(415, 'Envie dados no formato JSON.')
            tamanho = int(self.headers.get('Content-Length', '0'))
            if tamanho < 1 or tamanho > 16384:
                raise Erro(413, 'Pedido excede o tamanho permitido.')
            dados = json.loads(self.rfile.read(tamanho))
            if not isinstance(dados, dict):
                raise Erro(400, 'Envie um objeto JSON.')
            # A identidade vem exclusivamente da sessão, nunca do pedido.
            if any(campo in dados for campo in ['conta', 'conta_id', 'usuario', 'usuario_id', 'dono', 'caminho', 'arquivo']):
                raise Erro(400, 'Este pedido contém campos não permitidos.')
        with banco() as con:
            if metodo == 'POST' and caminho in ['/api/cadastro', '/api/entrar']:
                cliente = self.cliente()
                self.limitar(con, 'entrada_origem:' + cliente, LIMITE_ORIGEM)
                email = dados.get('email', '')
                if not isinstance(email, str):
                    raise Erro(400, 'Informe um e-mail válido.')
                email = email.strip().lower()
                senha = dados.get('senha', '')
                eh_teste = caminho == '/api/entrar' and email == 'teste' and PERFIL_TESTE
                if not isinstance(senha, str) or len(senha) > 128 or not senha:
                    raise Erro(400, 'Informe sua senha.')
                if not eh_teste and (not re.fullmatch(r'[^\s@]{1,100}@[^\s@]{1,100}\.[^\s@]{2,30}', email) or not 12 <= len(senha) <= 128):
                    raise Erro(400, 'Informe e-mail válido e senha com 12 a 128 caracteres.')
                # Pela fila pública todos chegam do conector: só a cota por conta e origem deixaria quem sabe o e-mail
                # travar a dona da conta com 10 senhas erradas. Navegador já autorizado da conta tem cota própria,
                # que quem não conhece o identificador dele não alcança. Revisão de segurança de 14/11/2026.
                balde = 'entrada_conta_origem:' + digest(email) + ':' + cliente
                aparelho = dados.get('dispositivo', '')
                if isinstance(aparelho, str) and re.fullmatch(r'[A-Za-z0-9_-]{32,100}', aparelho):
                    dona = con.execute('SELECT id FROM contas WHERE email=?', (email,)).fetchone()
                    if dona and con.execute('SELECT 1 FROM dispositivos WHERE id=? AND conta=? AND revogado=0', (digest(str(dona['id']) + ':' + aparelho), dona['id'])).fetchone():
                        balde = 'entrada_conta_dispositivo:' + digest(email) + ':' + digest(aparelho)
                self.limitar(con, balde, 10)
                if caminho == '/api/cadastro':
                    nome = dados.get('nome', '')
                    if not isinstance(nome, str):
                        raise Erro(400, 'Informe um nome válido.')
                    nome = nome.strip()
                    if not 2 <= len(nome) <= 80:
                        raise Erro(400, 'O nome deve ter de 2 a 80 caracteres.')
                    sal = secrets.token_hex(16)
                    try:
                        con.execute('INSERT INTO contas(nome,email,sal,senha) VALUES(?,?,?,?)', (nome, email, sal, resumo(senha, sal)))
                        con.commit()
                    except sqlite3.IntegrityError:
                        raise Erro(400, 'Não foi possível cadastrar. Confira os dados ou entre na sua conta.')
                conta = con.execute('SELECT * FROM contas WHERE email=?', (email,)).fetchone()
                sal = conta['sal'] if conta else '0' * 32
                legado = bool(conta and not conta['senha'].startswith('scrypt$'))
                valido = hmac.compare_digest(resumo(senha, sal, legado), conta['senha'] if conta else '0' * 128)
                if not conta or not valido:
                    raise Erro(401, 'E-mail ou senha incorretos.')
                if legado:
                    con.execute('UPDATE contas SET senha=? WHERE id=?', (resumo(senha, sal), conta['id']))
                identificador=dados.get('dispositivo','')
                if not isinstance(identificador,str) or (identificador and not re.fullmatch(r'[A-Za-z0-9_-]{32,100}',identificador)):
                    raise Erro(400,'Identificação do dispositivo inválida.')
                identificador=identificador or secrets.token_urlsafe(32)
                id_dispositivo=digest(str(conta['id'])+':'+identificador)
                registrado=con.execute('SELECT revogado FROM dispositivos WHERE id=? AND conta=?',(id_dispositivo,conta['id'])).fetchone()
                if registrado and registrado['revogado']:
                    raise Erro(403,'Este dispositivo foi revogado. Use outro dispositivo autorizado.')
                if not registrado:
                    if con.execute('SELECT COUNT(*) FROM dispositivos WHERE conta=? AND revogado=0',(conta['id'],)).fetchone()[0]>=5:
                        raise Erro(403,'Limite de cinco dispositivos. Revogue um dispositivo antes de adicionar outro.')
                    nome_dispositivo=dados.get('nomeDispositivo','Navegador')
                    if not isinstance(nome_dispositivo,str) or not 1<=len(nome_dispositivo)<=60:raise Erro(400,'Nome do dispositivo inválido.')
                    con.execute('INSERT INTO dispositivos(id,conta,nome,criado,ultimo) VALUES(?,?,?,?,?)',(id_dispositivo,conta['id'],nome_dispositivo,time.time(),time.time()))
                else:con.execute('UPDATE dispositivos SET ultimo=? WHERE id=?',(time.time(),id_dispositivo))
                token = secrets.token_urlsafe(32)
                con.execute('DELETE FROM sessoes WHERE expira<? OR token=?', (time.time(), digest(self.token())))
                con.execute('INSERT INTO sessoes(token,conta,expira,dispositivo) VALUES(?,?,?,?)', (digest(token), conta['id'], time.time() + 30 * 86400,id_dispositivo))
                con.execute('DELETE FROM sessoes WHERE conta=? AND token NOT IN (SELECT token FROM sessoes WHERE conta=? ORDER BY expira DESC LIMIT 5)', (conta['id'], conta['id']))
                con.commit()
                self.registrar('entrada_aceita', 200)
                cookie = f'{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000' + ('; Secure' if SEGURO else '')
                return self.enviar(200, ({'nome': conta['nome'], 'iniciando':True, 'dispositivo':identificador} if INDIVIDUAIS else {'nome': conta['nome'], 'dispositivo':identificador, 'painel': self.painel(con, {'id': conta['id'], 'nome': conta['nome']})}), cookie=cookie)
            conta = self.conta(con)
            if INDIVIDUAIS and metodo=='GET' and caminho.startswith('/site/'):
                recurso=caminho[len('/site'):]
                if recurso not in ['/','/app.js','/tema-inicial.js','/simulador.js','/estilo.css','/textura.svg'] and not RECURSO_ESTATICO.fullmatch(recurso):raise Erro(404,'Página não encontrada.')
                resposta=ambiente(conta['id'],'site',caminho=recurso)
                return self.enviar(200,base64.b64decode(resposta['corpo']),resposta['tipo'])
            if caminho == '/api/dispositivos':
                if metodo=='GET':
                    atual=con.execute('SELECT dispositivo FROM sessoes WHERE token=?',(digest(self.token()),)).fetchone()[0]
                    return self.enviar(200,{'dispositivos':[dict(r,atual=r['id']==atual) for r in con.execute('SELECT id,nome,ultimo FROM dispositivos WHERE conta=? AND revogado=0',(conta['id'],))]})
                alvo=dados.get('id')
                if dados.get('acao')!='revogar' or not isinstance(alvo,str):raise Erro(400,'Dispositivo inválido.')
                if not con.execute('SELECT 1 FROM dispositivos WHERE conta=? AND id=? AND revogado=0',(conta['id'],alvo)).fetchone():raise Erro(404,'Dispositivo não encontrado.')
                con.execute('UPDATE dispositivos SET revogado=1 WHERE conta=? AND id=?',(conta['id'],alvo))
                con.execute('DELETE FROM sessoes WHERE conta=? AND dispositivo=?',(conta['id'],alvo))
                con.commit()
                return self.enviar(200,{'ok':True})
            if metodo == 'POST' and caminho == '/api/sair':
                con.execute('DELETE FROM sessoes WHERE token=?', (digest(self.token()),))
                con.commit()
                return self.enviar(200, {'ok': True}, cookie=COOKIE+'=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0' + ('; Secure' if SEGURO else ''))
            if metodo == 'GET' and caminho == '/api/painel':
                return self.enviar(200, self.painel(con, conta))
            partes = re.fullmatch(r'/api/questoes/([0-9]+)', caminho)
            if partes:
                if INDIVIDUAIS:ambiente(conta['id'])
                questao = next((q for q in QUESTOES if q['id'] == int(partes[1])), None)
                if not questao:
                    raise Erro(404, 'Questão não encontrada.')
                if metodo == 'GET':
                    return self.enviar(200,publica(questao))
                if dados.get('acao') == 'imagem':
                    indice, parte = dados.get('indice'), dados.get('parte')
                    imagens = questao.get('imagens', [])
                    if type(indice) is not int or not 0 <= indice < len(imagens):
                        raise Erro(400, 'Imagem inválida.')
                    info = imagens[indice]
                    if type(parte) is not int or not 0 <= parte < info['partes']:
                        raise Erro(400, 'Parte de imagem inválida.')
                    sha = info['hash']
                    if not re.fullmatch(r'[0-9a-f]{64}', sha):
                        raise Erro(400, 'Imagem inválida.')
                    arquivo = Path(ARQUIVO_CATALOGO).parent / 'imagens' / (sha + '.png')
                    with arquivo.open('rb') as imagem:
                        imagem.seek(parte * 49152)
                        bloco = imagem.read(49152)
                    return self.enviar(200, {'bloco':base64.b64encode(bloco).decode(), 'partes':info['partes'], 'tipo':'image/png', 'hash':sha})
                if questao.get('grupo'):
                    self.limitar(con,'respostas:'+str(conta['id']),200)
                    try: resultado=responder_conjunto(con,conta['id'],questao,QUESTOES,dados)
                    except ValueError as e: raise Erro(400,str(e))
                    return self.enviar(200,anexar_proxima(resultado,dados))
                alternativa = dados.get('alternativa')
                if type(alternativa) is not int or not 0 <= alternativa < len(questao['alternativas']):
                    raise Erro(400, 'Selecione uma alternativa válida.')
                self.limitar(con, 'respostas:' + str(conta['id']), 200)
                chave = dados.get('envio')
                if chave is not None and (not isinstance(chave,str) or not re.fullmatch(r'[a-zA-Z0-9-]{20,80}',chave)):
                    raise Erro(400, 'Identificador de envio inválido.')
                con.execute('BEGIN IMMEDIATE')
                if chave:
                    anterior=con.execute('SELECT * FROM envios WHERE conta=? AND chave=?',(conta['id'],chave)).fetchone()
                    if anterior:
                        if anterior['questao'] != questao['id'] or anterior['alternativa'] != alternativa:
                            raise Erro(409, 'Este envio já foi usado para outra resposta.')
                        return self.enviar(200,anexar_proxima(json.loads(anterior['resultado']),dados))
                acerto = alternativa == questao['correta']
                # "Chutei" vem do aluno e só afeta a revisão dele; o acerto continua decidido aqui.
                con.execute('INSERT INTO respostas(conta,questao,alternativa,acerto,criada,chute) VALUES(?,?,?,?,?,?)', (conta['id'], questao['id'], alternativa, acerto, time.time(), int(dados.get('chute') is True)))
                concluida=avancar(con,conta['id'],questao['id'],QUESTOES)
                resultado={'acerto':acerto,'correta':questao['correta'],'explicacao':questao['explicacao'],'densidadeConcluida':concluida,'estatisticaOriginal':None}
                if chave:
                    con.execute('INSERT INTO envios VALUES(?,?,?,?,?)',(conta['id'],chave,questao['id'],alternativa,json.dumps(resultado)))
                resultado['acompanhamento']={'densidade':ciclo(con,conta['id'],QUESTOES),'perfil':perfil(con,conta['id'],QUESTOES)}
                totais=con.execute('SELECT COUNT(*) total,COALESCE(SUM(acerto),0) acertos FROM respostas WHERE conta=?',(conta['id'],)).fetchone()
                resultado['progresso']=dict(totais)
                resultado['estudo']=estudo(con,conta['id'],QUESTOES)
                if chave: con.execute('UPDATE envios SET resultado=? WHERE conta=? AND chave=?',(json.dumps(resultado),conta['id'],chave))
                con.commit()
                return self.enviar(200,anexar_proxima(resultado,dados))
            raise Erro(404, 'Página não encontrada.')

if __name__ == '__main__':
    Servidor((os.environ.get('ESCUTA','0.0.0.0'), int(os.environ.get('PORTA', '8000'))), API).serve_forever()
