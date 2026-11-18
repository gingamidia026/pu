// Páginas públicas no Chrome sem janela (tests/cdp.mjs): todas as páginas de leitura geradas por paginas/gerar.py,
// servidas como o GitHub Pages serve (pasta → index.html). Confere em 320, 390, 768 e 1440 px: nenhuma rolagem lateral,
// nenhum erro de JavaScript nem violação da política de conteúdo, nenhum pedido a outro endereço, contraste AA de
// todo texto visível; a contagem e a busca com e sem JavaScript; o campo de busca com 44 px de altura.
// Uso: node tests/paginas-navegador.mjs [pasta-das-fotos]   (com pasta, grava a página inteira em 390 e 1440 px)
// Dominique-Oliveira-Claude🤖🧡, 17/11/2026.
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {abrirChrome, dormir} from './cdp.mjs';

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const FOTOS = process.argv[2] ? path.resolve(process.argv[2]) : null;
const TIPOS = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2', '.webmanifest': 'application/manifest+json', '.xml': 'application/xml', '.txt': 'text/plain'};

// Páginas de leitura, pelo conteúdo do gerador.
const paginas = fs.readdirSync(path.join(RAIZ, 'paginas/conteudo')).filter(n => n.endsWith('.json'))
  .map(n => JSON.parse(fs.readFileSync(path.join(RAIZ, 'paginas/conteudo', n), 'utf8'))).filter(p => p.tipo === 'leitura');

const servidor = http.createServer((pedido, resposta) => {
  const caminho = decodeURIComponent(new URL(pedido.url, 'http://x').pathname);
  const arquivo = path.join(RAIZ, caminho.endsWith('/') ? caminho + 'index.html' : caminho);
  if (!arquivo.startsWith(RAIZ + path.sep) || !fs.existsSync(arquivo) || fs.statSync(arquivo).isDirectory()) { resposta.writeHead(404); return resposta.end(); }
  resposta.writeHead(200, {'Content-Type': TIPOS[path.extname(arquivo)] || 'application/octet-stream'});
  resposta.end(fs.readFileSync(arquivo));
}).listen(0, '127.0.0.1');
await new Promise(ok => servidor.once('listening', ok));
const BASE = `http://127.0.0.1:${servidor.address().port}`;

