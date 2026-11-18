// Proteção contra enquadramento (achado N5): o PU aberto num quadro de outro site some e o app.js não roda;
// num quadro da mesma origem (moldura de conferência) continua visível. O GitHub Pages não manda cabeçalho contra
// quadro, então a defesa é a checagem no início do app/public/app.js.
// Dois servidores locais em portas diferentes = duas origens (o "outro site" e o PU). Chrome sem janela (tests/cdp.mjs).
// Uso: node tests/enquadramento-navegador.mjs
// Dominique-Oliveira-Claude🤖🧡, 17/11/2026.
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {abrirChrome, dormir} from './cdp.mjs';

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const TIPOS = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2', '.webmanifest': 'application/manifest+json'};

const ouvir = tratar => new Promise(ok => { const s = http.createServer(tratar).listen(0, '127.0.0.1', () => ok(s)); });
// O PU como o GitHub Pages serve (pasta → index.html), sem cabeçalho de quadro; /moldura.html é a moldura da mesma origem.
const pu = await ouvir((pedido, resposta) => {
  const caminho = decodeURIComponent(new URL(pedido.url, 'http://x').pathname);
  if (caminho === '/moldura.html') { resposta.writeHead(200, {'Content-Type': TIPOS['.html']}); return resposta.end('<!doctype html><iframe id="q" src="/" style="width:390px;height:620px"></iframe>'); }
  const arquivo = path.join(RAIZ, caminho.endsWith('/') ? caminho + 'index.html' : caminho);
  if (!arquivo.startsWith(RAIZ + path.sep) || !fs.existsSync(arquivo) || fs.statSync(arquivo).isDirectory()) { resposta.writeHead(404); return resposta.end(); }
  resposta.writeHead(200, {'Content-Type': TIPOS[path.extname(arquivo)] || 'application/octet-stream'});
  resposta.end(fs.readFileSync(arquivo));
});
const BASE = `http://127.0.0.1:${pu.address().port}`;
const outro = await ouvir((pedido, resposta) => {
  resposta.writeHead(200, {'Content-Type': TIPOS['.html']});
  resposta.end(`<!doctype html><p>Outro site</p><iframe id="q" src="${BASE}/" style="width:390px;height:620px"></iframe>`);
});
const OUTRO = `http://127.0.0.1:${outro.address().port}`;

let falhas = 0;
const verdade = (v, msg) => { if (!v) throw new Error(msg); };
async function item(nome, f) {
  try { await f(); console.log('OK     ' + nome); } catch (erro) { falhas++; console.log('FALHOU ' + nome + '\n       ' + erro.message); }
}

const chrome = await abrirChrome();
const p = await chrome.novaPagina({largura: 1024, altura: 800, celular: false});

// Avalia dentro do quadro (mesmo site, outra porta: o Chrome mantém no mesmo processo, então o quadro aparece na árvore).
async function noQuadro(expressao) {
  const {frameTree} = await p.s('Page.getFrameTree');
  const filho = (frameTree.childFrames || [])[0];
  if (!filho) return {semQuadro: true};
  const {executionContextId} = await p.s('Page.createIsolatedWorld', {frameId: filho.frame.id, worldName: 'teste-quadro'});
  const r = await p.s('Runtime.evaluate', {expression: expressao, contextId: executionContextId, returnByValue: true});
  return {valor: r.result.value, endereco: filho.frame.url};
}
async function esperarQuadroCarregado() {
  for (let i = 0; i < 80; i++) { const r = await noQuadro('document.readyState'); if (r.valor === 'complete') return; await dormir(100); }
  throw new Error('quadro não carregou');
}

await item('quadro de outro site: o PU some (ou sai do quadro) e o app.js para no começo', async () => {
  await p.ir(OUTRO + '/');
  await esperarQuadroCarregado(); await dormir(400);
  const topo = await p.avaliar('location.href');
  if (topo.startsWith(BASE)) return;  // o navegador deixou o PU tomar a janela inteira: também resolve
  const r = await noQuadro(`JSON.stringify({display: getComputedStyle(document.documentElement).display, entrou: !!document.querySelector('#conteudo') && document.querySelector('#conteudo').getBoundingClientRect().height > 0})`);
  const lido = JSON.parse(r.valor);
  verdade(lido.display === 'none', 'PU visível dentro do quadro de outro site: ' + r.valor);
});

await item('quadro da mesma origem (moldura de conferência): o PU continua visível', async () => {
  await p.ir(BASE + '/moldura.html');
  await esperarQuadroCarregado(); await dormir(400);
  const r = await noQuadro(`getComputedStyle(document.documentElement).display`);
  verdade(r.valor && r.valor !== 'none', 'moldura da mesma origem escondeu o PU: ' + JSON.stringify(r));
  verdade((await p.avaliar('location.href')) === BASE + '/moldura.html', 'a moldura não deve ser trocada');
});

await item('fora de quadro: a entrada abre normalmente', async () => {
  await p.ir(BASE + '/');
  verdade((await p.avaliar('getComputedStyle(document.documentElement).display')) !== 'none', 'entrada escondida fora de quadro');
});

await chrome.fechar(); pu.close(); outro.close();
console.log(falhas ? `\n${falhas} item(ns) falharam.` : '\n3 de 3 itens passaram.');
process.exit(falhas ? 1 : 0);
