"""Imagens fixadas por sha256 e proxy Caddy com usuário próprio e raiz só leitura (achado U5 da revisão de 14/11/2026).

1. Todo FROM dos Dockerfiles e toda image do compose.yaml levam @sha256 (como a medição).
2. Sobe, num projeto separado (pu-teste-caddy, porta livre, aplicação falsa: tests/compose.teste-caddy.yaml), o proxy
   do compose.yaml; confere que ele responde pela porta, roda com o usuário 10002, raiz só leitura, e não grava fora
   de /config e /data. No fim derruba só esse projeto. Não toca nos contêineres do PU em execução (projeto enem).
Precisa do Docker (DOCKER_HOST=unix:///run/user/1000/docker.sock neste PC); sem Docker, a parte 2 é pulada.
Uso: DOCKER_HOST=unix:///run/user/1000/docker.sock python3 tests/caddy_endurecido.py
Dominique-Oliveira-Claude🤖🧡, 17/11/2026.
"""
import json
import re
import shutil
import socket
import subprocess
import time
import unittest
import urllib.request
from pathlib import Path
import os

RAIZ = Path(__file__).resolve().parents[1]
PROJETO = 'pu-teste-caddy'
SHA = re.compile(r'@sha256:[0-9a-f]{64}$')


def docker_disponivel():
    return shutil.which('docker') and subprocess.run(['docker', 'info'], capture_output=True).returncode == 0


class CaddyEndurecido(unittest.TestCase):
    def test_1_imagens_fixadas_por_sha256(self):
        froms = [(arquivo, linha.split()[1]) for arquivo in ('Dockerfile', 'ambiente/Dockerfile', 'conector/Dockerfile')
                 for linha in (RAIZ / arquivo).read_text().splitlines() if linha.startswith('FROM ')]
        imagens = [('compose.yaml', m) for m in re.findall(r'^\s+image:\s*(\S+)', (RAIZ / 'compose.yaml').read_text(), re.M)]
        self.assertEqual(len(froms), 3)
        self.assertTrue(any('caddy:2-alpine' in i for _, i in imagens), imagens)
        soltas = [f'{a}: {i}' for a, i in froms + imagens if not SHA.search(i)]
        self.assertEqual(soltas, [], 'imagem sem resumo sha256')

    @unittest.skipUnless(docker_disponivel(), 'sem Docker')
    def test_2_proxy_com_usuario_proprio_e_raiz_so_leitura(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            porta = s.getsockname()[1]
        compose = ['docker', 'compose', '-p', PROJETO, '-f', str(RAIZ / 'compose.yaml'), '-f', str(RAIZ / 'tests/compose.teste-caddy.yaml')]
        ambiente = {**os.environ, 'PU_TESTE_PORTA': str(porta)}
        try:
            subida = subprocess.run(compose + ['up', '-d', '--wait', 'proxy'], capture_output=True, text=True, env=ambiente, timeout=300)
            self.assertEqual(subida.returncode, 0, subida.stderr[-800:])
            for _ in range(50):
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{porta}/api/saude', timeout=2) as r:
                        corpo = r.read()
                    break
                except OSError:
                    time.sleep(.2)
            else:
                self.fail('proxy não respondeu')
            self.assertEqual(corpo, b'aplicacao falsa do teste')
            nome = subprocess.run(compose + ['ps', '-q', 'proxy'], capture_output=True, text=True, env=ambiente).stdout.strip()
            info = json.loads(subprocess.run(['docker', 'inspect', nome], capture_output=True, text=True).stdout)[0]
            self.assertEqual(info['Config']['User'], '10002:10002')
            self.assertTrue(info['HostConfig']['ReadonlyRootfs'], 'raiz gravável')
            self.assertTrue(info['Config']['Image'].startswith('caddy:2-alpine@sha256:'), info['Config']['Image'])
            dentro = lambda *cmd: subprocess.run(['docker', 'exec', nome, *cmd], capture_output=True, text=True)
            self.assertEqual(dentro('id', '-u').stdout.strip(), '10002')
            self.assertNotEqual(dentro('touch', '/etc/caddy/teste').returncode, 0, 'gravou em /etc/caddy')
            self.assertNotEqual(dentro('touch', '/teste').returncode, 0, 'gravou na raiz')
            self.assertEqual(dentro('touch', '/data/teste').returncode, 0, '/data precisa aceitar gravação')
        finally:
            subprocess.run(compose + ['down', '-v', '--remove-orphans'], capture_output=True, env=ambiente, timeout=120)


if __name__ == '__main__':
    unittest.main(verbosity=1)