let falhas = 0, feitos = 0;
const igual = (a, b, msg) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${msg}: ${JSON.stringify(a)} ≠ ${JSON.stringify(b)}`); };
const verdade = (v, msg) => { if (!v) throw new Error(msg); };
async function item(nome, f) {
  feitos++;
  try { await f(); console.log('OK     ' + nome); } catch (erro) { falhas++; console.log('FALHOU ' + nome + '\n       ' + erro.message); }
}

const chrome = await abrirChrome();
const p = await chrome.novaPagina({largura: 390, altura: 844});
const pedidos = [], violacoes = [];
p.aoEvento('Network.requestWillBeSent', m => pedidos.push(m.request.url));
p.aoEvento('Log.entryAdded', m => { if (/Content Security Policy/i.test(m.entry.text)) violacoes.push(m.entry.text); });

const CONTRASTE = `(() => { const cor = t => (t.match(/[\\d.]+/g) || []).map(Number);
  const lum = ([r, g, b]) => [r, g, b].map(c => { c /= 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }).reduce((s, c, i) => s + c * [0.2126, 0.7152, 0.0722][i], 0);
  const razao = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m); return Math.round((x + 0.05) / (y + 0.05) * 100) / 100; };
  const fundo = e => { for (let x = e; x; x = x.parentElement) { const v = cor(getComputedStyle(x).backgroundColor); if (v.length === 3 || v[3] > 0.5) return v.slice(0, 3); } return [255, 255, 255]; };
  return [...document.querySelectorAll('body *')].filter(e => e.getClientRects().length && !e.closest('.pular') && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()))
    .map(e => [e.tagName + '.' + e.className + ' "' + e.textContent.trim().slice(0, 24) + '"', razao(cor(getComputedStyle(e).color).slice(0, 3), fundo(e))]).filter(([, r]) => r < 4.5); })()`;

for (const pagina of paginas) {
  await item(`${pagina.endereco}: sem rolagem lateral, sem erro, nada de fora e contraste AA em 320, 390, 768 e 1440`, async () => {
    pedidos.length = 0; violacoes.length = 0; p.erros.length = 0;
    for (const largura of [320, 390, 768, 1440]) {
      await p.tamanho(largura, 900); await p.ir(BASE + pagina.endereco); await p.avaliar('document.fonts.ready.then(() => true)'); await dormir(100);
      verdade(await p.semRolagemLateral(), `rolagem lateral em ${largura}`);
      igual(await p.avaliar(CONTRASTE), [], `contraste AA em ${largura}`);
      // Nada passa da largura da janela, a não ser dentro da caixa de rolagem da tabela larga.
      const largos = await p.avaliar(`[...document.querySelectorAll('main *')].filter(e => !e.closest('.rolagem') && e.getBoundingClientRect().right > innerWidth + 1).map(e => e.tagName + '.' + e.className).slice(0, 5)`);
      igual(largos, [], `elemento passando da largura em ${largura}`);
    }
    igual(p.erros, [], 'erros no console');
    igual(violacoes, [], 'violação da política de conteúdo');
    igual(pedidos.filter(u => /^(https?|wss?):/.test(u) && !u.startsWith(BASE + '/')), [], 'pedido a outro endereço');
    const scripts = [...new Set(pedidos.filter(u => u.startsWith(BASE + '/') && /\.js(\?|$)/.test(u)).map(u => new URL(u).pathname))];
    const declarados = (Array.isArray(pagina.script) ? pagina.script : pagina.script ? [pagina.script] : []).map(s => s.startsWith('/') ? s : '/paginas/' + s);
    igual(scripts, declarados, 'só os scripts que a página declara');
  });
}

await item('calendário: contagem calculada no aparelho e, sem JavaScript, as datas por extenso', async () => {
  await p.tamanho(390, 844); await p.ir(BASE + '/calendario-vestibulares/');
  const saida = await p.texto('[data-contagem-saida]');
  verdade(/^(Faltam \d+ dias|Falta 1 dia|A próxima prova é hoje|As provas desta lista já passaram)/.test(saida), 'texto da contagem: ' + saida);
  // Relógio do aparelho em 2026-11-17: a próxima prova da lista é a 1ª fase da Unesp (22/11), em 5 dias.
  // Relógio do aparelho trocado antes do script da página (o protocolo injeta fora da política de conteúdo).
  const {identifier} = await p.s('Page.addScriptToEvaluateOnNewDocument', {source: `{ const Real = Date, fixo = Real.parse('2026-11-17T12:00:00-03:00');
    globalThis.Date = class extends Real { constructor(...a) { super(...(a.length ? a : [fixo])); } static now() { return fixo; } }; }`});
  await p.recarregar();
  igual(await p.texto('[data-contagem-saida]'), 'Faltam 5 dias para a 1ª fase da Unesp, em 22 de novembro de 2026.', 'contagem em 17/11/2026');
  igual(await p.avaliar(`document.querySelectorAll('.datas-de-prova .passou').length`), 4, 'Enem (2 dias), Fuvest e Unicamp 1ª fase já passaram');
  await p.s('Page.removeScriptToEvaluateOnNewDocument', {identifier});
  // Cada prova da lista, na véspera (singular) e no dia: artigo certo e nome da banca com a preposição certa.
  const esperado = {
    '2026-10-18': 'a 1ª fase da Unicamp', '2026-11-01': 'a 1ª fase da Fuvest', '2026-11-08': 'o 1º dia do Enem', '2026-11-15': 'o 2º dia do Enem',
    '2026-11-22': 'a 1ª fase da Unesp', '2026-11-29': 'o 1º dia da 2ª fase da Unicamp', '2026-11-30': 'o 2º dia da 2ª fase da Unicamp',
    '2026-12-06': 'o 1º dia da 2ª fase da Fuvest', '2026-12-07': 'o 2º dia da 2ª fase da Fuvest', '2026-12-10': 'a prova de Conhecimentos Gerais da Famerp',
    '2026-12-11': 'a prova de Conhecimentos Específicos e Redação da Famerp', '2026-12-13': 'a 2ª fase da Unesp'};
  igual(await p.avaliar(`[...document.querySelectorAll('.datas-de-prova li')].map(l => l.dataset.data)`), Object.keys(esperado), 'provas da lista');
  const MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
  for (const [data, nome] of Object.entries(esperado)) {
    const d = new Date(data + 'T12:00:00-03:00'), extenso = `${d.getUTCDate() === 1 ? '1º' : d.getUTCDate()} de ${MESES[d.getUTCMonth()]} de ${d.getUTCFullYear()}`;
    const vespera = new Date(d.getTime() - 864e5).toISOString().slice(0, 10);
    const casos = [[0, `A próxima prova é hoje: ${nome}.`]];
    if (!(vespera in esperado)) casos.unshift([1, `Falta 1 dia para ${nome}, em ${extenso}.`]);  // véspera com outra prova mostra a outra
    for (const [antes, frase] of casos) {
      const fixo = d.getTime() - antes * 864e5;
      const {identifier: id} = await p.s('Page.addScriptToEvaluateOnNewDocument', {source: `{ const Real = Date, fixo = ${fixo};
        globalThis.Date = class extends Real { constructor(...a) { super(...(a.length ? a : [fixo])); } static now() { return fixo; } }; }`});
      await p.recarregar();
      igual(await p.texto('[data-contagem-saida]'), frase, `contagem em ${new Date(fixo).toISOString().slice(0, 10)}`);
      await p.s('Page.removeScriptToEvaluateOnNewDocument', {identifier: id});
    }
  }
  await p.s('Emulation.setScriptExecutionDisabled', {value: true}); await p.recarregar();
  igual(await p.avaliar(`getComputedStyle(document.querySelector('[data-contagem-saida]')).display`), 'none', 'sem script, a frase vazia some');
  const datas = await p.avaliar(`[...document.querySelectorAll('.datas-de-prova time')].map(t => t.textContent)`);
  verdade(datas.length >= 10 && datas.every(d => /^(1º|\d{1,2}) de [a-zç]+ de \d{4}$/.test(d)), 'datas por extenso: ' + datas.join(' | '));
  verdade((await p.avaliar(`document.querySelectorAll('tr[data-aviso]').length`)) >= 8, 'avisos de data não encontrada visíveis');
  await p.s('Emulation.setScriptExecutionDisabled', {value: false});
});

for (const [endereco, procura, esperado] of [['/notas-de-corte/fuvest/', 'medicina', /Medicina/], ['/notas-de-corte/unicamp/', 'computacao', /Computação/]]) {
  await item(`${endereco}: busca por curso (sem acento), 44 px de toque e, sem JavaScript, a tabela inteira`, async () => {
    await p.tamanho(390, 844); await p.ir(BASE + endereco);
    const total = await p.avaliar(`document.querySelectorAll('#cortes tbody tr').length`);
    igual(await p.avaliar(`document.querySelector('[data-filtro]').hidden`), false, 'campo aparece com script');
    verdade((await p.avaliar(`document.querySelector('.filtro input').getBoundingClientRect().height`)) >= 44, 'campo com 44 px');
    await p.preencher('.filtro input', procura);
    const vistas = await p.avaliar(`[...document.querySelectorAll('#cortes tbody tr')].filter(l => !l.hidden).map(l => l.cells[0].textContent)`);
    verdade(vistas.length > 0 && vistas.length < total && vistas.every(n => esperado.test(n)), 'linhas filtradas: ' + vistas.join(' | '));
    verdade(/encontrada/.test(await p.texto('.filtro-total')), 'total anunciado');
    await p.preencher('.filtro input', 'zzzz');
    verdade(/Nenhum curso/.test(await p.texto('.filtro-total')), 'aviso de nenhum curso');
    await p.s('Emulation.setScriptExecutionDisabled', {value: true}); await p.recarregar();
    igual(await p.avaliar(`document.querySelector('[data-filtro]').hidden`), true, 'sem script, campo escondido');
    igual(await p.avaliar(`[...document.querySelectorAll('#cortes tbody tr')].filter(l => l.getClientRects().length).length`), total, 'sem script, todas as linhas');
    await p.s('Emulation.setScriptExecutionDisabled', {value: false});
  });
}

await item('obras: listas lado a lado no computador e uma embaixo da outra no celular', async () => {
  await p.tamanho(1440, 900); await p.ir(BASE + '/obras-obrigatorias/');
  const lado = await p.avaliar(`[...document.querySelectorAll('#ano-2027 .par-grade > div')].map(d => Math.round(d.getBoundingClientRect().top))`);
  igual(lado[0], lado[1], 'mesma altura no computador');
  await p.tamanho(390, 844); await dormir(100);
  const pilha = await p.avaliar(`[...document.querySelectorAll('#ano-2027 .par-grade > div')].map(d => { const r = d.getBoundingClientRect(); return {top: r.top, bottom: r.bottom}; })`);
  verdade(pilha[1].top >= pilha[0].bottom, 'uma embaixo da outra no celular');
});

await item('calculadora: média com os pesos, quanto falta, erro de campo, texto do estudante sem virar HTML e nada enviado', async () => {
  pedidos.length = 0;
  await p.tamanho(390, 844); await p.ir(BASE + '/calculadora-nota-enem/');
  await p.esperar('document.querySelector("#simular-nota")');
  igual(await p.avaliar(`document.querySelectorAll('h1').length`), 1, 'um h1 só (o da página)');
  igual(await p.avaliar(`!!document.querySelector('.sem-script')`), false, 'aviso sem script some quando a calculadora abre');
  // Exemplo do texto da página: 600, 650, 550, 700, 800 com pesos 1, 1, 2, 3, 1 dá 656,25; média simples 660.
  const notas = {linguagens: '600', humanas: '650', natureza: '550', matematica: '700', redacao: '800'};
  const pesos = {linguagens: '1', humanas: '1', natureza: '2', matematica: '3', redacao: '1'};
  for (const [id, v] of Object.entries(notas)) await p.preencher('#nota-' + id, v);
  for (const [id, v] of Object.entries(pesos)) await p.preencher('#peso-0-' + id, v);
  await p.preencher('#instituicao-0', '<img src=x onerror="window.invadiu=1">');
  await p.preencher('#corte-0', '700');
  await p.clicar('button[type=submit]');
  await p.esperar('document.querySelector(".resultado-opcao")');
  const r = await p.texto('#resultado-nota');
  verdade(r.includes('656,25') && r.includes('660,00'), 'média ponderada 656,25 e simples 660,00: ' + r.slice(0, 160));
  verdade(r.includes('Faltam 43,75 pontos'), 'falta 43,75 para 700');
  verdade(r.includes('não garante aprovação'), 'aviso de que não garante aprovação');
  igual(await p.avaliar(`[!!document.querySelector('#resultado-nota img'), window.invadiu || 0, document.querySelector('.resultado-opcao h3').textContent.includes('<img')]`), [false, 0, true], 'texto do estudante mostrado como texto');
  verdade(!/chance|aprovad[oa] com/i.test(await p.texto('main')), 'sem promessa de chance ou aprovação');
  verdade(await p.semRolagemLateral(), 'sem rolagem lateral com o resultado');
  igual(await p.avaliar(CONTRASTE), [], 'contraste AA com o resultado');
  if (FOTOS) {
    await p.captura(path.join(FOTOS, 'calculadora-resultado-390.png'));
    await p.tamanho(1440, 900); await dormir(150);
    verdade(await p.semRolagemLateral(), 'sem rolagem lateral com o resultado em 1440');
    await p.captura(path.join(FOTOS, 'calculadora-resultado-1440.png')); await p.tamanho(390, 844);
  }
  await p.preencher('#nota-redacao', '1200'); await p.clicar('button[type=submit]');
  verdade(/Redação/.test(await p.texto('#erro-nota')), 'erro de redação acima de 1.000');
  await p.clicar('#adicionar-opcao'); await p.esperar('document.querySelector("#instituicao-1")');
  igual(await p.avaliar(`document.querySelector('#nota-matematica').value`), '700', 'notas mantidas ao adicionar opção');
  igual(await p.avaliar(`document.querySelectorAll('h1').length`), 1, 'continua com um h1 depois de redesenhar');
  igual(pedidos.filter(u => /^(https?|wss?):/.test(u) && !(u.startsWith(BASE + '/') && /\.(js|css|woff2|png|svg|webmanifest)(\?|$)/.test(u)) && !u.endsWith('/calculadora-nota-enem/')), [], 'nenhum pedido além dos arquivos da página');
  await p.s('Emulation.setScriptExecutionDisabled', {value: true}); await p.recarregar();
  verdade(/JavaScript/.test(await p.texto('.sem-script')), 'sem script, a conta por extenso');
  await p.s('Emulation.setScriptExecutionDisabled', {value: false});
});

await item('acertos e nota: quatro tabelas com rolagem só dentro da caixa, 1ª coluna fixa e sem script', async () => {
  await p.tamanho(390, 844); await p.ir(BASE + '/acertos-e-nota-enem/');
  igual(await p.avaliar(`['linguagens', 'humanas', 'natureza', 'matematica'].map(id => document.querySelectorAll('#' + id + ' tbody tr').length)`), [46, 46, 44, 45], 'linhas de 0 ao máximo de acertos');
  igual(await p.avaliar(`[...document.querySelectorAll('.rolagem')].every(c => c.scrollWidth > c.clientWidth)`), true, 'tabela larga rola dentro da caixa no celular');
  verdade(await p.semRolagemLateral(), 'a página não rola para o lado');
  const fixa = await p.avaliar(`(() => { const caixa = document.querySelector('#matematica .rolagem'); const celula = caixa.querySelector('tbody td'); const antes = celula.getBoundingClientRect().left; caixa.scrollLeft = 300; return [antes, celula.getBoundingClientRect().left]; })()`);
  igual(fixa[0], fixa[1], '1ª coluna fica no lugar ao rolar a tabela');
  igual(await p.avaliar(`document.querySelectorAll('script[src]').length`), 0, 'página sem script');
});

if (FOTOS) {
  fs.mkdirSync(FOTOS, {recursive: true});
  for (const pagina of paginas) {
    for (const largura of [390, 1440]) {
      await p.tamanho(largura, largura < 800 ? 844 : 900); await p.ir(BASE + pagina.endereco); await p.avaliar('document.fonts.ready.then(() => true)'); await dormir(150);
      const nome = pagina.endereco.replace(/^\/|\/$/g, '').replace(/\//g, '-') + `-${largura}.png`;
      await p.captura(path.join(FOTOS, nome));
    }
  }
  console.log('Fotos em ' + FOTOS);
}

await chrome.fechar(); servidor.close();
console.log(`\n${feitos - falhas} de ${feitos} itens passaram.`);
process.exit(falhas ? 1 : 0);
