#!/usr/bin/env python3
"""Mede a fluidez do servidor com um catálogo inteiro, sem tocar na produção.

Uso: python3 tests/medir_fluidez.py <pasta do catálogo com atual.json e imagens/> [--repeticoes N]

Sobe o servidor com banco temporário, cria uma conta sintética e mede: tempo de subida
(até /api/saude responder), memória residente depois do primeiro painel, tamanho e tempo
de /api/painel e de /api/questoes/<id> (questão sem figura, com figura e de conjunto).
Imprime um JSON. Dominique-Oliveira-Claude🤖🧡, 14/11/2026.
"""
import argparse
import http.cookiejar
import json
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def memoria_kb(pid):
    for linha in Path(f'/proc/{pid}/status').read_text().splitlines():
        if linha.startswith('VmRSS:'):
            return int(linha.split()[1])
    return None


def medir(pasta, repeticoes):
    catalogo = Path(pasta) / 'atual.json'
    dados = json.loads(catalogo.read_text())
    questoes = dados['questoes']
    with tempfile.TemporaryDirectory() as tmp, socket.socket() as s:
        s.bind(('127.0.0.1', 0)); porta = s.getsockname()[1]; s.close()
        origem = f'http://127.0.0.1:{porta}'
        inicio = time.perf_counter()
        proc = subprocess.Popen([sys.executable, str(RAIZ / 'app/servidor.py')], stdout=subprocess.DEVNULL,
                                env={**os.environ, 'DADOS': tmp, 'CATALOGO': str(catalogo), 'PORTA': str(porta),
                                     'ESCUTA': '127.0.0.1', 'ORIGEM': origem, 'PERFIL_TESTE': '0', 'AMBIENTES_INDIVIDUAIS': '0'})
        try:
            for _ in range(400):
                try:
                    urllib.request.urlopen(origem + '/api/saude', timeout=1).close(); break
                except OSError:
                    time.sleep(.025)
            subida = time.perf_counter() - inicio
            cliente = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

            def pedido(caminho, corpo=None):
                req = urllib.request.Request(origem + caminho, data=None if corpo is None else json.dumps(corpo).encode(),
                                             headers={'Origin': origem, 'Content-Type': 'application/json'})
                t = time.perf_counter()
                with cliente.open(req) as r:
                    bruto = r.read()
                return time.perf_counter() - t, bruto

            pedido('/api/cadastro', {'nome': 'Medida', 'email': 'medida@example.com', 'senha': 'Senha longa de medida 123!'})

            def serie(caminho):
                tempos, tamanho = [], 0
                for _ in range(repeticoes):
                    t, bruto = pedido(caminho); tempos.append(t); tamanho = len(bruto)
                return {'bytes': tamanho, 'ms_mediana': round(statistics.median(tempos) * 1000, 1),
                        'ms_max': round(max(tempos) * 1000, 1)}

            resultado = {'questoes': len(questoes), 'subida_s': round(subida, 3)}
            resultado['painel'] = serie('/api/painel')
            resultado['memoria_mb'] = round(memoria_kb(proc.pid) / 1024, 1)
            amostras = {
                'sem_figura': next((q for q in questoes if not q.get('imagens') and not q.get('grupo')), None),
                'com_figura': next((q for q in questoes if q.get('imagens') and not q.get('grupo')), None),
                'conjunto': next((q for q in questoes if q.get('grupo')), None),
            }
            resultado['questao'] = {k: dict(serie(f"/api/questoes/{q['id']}"), id=q['id']) for k, q in amostras.items() if q}
            # A maior resposta possível de questão: a de enunciado e conjunto mais longos.
            maior = max(questoes, key=lambda q: len(json.dumps(q, ensure_ascii=False)) + (5000 if q.get('grupo') else 0))
            resultado['questao']['maior'] = dict(serie(f"/api/questoes/{maior['id']}"), id=maior['id'])
            return resultado
        finally:
            proc.terminate(); proc.wait()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('pasta'); p.add_argument('--repeticoes', type=int, default=15)
    a = p.parse_args()
    print(json.dumps(medir(a.pasta, a.repeticoes), ensure_ascii=False, indent=1))
