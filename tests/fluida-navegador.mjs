// Teste de navegador da plataforma fluida do PU, sem gastar tokens e sem tocar no banco real.
// Sobe o servidor com banco e catálogo temporários, abre o Chrome sem janela e percorre os fluxos de estudo.
// Uso: node tests/fluida-navegador.mjs [pasta-de-capturas]. Saída: uma linha "OK" ou "FALHA" por item.
// Dominique-Oliveira-Claude🤖🧡, 12/11/2026.
import {spawn, spawnSync} from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import zlib from 'node:zlib';
import {abrirChrome, dormir} from './cdp.mjs';

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const CAPTURAS = process.argv[2] || '';
const pasta = fs.mkdtempSync(path.join(os.tmpdir(), 'pu-fluida-'));
const portaLivre = () => new Promise(ok => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const {port} = s.address(); s.close(() => ok(port)); }); });

// ---------- Catálogo sintético: quatro matérias, uma figura, um conjunto e texto quebrado como no PDF ----------
function png(largura, altura) {
  const crc = dados => { let c = ~0; for (const b of dados) { c ^= b; for (let k = 0; k < 8; k++) c = c & 1 ? (c >>> 1) ^ 0xEDB88320 : c >>> 1; } return ~c >>> 0; };
  const bloco = (tipo, dados) => { const corpo = Buffer.concat([Buffer.from(tipo), dados]); const tamanho = Buffer.alloc(4); tamanho.writeUInt32BE(dados.length); const soma = Buffer.alloc(4); soma.writeUInt32BE(crc(corpo)); return Buffer.concat([tamanho, corpo, soma]); };
  const cabecalho = Buffer.alloc(13); cabecalho.writeUInt32BE(largura, 0); cabecalho.writeUInt32BE(altura, 4); cabecalho[8] = 8; cabecalho[9] = 2;
  const linhas = Buffer.alloc((largura * 3 + 1) * altura, 0x99);
  for (let y = 0; y < altura; y++) linhas[y * (largura * 3 + 1)] = 0;
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), bloco('IHDR', cabecalho), bloco('IDAT', zlib.deflateSync(linhas)), bloco('IEND', Buffer.alloc(0))]);
}
const figura = png(120, 60); const hashFigura = crypto.createHash('sha256').update(figura).digest('hex');
fs.mkdirSync(path.join(pasta, 'catalogo/imagens'), {recursive: true});
fs.writeFileSync(path.join(pasta, 'catalogo/imagens', hashFigura + '.png'), figura);
const MATERIAS = [['Português', 'Linguagens'], ['Matemática', 'Matemática'], ['Física', 'Ciências da Natureza'], ['História', 'Ciências Humanas']];
const PLACEBO = 'Gabarito registrado no cofre a partir do caderno oficial. Ainda não há solução comentada para esta questão.';
const questoes = [];
for (let id = 1; id <= 24; id++) {
  const [materia, area] = MATERIAS[id % 4];
  questoes.push({id, chave: 'teste:' + id, area, materia, topico: `Assunto ${id % 2 ? 'ímpar' : 'par'} de ${materia}`, titulo: `Enem 2099 · Questão ${String(id).padStart(2, '0')}`, ano: 2099, numero: id, oficial: true, extrator: 2,
    enunciado: `Enunciado curto da questão ${id}.`, alternativas: ['alternativa um', 'alternativa dois', 'alternativa três', 'alternativa quatro', 'alternativa cinco'], correta: id % 5, explicacao: PLACEBO, imagens: [], textoParcial: false, textoComum: '', grupo: '', fonte: 'https://example.com/prova.pdf'});
}
const q = id => questoes.find(x => x.id === id);
q(2).explicacao = 'Explicação comentada da questão 2.';
q(5).enunciado = 'Observe a figura.\n[[midia:0]]\nO que a figura mostra?'; q(5).imagens = [{hash: hashFigura, tipo: 'image/png', partes: 1}];
q(7).enunciado = 'Texto longo copiado do caderno da prova, com linhas quebradas\npela coluna do PDF, que precisam voltar a ser um parágrafo só\nquando aparecem na tela do celular de quem estuda.\nSOBRENOME, N. Obra de teste. São Paulo: Editora, 2020.\nQual é o comando desta questão?';
for (const id of [21, 22]) Object.assign(q(id), {grupo: 'grupo-teste', grupoIds: [21, 22], textoComum: 'Texto comum às duas perguntas do conjunto.', materia: 'História', area: 'Ciências Humanas', topico: 'Conjunto de História'});
fs.writeFileSync(path.join(pasta, 'catalogo/atual.json'), JSON.stringify({formato: 1, questoes, anuladas: 0, revisar: 0, versao: 'fluida'}));

// ---------- Servidor do PU e servidor estático da entrada pública ----------
const porta = await portaLivre(); const portaPublica = await portaLivre();
const URL_LOCAL = `http://127.0.0.1:${porta}`; const URL_PUBLICA = `http://127.0.0.1:${portaPublica}`;
fs.mkdirSync(path.join(pasta, 'dados'));
const servidor = spawn('python3', [path.join(RAIZ, 'app/servidor.py')], {stdio: 'ignore', env: {...process.env, DADOS: path.join(pasta, 'dados'), CATALOGO: path.join(pasta, 'catalogo/atual.json'), PORTA: String(porta), ESCUTA: '127.0.0.1', ORIGEM: URL_LOCAL, PERFIL_TESTE: '0', AMBIENTES_INDIVIDUAIS: '0'}});
const INTERMEDIARIO = 'https://intermediario.teste';
const estatico = http.createServer((pedido, resposta) => {
  const caminho = decodeURIComponent(new URL(pedido.url, URL_PUBLICA).pathname);
  if (caminho === '/configuracao-publica.js') { resposta.writeHead(200, {'Content-Type': 'text/javascript'}); return resposta.end(`window.ENEM_PUBLICO = Object.freeze({habilitado: true, intermediario: '${INTERMEDIARIO}'});`); }
  const arquivo = path.join(RAIZ, caminho === '/' ? 'index.html' : caminho);
  if (!arquivo.startsWith(RAIZ) || !/^\/(index\.html)?$|^\/app\/public\/(?:(?:fontes|ilustracoes)\/)?[a-z0-9][a-z0-9-]*(?:\.[a-z0-9]+)+$|^\/manifest\.webmanifest$|^\/icones\/[a-z0-9.-]+$/.test(caminho) || !fs.existsSync(arquivo)) { resposta.writeHead(404); return resposta.end(); }
  resposta.writeHead(200, {'Content-Type': {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.webp': 'image/webp', '.woff2': 'font/woff2', '.webmanifest': 'application/manifest+json'}[path.extname(arquivo)]});
  // A política de conteúdo da entrada pública aponta para o intermediário real; no teste, para o simulado.
  resposta.end(caminho === '/' ? fs.readFileSync(arquivo, 'utf8').replace('https://enem-ginga-conexao.sabrinaconradoadv.chatgpt.site', INTERMEDIARIO) : fs.readFileSync(arquivo));
}).listen(portaPublica, '127.0.0.1');
for (let i = 0; i < 100; i++) { try { await fetch(URL_LOCAL + '/api/saude'); break; } catch { await dormir(50); } }

const sql = comando => { const r = spawnSync('python3', ['-c', `import sqlite3,sys,json\nc=sqlite3.connect(sys.argv[1])\nr=c.execute(sys.argv[2]).fetchall()\nc.commit()\nprint(json.dumps(r))`, path.join(pasta, 'dados/estudos.sqlite3'), comando], {encoding: 'utf8'}); if (r.status) throw new Error(r.stderr); return JSON.parse(r.stdout); };

// ---------- Roteiro ----------
const resultados = [];
const chrome = await abrirChrome();
let p = await chrome.novaPagina({largura: 390, altura: 844});
// O tema automático depende da hora. Os itens que conferem as cores do diurno rodam num fuso em que agora é dia (das 9h às 15h).
const FUSO_DE_DIA = Intl.supportedValuesOf('timeZone').find(f => { const h = Number(new Intl.DateTimeFormat('en-US', {timeZone: f, hour: 'numeric', hourCycle: 'h23'}).format(new Date())) % 24; return h >= 9 && h < 15; });
await p.s('Emulation.setTimezoneOverride', {timezoneId: FUSO_DE_DIA});
async function item(nome, passos) {
  try { await passos(); resultados.push([nome, true]); console.log('OK     ' + nome); }
  catch (e) { resultados.push([nome, false]); console.log('FALHA  ' + nome + ' :: ' + e.message.split('\n')[0]); if (CAPTURAS) await p.captura(path.join(CAPTURAS, 'falha-' + nome.replace(/[^a-z0-9]+/gi, '-').slice(0, 50) + '.png')).catch(() => {}); }
}
const igual = (obtido, esperado, nome) => { if (JSON.stringify(obtido) !== JSON.stringify(esperado)) throw new Error(`${nome}: esperado ${JSON.stringify(esperado)}, veio ${JSON.stringify(obtido)}`); };
const certo = (condicao, nome) => { if (!condicao) throw new Error(nome); };
const trocou = '(id => { const e = document.querySelector(".questao:not(.esqueleto)"); return Boolean(e) && Number(e.dataset.id) !== id; })';
const idAtual = () => p.avaliar('Number(document.querySelector(".questao")?.dataset.id || 0)');
const questaoPronta = () => p.esperar('document.querySelector(".questao:not(.esqueleto) #conferir, .questao:not(.esqueleto) #proxima")', 8000, 'questão pronta');
const marcar = (id, alternativa) => p.clicar(`input[name="alternativa-${id}"][value="${alternativa}"]`);
const errada = id => (q(id).correta + 1) % 5;
const hoje = async () => (await p.texto('.ritmo-hoje strong')).trim();
async function responder({acertar = true, chute = false} = {}) {
  await questaoPronta(); const id = await idAtual(); const ids = q(id).grupo ? q(id).grupoIds : [id];
  for (const cada of ids) await marcar(cada, acertar ? q(cada).correta : errada(cada));
  await p.clicar(chute ? '#chutei' : '#conferir');
  await p.esperar('document.querySelector("#proxima, #ver-resposta")');
  if (await p.existe('#ver-resposta')) await p.clicar('#ver-resposta');
  await p.esperar('document.querySelector("#proxima")');
  return id;
}
// Abre uma questão escolhida pelo teste, mesmo que a conta já a tenha respondido.
const abrir = async id => { await p.avaliar(`(() => { estado.primeira = ${id}; estado.puladas.clear(); estado.feitasSessao.delete(${id}); if (!painel.densidade.pendentes.includes(${id})) painel.densidade.pendentes.unshift(${id}); prefs.alvo.valor = 999; verEstudo(); })()`); await p.esperar(`Number(document.querySelector(".questao:not(.esqueleto)")?.dataset.id) === ${id}`, 8000, 'abrir a questão ' + id); };
const seguinte = async () => { const antes = await idAtual(); await p.clicar('#proxima'); await p.esperar(`document.querySelector(".marco") || (document.querySelector(".questao:not(.esqueleto)") && Number(document.querySelector(".questao").dataset.id) !== ${antes})`, 8000, 'próxima questão ou marco'); };
async function cadastrar(nome) {
  await p.ir(URL_LOCAL); await p.esperar('document.querySelector("#acesso")');
  await p.clicar('#trocar'); await p.preencher('#nome', nome); await p.preencher('#email', nome.toLowerCase().replace(/\W+/g, '') + '@example.com'); await p.preencher('#senha', 'Senha longa de teste 123!');
  await p.clicar('#acesso button[type=submit]'); await questaoPronta();
}

await item('entrada explica o PU antes do cadastro e deixa experimentar uma questão', async () => {
  await p.ir(URL_LOCAL); await p.esperar('document.querySelector("#acesso")');
  certo((await p.texto('.apresentacao')).includes('uma questão por vez'), 'apresentação');
  igual(await p.avaliar('document.querySelector("#menu").hidden'), true, 'menu escondido sem sessão');
  await p.clicar('#demonstracao input[value="0"]');
  certo((await p.texto('#retorno-demonstracao')).includes('A certa é a D'), 'correção da demonstração');
  igual(await p.avaliar('document.querySelector("#demonstracao .alternativa:nth-of-type(4)").dataset.correcao'), 'correta', 'alternativa certa marcada');
  await p.clicar('#quero-conta'); await p.esperar('document.querySelector("#nome")');
  if (CAPTURAS) await p.captura(path.join(CAPTURAS, 'entrada-390.png'));
});
await item('entrada sem rolagem lateral em 320, 360, 390, 412, 768 e 1280', async () => {
  for (const largura of [320, 360, 412, 768, 1280, 390]) { await p.tamanho(largura, 844); await dormir(120); certo(await p.semRolagemLateral(), 'rolagem lateral em ' + largura); }
});
// Nome acessível calculado pelo próprio Chrome (árvore de acessibilidade), para provar que o rótulo que vira não duplica.
const nomeAcessivel = async seletor => {
  const {root} = await p.s('DOM.getDocument', {depth: 0}); const {nodeId} = await p.s('DOM.querySelector', {nodeId: root.nodeId, selector: seletor});
  const {nodes} = await p.s('Accessibility.getPartialAXTree', {nodeId, fetchRelatives: false}); return nodes[0]?.name?.value ?? null;
};
await item('entrada nova: faixa que corre, selos fora da leitura e botão principal com um nome só', async () => {
  await p.tamanho(390, 844); await p.clicar('#trocar'); await p.esperar('document.querySelector("#acesso") && !document.querySelector("#nome")');
  igual(await p.avaliar('document.querySelectorAll(".faixa-corre").length'), 1, 'uma faixa que corre');
  igual(await p.avaliar('getComputedStyle(document.querySelector(".trilho")).animationName'), 'correr-faixa', 'faixa correndo');
  const velocidade = await p.avaliar('document.querySelector(".frases").offsetWidth / parseFloat(getComputedStyle(document.querySelector(".trilho")).animationDuration)');
  certo(velocidade > 30 && velocidade < 50, 'cerca de 40 px/s, veio ' + velocidade);
  igual(await p.avaliar('[...document.querySelectorAll(".frases")].map(l => l.getAttribute("aria-hidden"))'), [null, 'true'], 'cópia da faixa fora da leitura de tela');
  igual(await p.avaliar('getComputedStyle(document.querySelector(".faixa-corre")).overflowX'), 'clip', 'faixa recortada');
  const selos = await p.avaliar('[...document.querySelectorAll(".selos-cartaz")].map(s => ({oculto: s.getAttribute("aria-hidden"), desenhos: s.querySelectorAll("svg").length, noTitulo: Boolean(s.closest("h1"))}))');
  igual(selos, [{oculto: 'true', desenhos: 3, noTitulo: true}], 'selos encostados no título e fora da leitura');
  igual(await nomeAcessivel('.apresentacao h1'), 'Estude para o Enem uma questão por vez.', 'título sem os selos no nome');
  const botao = '#acesso button[type=submit]';
  igual(await p.avaliar(`[...document.querySelector("${botao}").querySelectorAll(".vira-a, .vira-b")].map(e => e.className + ":" + e.getAttribute("aria-hidden"))`), ['vira-a:null', 'vira-b:true'], 'rótulo duplicado com aria-hidden na cópia');
  igual(await nomeAcessivel(botao), 'Entrar', 'nome acessível único'); igual((await p.texto(botao)).trim(), 'Entrar', 'innerText único');
  igual(await p.avaliar('[...document.querySelectorAll("#menu a")].every(a => a.querySelector(".vira-b[aria-hidden=true]"))'), true, 'menu com o rótulo que vira');
  for (const largura of [320, 360, 390, 412, 768, 1280]) { await p.tamanho(largura, 844); await dormir(120); certo(await p.semRolagemLateral(), 'rolagem lateral na entrada nova em ' + largura); }
  // Com ponteiro fino, passar sobre o botão troca o rótulo; o nome acessível continua um só.
  if (await p.avaliar('matchMedia("(hover:hover) and (pointer:fine)").matches')) {
    const centro = await p.avaliar(`(() => { const e = document.querySelector("${botao}"); e.scrollIntoView({block: "center"}); const r = e.getBoundingClientRect(); return {x: r.x + r.width / 2, y: r.y + r.height / 2}; })()`);
    await p.s('Input.dispatchMouseEvent', {type: 'mouseMoved', x: centro.x, y: centro.y}); await dormir(900);
    igual(await p.avaliar(`getComputedStyle(document.querySelector("${botao} .vira-b")).visibility`), 'visible', 'cópia aparece no passar do ponteiro');
    igual(await nomeAcessivel(botao), 'Entrar', 'nome único com o rótulo virado');
    await p.s('Input.dispatchMouseEvent', {type: 'mouseMoved', x: 1, y: 1});
  }
  // Foco pelo teclado também vira o rótulo (o Chrome sem janela não tem ponteiro fino).
  await p.tecla('x'); await p.avaliar(`document.querySelector("${botao}").focus()`); await dormir(900);
  igual(await p.avaliar(`[getComputedStyle(document.querySelector("${botao} .vira-b")).visibility, getComputedStyle(document.querySelector("${botao} .vira-a")).opacity]`), ['visible', '0'], 'rótulo virado no foco pelo teclado');
  igual(await nomeAcessivel(botao), 'Entrar', 'nome único com o rótulo virado'); igual((await p.texto(botao)).trim().startsWith('Entrar'), true, 'texto do botão');
  await p.avaliar('document.activeElement.blur()');
  await p.s('Emulation.setEmulatedMedia', {features: [{name: 'prefers-reduced-motion', value: 'reduce'}]});
  try {
    await dormir(100);
    igual(await p.avaliar('getComputedStyle(document.querySelector(".trilho")).animationName'), 'none', 'faixa parada com movimento reduzido');
    igual(await p.avaliar('getComputedStyle(document.querySelector(".trilho")).transform'), 'none', 'faixa no início');
    igual(await p.avaliar('[...new Set([...document.querySelectorAll(".entrada > *, .entrada *")].map(e => getComputedStyle(e).animationName))]'), ['none'], 'entrada sem animação, inclusive a boia e o livro da cena');
  } finally { await p.s('Emulation.setEmulatedMedia', {features: []}); }
  await p.tamanho(390, 844); await dormir(100);
});
// Página de entrada de 14/11/2026: texto no HTML, seções na ordem do plano de páginas, provas de um lugar só, endereços do formulário,
// duas fontes, contraste AA, formulário limpo e cabeçalho de compartilhamento igual nos dois index.html.
const SECOES_ENTRADA = ['apresentacao', 'experimente', 'como-funciona', 'o-que-voce-ganha', 'provas', 'por-que', 'perguntas', 'entrar'];
await item('entrada de 14/11: texto da apresentação no HTML, seções na ordem, provas no ar de um lugar só, duas fontes e contraste AA', async () => {
  const bloco = arquivo => { const t = fs.readFileSync(path.join(RAIZ, arquivo), 'utf8'); const i = t.indexOf('<!-- entrada:inicio'), f = t.indexOf('<!-- entrada:fim -->'); certo(i > 0 && f > i, 'bloco da entrada em ' + arquivo); return t.slice(i, f); };
  const [raiz, aplicacao] = ['index.html', 'app/public/index.html'].map(bloco);
  igual(raiz, aplicacao, 'mesmo bloco nos dois index.html');
  certo(raiz.includes('<div class="entrada" data-estatica>'), 'bloco marcado como molde');
  for (const id of SECOES_ENTRADA) certo(raiz.includes(`id="${id}"`), 'seção no HTML: ' + id);
  const fonteApp = fs.readFileSync(path.join(RAIZ, 'app/public/app.js'), 'utf8');
  for (const trecho of ['Como funciona', 'O que você ganha', 'Perguntas frequentes', 'Por que estudar assim', 'Quanto custa?']) { certo(raiz.includes(trecho), 'texto no HTML: ' + trecho); certo(!fonteApp.includes(trecho), 'texto só no HTML, fora do app.js: ' + trecho); }
  const cabeca = arquivo => { const t = fs.readFileSync(path.join(RAIZ, arquivo), 'utf8'); return [(t.match(/<title>[^<]+<\/title>/) || [''])[0]].concat(['name="description"', 'rel="canonical"', 'og:title', 'og:description', 'og:image"', 'og:url', 'twitter:card'].map(c => (t.match(new RegExp('<[^>]*' + c.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '[^>]*>')) || [''])[0])); };
  const [c1, c2] = ['index.html', 'app/public/index.html'].map(cabeca);
  certo(c1.every(Boolean), 'título, descrição e compartilhamento: ' + JSON.stringify(c1)); igual(c1, c2, 'cabeçalho igual nos dois index.html');
  // Sem JavaScript o molde fica escondido: quem tem sessão guardada não vê a apresentação antes da questão.
  await p.s('Emulation.setScriptExecutionDisabled', {value: true});
  try { await p.ir(URL_LOCAL); igual(await p.avaliar('getComputedStyle(document.querySelector(".entrada[data-estatica]")).display'), 'none', 'molde escondido até o app.js decidir'); }
  finally { await p.s('Emulation.setScriptExecutionDisabled', {value: false}); }
  await p.tamanho(390, 844); await p.ir(URL_LOCAL); await p.esperar('document.querySelector("#acesso")'); await p.avaliar('document.fonts.ready');
  igual(await p.avaliar('[...document.querySelectorAll(".entrada section[id]")].map(s => s.id)'), SECOES_ENTRADA, 'seções na ordem do plano de páginas');
  igual(await p.avaliar('document.querySelectorAll(".entrada[data-estatica], [data-lugar=faixa-que-corre]").length'), 0, 'molde trocado pela página desenhada');
  const provas = await p.avaliar(`({lista: PROVAS_NO_AR.map(x => x.prova + ' ' + x.edicao), total: PROVAS_NO_AR.reduce((s, x) => s + x.questoes, 0),
    itens: [...document.querySelectorAll('.provas-lista li strong')].map(e => e.textContent), numero: document.querySelector('.numero-cartaz strong').textContent,
    outras: (document.querySelector('.entrada').innerText.match(/Fuvest|USP|Unesp|Unicamp|Famerp/g) || [])})`);
  igual(provas.itens, provas.lista, 'provas desenhadas a partir de PROVAS_NO_AR'); igual(provas.numero, provas.total.toLocaleString('pt-BR'), 'total do banco');
  igual(provas.lista, ['Enem 2024', 'Enem 2025'], 'no ar hoje só o Enem 2024 e o 2025'); igual(provas.outras, [], 'nenhuma prova prometida antes de entrar no banco');
  const fontes = await p.avaliar(`({usadas: [...new Set([...document.querySelectorAll('body *')].filter(e => e.getClientRects().length && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())).map(e => getComputedStyle(e).fontFamily.split(',')[0].replace(/"/g, '')))].sort(),
    baixadas: [...new Set([...document.fonts].filter(f => f.status === 'loaded').map(f => f.family.replace(/"/g, '')))].sort()})`);
  igual(fontes.usadas, ['Atkinson Hyperlegible Next', 'Bricolage Grotesque'], 'só Bricolage e Atkinson na entrada'); igual(fontes.baixadas, ['Atkinson Hyperlegible Next', 'Bricolage Grotesque'], 'Newsreader e JetBrains Mono não baixam');
  for (const largura of [390, 768, 1440]) {
    await p.tamanho(largura, 900); await dormir(150);
    const fracos = await p.avaliar(`(() => { const cor = t => (t.match(/[\\d.]+/g) || []).map(Number);
      const lum = ([r, g, b]) => [r, g, b].map(c => { c /= 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }).reduce((s, c, i) => s + c * [0.2126, 0.7152, 0.0722][i], 0);
      const razao = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m); return Math.round((x + 0.05) / (y + 0.05) * 100) / 100; };
      const fundo = e => { for (let x = e; x; x = x.parentElement) { const v = cor(getComputedStyle(x).backgroundColor); if (v.length === 3 || v[3] > 0.5) return v.slice(0, 3); } return [255, 255, 255]; };
      return [...document.querySelectorAll('body *')].filter(e => e.getClientRects().length && !e.closest('.oculto, button:disabled') && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()))
        .map(e => [e.tagName + '.' + e.className + ' "' + e.textContent.trim().slice(0, 24) + '"', razao(cor(getComputedStyle(e).color).slice(0, 3), fundo(e))]).filter(([, r]) => r < 4.5); })()`);
    igual(fracos, [], 'contraste AA em ' + largura);
    // Formulário limpo: nenhum selo, tarja, cena ou pegada sobre ele ou a menos de 16 px.
    const encostados = await p.avaliar(`(() => { const f = document.querySelector('.formulario').getBoundingClientRect();
      return [...document.querySelectorAll('.selo-desenho, .selo-novo, .tarja, .cena-mar, .pegadas, .faixa-corre')].filter(e => { const r = e.getBoundingClientRect(); return r.right > f.left - 16 && r.left < f.right + 16 && r.bottom > f.top - 16 && r.top < f.bottom + 16; }).map(e => e.className.baseVal ?? e.className); })()`);
    igual(encostados, [], 'formulário limpo em ' + largura);
    certo(await p.semRolagemLateral(), 'rolagem lateral em ' + largura);
  }
  await p.tamanho(390, 844); await dormir(100);
  // Cores de decoração da página: azul-mar, amarelo-sol e laranja-boia; nada de rosa-goiaba nem roxo-ipê.
  const decoracao = await p.avaliar(`(() => { const sonda = document.createElement('span'); document.body.append(sonda); const valor = v => { sonda.style.color = 'var(' + v + ')'; return getComputedStyle(sonda).color; };
    const proibidas = ['--rosa-goiaba', '--roxo-ipe', '--rosa-claro', '--roxo-claro'].map(valor); sonda.remove();
    const usadas = new Set([...document.querySelectorAll('.entrada, .entrada *')].flatMap(e => { const c = getComputedStyle(e); return [c.backgroundColor, c.fill, c.color]; }));
    return proibidas.filter(c => usadas.has(c)); })()`);
  igual(decoracao, [], 'sem rosa-goiaba nem roxo-ipê na entrada');
});
await item('entrada de 14/11: ?criar-conta, #entrar e o link Entrar do topo levam ao formulário; o formulário continua igual', async () => {
  const noFormulario = () => p.avaliar('(() => { const r = document.querySelector("#entrar").getBoundingClientRect(); return r.top >= 0 && r.top < innerHeight / 2; })()');
  await p.tamanho(390, 844); await p.ir(URL_LOCAL + '/?criar-conta'); await p.esperar('document.querySelector("#nome")'); await dormir(300);
  certo(await noFormulario(), '?criar-conta rola até o formulário'); igual(await p.avaliar('document.activeElement.id'), 'nome', 'foco no primeiro campo do cadastro');
  igual(await p.texto('#titulo-acesso'), 'Crie sua conta', 'título do cadastro');
  await p.ir(URL_LOCAL + '/#entrar'); await p.esperar('document.querySelector("#acesso") && !document.querySelector("#nome")'); await dormir(300);
  certo(await noFormulario(), '#entrar rola até o formulário'); igual(await p.avaliar('document.activeElement.id'), 'email', 'foco no e-mail');
  await p.ir(URL_LOCAL + '/#criar-conta'); await p.esperar('document.querySelector("#nome")'); await dormir(300); certo(await noFormulario(), '#criar-conta rola até o formulário');
  await p.ir(URL_LOCAL); await p.esperar('document.querySelector("#acesso")'); await p.avaliar('scrollTo(0, 0)');
  certo(await p.avaliar('getComputedStyle(document.querySelector(".entrar-topo")).display !== "none" && document.querySelector(".entrar-topo").getBoundingClientRect().height >= 44'), 'link Entrar no topo da entrada, com 44 px de toque');
  await p.clicar('.entrar-topo'); await dormir(900); certo(await noFormulario(), 'link Entrar do topo leva ao formulário'); igual(await p.avaliar('document.activeElement.id'), 'email', 'foco no e-mail pelo topo');
  // Responder a demonstração e pedir a conta troca só o formulário: a demonstração respondida continua.
  await p.clicar('#demonstracao input[value="3"]'); await p.clicar('#quero-conta'); await p.esperar('document.querySelector("#nome")'); await dormir(600);
  igual(await p.avaliar('document.querySelector("#demonstracao").disabled'), true, 'demonstração continua respondida'); certo(await noFormulario(), 'Criar minha conta leva ao formulário');
  await p.clicar('#trocar'); await p.esperar('!document.querySelector("#nome")'); igual(await p.texto('#titulo-acesso'), 'Entre para estudar', 'troca para entrar');
  igual(await p.avaliar('[...document.querySelectorAll("#acesso input")].map(i => i.name + ":" + i.type + ":" + i.autocomplete)'), ['email:text:username', 'senha:password:current-password'], 'campos da entrada iguais');
  await p.clicar('#trocar'); await p.esperar('document.querySelector("#nome")');
  igual(await p.avaliar('[...document.querySelectorAll("#acesso input")].map(i => i.name + ":" + i.type + ":" + i.autocomplete + ":" + i.minLength)'), ['nome:text:name:2', 'email:email:username:-1', 'senha:password:new-password:12'], 'campos do cadastro iguais');
  await p.clicar('#trocar'); await p.esperar('!document.querySelector("#nome")');
  await p.preencher('#email', 'digitado@example.com'); await p.clicar('#trocar'); await p.esperar('document.querySelector("#nome")');
  igual(await p.avaliar('document.querySelector("#email").value'), 'digitado@example.com', 'trocar de modo mantém o e-mail digitado');
  await p.clicar('#trocar'); await p.esperar('!document.querySelector("#nome")');
  // Faixa que corre com botão de pausa (no celular não há ponteiro para pará-la).
  await p.clicar('.pausar-faixa');
  igual(await p.avaliar('[getComputedStyle(document.querySelector(".trilho")).animationPlayState, document.querySelector(".pausar-faixa").getAttribute("aria-pressed")]'), ['paused', 'true'], 'faixa pausada pelo botão');
  await p.clicar('.pausar-faixa'); await p.avaliar('document.activeElement.blur()');
  igual(await p.avaliar('getComputedStyle(document.querySelector(".trilho")).animationPlayState'), 'running', 'faixa segue de novo');
  // Foco visível no link do topo, com contraste de pelo menos 3:1 sobre o branco.
  await p.tecla('x'); await p.avaliar('document.querySelector(".entrar-topo").focus()');
  igual(await p.avaliar('[getComputedStyle(document.querySelector(".entrar-topo")).outlineStyle, getComputedStyle(document.querySelector(".entrar-topo")).outlineColor]'), ['solid', 'rgb(39, 71, 245)'], 'foco azul-mar no link do topo');
  await p.avaliar('document.activeElement.blur(); scrollTo(0, 0)');
});
await item('cadastro cai direto numa questão curta, sem clique a mais', async () => {
  await cadastrar('Primeira');
  const id = await idAtual(); certo(id > 0 && !q(id).imagens.length && !q(id).grupo, 'primeira questão curta, veio ' + id);
  igual(await hoje(), '0 de 5', 'ritmo do dia');
  igual(await p.avaliar('document.querySelector("#conferir").disabled'), true, 'Conferir só depois de marcar');
  certo(!(await p.avaliar('fetch("/api/painel").then(r => r.text())')).includes('"correta"'), 'painel sem gabarito');
  igual(await p.avaliar('getComputedStyle(document.querySelector(".entrar-topo")).display'), 'none', 'link Entrar do topo some com a conta aberta');
});
await item('menu embaixo no celular e no cabeçalho no computador, com cinco destinos', async () => {
  igual(await p.avaliar('[...document.querySelectorAll("#menu a")].map(a => a.innerText.trim())'), ['Estudar', 'Progresso', 'Simulado', 'Nota', 'Conta'], 'destinos');
  igual(await p.avaliar('getComputedStyle(document.querySelector("#menu")).position'), 'fixed', 'menu fixo no celular');
  certo(await p.avaliar('[...document.querySelectorAll("#menu a")].every(a => a.getBoundingClientRect().height >= 44)'), 'toque de 44 px');
  await p.tamanho(1280, 900); await dormir(100);
  igual(await p.avaliar('getComputedStyle(document.querySelector("#menu")).position'), 'static', 'menu no cabeçalho');
  await p.tamanho(390, 844); await dormir(100);
});
await item('erro: marca a escolhida, deixa tentar de novo e só então mostra a certa', async () => {
  const id = await idAtual(); await marcar(id, errada(id)); await p.clicar('#conferir');
  await p.esperar('document.querySelector("#ver-resposta")');
  certo((await p.texto('.correcao')).includes('Não foi essa'), 'aviso de erro');
  igual(await p.avaliar(`document.querySelectorAll('.alternativa[data-correcao=correta]').length`), 0, 'gabarito ainda escondido');
  await marcar(id, q(id).correta);
  await p.esperar('document.querySelector("#proxima")');
  certo((await p.texto('.correcao')).includes('Agora sim'), 'segunda tentativa certa');
  igual(await p.avaliar(`[...document.querySelectorAll('.alternativa[data-correcao]')].map(a => a.dataset.correcao).sort()`), ['correta', 'errada'], 'escolhida e certa marcadas');
  certo((await p.texto('.correcao')).includes('volta na sua revisão amanhã'), 'aviso de revisão');
  igual(await hoje(), '1 de 5', 'ritmo');
  igual(sql('SELECT COUNT(*) FROM respostas')[0][0], 1, 'segunda tentativa não é registrada');
  if (CAPTURAS) await p.captura(path.join(CAPTURAS, 'correcao-390.png'));
});
await item('acerto mostra Certa e a próxima questão já vem pronta', async () => {
  await seguinte(); const id = await responder();
  certo((await p.texto('.correcao')).includes('Certa!'), 'acerto'); igual(await hoje(), '2 de 5', 'ritmo');
  await dormir(350);
  igual(await p.avaliar('getComputedStyle(document.querySelector(".alternativa[data-correcao=correta]")).backgroundColor'), 'rgb(237, 243, 236)', 'alternativa certa em verde, mesmo marcada');
  certo((await p.texto('#anuncio')).includes('Certa'), 'resultado anunciado ao leitor de tela');
  certo(id !== 0, 'id');
});
await item('Chutei: acerto no chute vai para a revisão', async () => {
  await seguinte(); await responder({chute: true});
  certo((await p.texto('.correcao')).includes('Como foi chute'), 'aviso do chute');
  igual(sql('SELECT COUNT(*) FROM respostas WHERE chute=1 AND acerto=1')[0][0], 1, 'chute gravado');
  await p.avaliar('location.hash = "#progresso"'); await p.esperar('document.querySelector(".passo")');
  certo((await p.texto('#conteudo')).includes('2 questões estão no seu caderno de revisão'), 'caderno com erro e chute');
  await p.avaliar('location.hash = "#estudar"'); await questaoPronta();
});
await item('alternativa marcada continua lá ao sair e voltar', async () => {
  const id = await idAtual(); await marcar(id, 3);
  await p.avaliar('location.hash = "#conta"'); await p.esperar('document.querySelector("#sair")');
  await p.avaliar('location.hash = "#estudar"'); await questaoPronta();
  igual(await idAtual(), id, 'mesma questão'); igual(await p.avaliar(`document.querySelector('input[name="alternativa-${id}"][value="3"]').checked`), true, 'marcação preservada');
});
await item('Pular troca de questão sem registrar resposta', async () => {
  const id = await idAtual(); const antes = sql('SELECT COUNT(*) FROM respostas')[0][0];
  await p.clicar('#pular'); await p.esperar(`${trocou}(${id})`, 8000, "troca de questão");
  igual(sql('SELECT COUNT(*) FROM respostas')[0][0], antes, 'nada registrado');
});
await item('falha de rede não perde a marcação nem conta a resposta duas vezes', async () => {
  await questaoPronta(); const id = await idAtual(); const antes = sql('SELECT COUNT(*) FROM respostas')[0][0];
  await marcar(id, q(id).correta);
  await p.s('Network.emulateNetworkConditions', {offline: true, latency: 0, downloadThroughput: -1, uploadThroughput: -1});
  await p.clicar('#conferir'); await p.esperar('document.querySelector("#retorno .engano")');
  certo((await p.texto('#retorno')).includes('não foi enviada'), 'aviso de envio');
  igual(await p.avaliar(`document.querySelector('input[name="alternativa-${id}"][value="${q(id).correta}"]').checked`), true, 'marcação mantida');
  await p.s('Network.emulateNetworkConditions', {offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1});
  await p.clicar('#conferir'); await p.esperar('document.querySelector("#proxima")');
  igual(sql('SELECT COUNT(*) FROM respostas')[0][0], antes + 1, 'uma resposta só');
});
await item('meta do dia: ponto de parada com Mais 5, sem empurrar', async () => {
  await seguinte(); await responder(); igual(await hoje(), '5 questões', 'meta'); await seguinte();
  certo((await p.texto('.marco')).includes('Meta de hoje cumprida'), 'marco');
  certo((await p.texto('.marco')).includes('Encerrar por hoje'), 'opção de parar');
  if (CAPTURAS) await p.captura(path.join(CAPTURAS, 'meta-390.png'));
  await p.clicar('#mais-cinco'); await questaoPronta(); igual(await hoje(), '5 de 10', 'novo bloco');
  certo(await p.existe('.ritmo .selo.certo'), 'selo de meta cumprida');
});
await item('foco por matéria mostra só a matéria escolhida e mantém a densidade', async () => {
  await p.clicar('#abrir-foco'); await p.clicar('#painel-foco [data-materia="Física"]'); await questaoPronta();
  certo((await p.texto('.questao-topo .rotulo')).startsWith('Física'), 'questão de Física');
  const feitas = sql('SELECT feitos FROM ciclos')[0][0]; await responder();
  certo(JSON.parse(sql('SELECT feitos FROM ciclos')[0][0]).length === JSON.parse(feitas).length + 1, 'densidade andou no foco');
  await seguinte(); certo((await p.texto('.questao-topo .rotulo')).startsWith('Física'), 'segue em Física');
  await p.clicar('.modos [data-modo="misturado"]'); await questaoPronta();
});
await item('figura carrega sozinha e libera o Conferir', async () => {
  await abrir(5);
  await p.esperar('document.querySelector(".figura img")?.naturalWidth === 120', 8000, 'figura carregada');
  await marcar(5, q(5).correta); igual(await p.avaliar('document.querySelector("#conferir").disabled'), false, 'Conferir liberado');
  await p.clicar('#conferir'); await p.esperar('document.querySelector("#proxima")');
});
await item('texto do PDF vira parágrafo, com referência e comando separados', async () => {
  await abrir(7);
  igual(await p.avaliar('document.querySelector(".enunciado .paragrafo").innerText.includes("\\n")'), false, 'parágrafo sem quebra do PDF');
  igual(await p.texto('.enunciado .comando'), 'Qual é o comando desta questão?', 'comando'); certo((await p.texto('.enunciado .fonte')).startsWith('SOBRENOME'), 'referência');
  if (CAPTURAS) await p.captura(path.join(CAPTURAS, 'questao-390.png'));
  await responder();
  certo(!(await p.texto('.correcao')).includes('solução comentada'), 'acerto seguro não pede explicação');
});
await item('conjunto: duas perguntas respondidas juntas e corrigidas uma a uma', async () => {
  await abrir(21);
  certo((await p.texto('.texto-comum')).includes('Texto comum'), 'texto comum');
  await marcar(21, q(21).correta); igual(await p.avaliar('document.querySelector("#conferir").disabled'), true, 'falta a segunda');
  await marcar(22, errada(22)); await p.clicar('#conferir'); await p.esperar('document.querySelector("#proxima")');
  igual(await p.avaliar('[...document.querySelectorAll(".correcao")].map(c => c.innerText.includes("Certa!"))'), [true, false], 'correção por pergunta');
});
await item('explicação comentada aparece quando existe', async () => {
  await abrir(2);
  await marcar(2, errada(2)); await p.clicar('#conferir'); await p.clicar('#ver-resposta'); await p.esperar('document.querySelector("#proxima")');
  certo((await p.texto('.correcao')).includes('Explicação comentada da questão 2.'), 'explicação');
  certo(await p.existe('[data-treinar]'), 'atalho para treinar o assunto');
});
await item('progresso leva à próxima ação e ao treino por assunto', async () => {
  await p.avaliar('location.hash = "#progresso"'); await p.esperar('document.querySelector(".passo")');
  certo((await p.texto('h1')).includes('Seu progresso'), 'título'); certo(await p.existe('details.materia'), 'matérias');
  certo((await p.texto('#conteudo')).includes('não são nota TRI'), 'aviso de TRI mantido');
  if (CAPTURAS) await p.captura(path.join(CAPTURAS, 'progresso-390.png'));
  await p.avaliar('document.querySelector("details.materia").open = true'); await p.clicar('[data-treinar-materia]');
  await questaoPronta(); igual(await p.avaliar('document.querySelector("#abrir-foco").hasAttribute("data-ativo")'), true, 'foco ligado');
  certo((await p.texto('#abrir-foco')).includes(':'), 'foco no assunto');
  await p.clicar('.modos [data-modo="misturado"]'); await questaoPronta();
});
await item('revisão espaçada: o erro de ontem volta hoje com selo de revisão', async () => {
  sql('UPDATE respostas SET criada = criada - 86400');
  await p.recarregar(); await questaoPronta();
  const vencidas = await p.avaliar('painel.estudo.revisao.vencidas.length'); certo(vencidas >= 3, 'vencidas: ' + vencidas);
  certo((await p.texto('.modos [data-modo="revisao"]')).includes(String(vencidas)), 'contagem na ficha');
  igual(await hoje(), '0 de 5', 'dia novo começa do zero');
  await p.clicar('.modos [data-modo="revisao"]'); await questaoPronta();
  certo(await p.existe('.questao .selo.revisao'), 'selo de revisão');
  await responder(); igual(await p.avaliar('painel.estudo.revisao.vencidas.length'), vencidas - 1, 'revisão feita sai da fila do dia');
  await p.clicar('.modos [data-modo="misturado"]'); await questaoPronta();
});
await item('abre na hora com o que ficou guardado, mesmo com o servidor fora', async () => {
  await p.recarregar(); await questaoPronta(); const id = await idAtual();
  certo(await p.avaliar('Boolean(JSON.parse(localStorage.getItem("pu.painel.v2")).conta)'), 'painel guardado');
  certo(!(await p.avaliar('localStorage.getItem("pu.painel.v2") + localStorage.getItem("pu.questoes.v2")')).includes('"correta"'), 'sem gabarito no aparelho');
  await p.s('Network.setBlockedURLs', {urls: ['*/api/*']});
  try {
    await p.recarregar();
    await p.esperar('document.querySelector(".questao:not(.esqueleto) #conferir")', 3000, 'questão na tela sem rede');
    igual(await idAtual(), id, 'mesma questão de antes');
    await p.esperar('document.querySelector("#aviso").textContent.includes("conectar")', 4000, 'aviso de conexão');
  } finally { await p.s('Network.setBlockedURLs', {urls: []}); }
  await p.recarregar(); await questaoPronta();
});
await item('simulado: correção só no fim, retomada depois de recarregar e revisão das questões', async () => {
  await p.avaliar('location.hash = "#simulado"'); await p.clicar('#comecar');
  await p.esperar('document.querySelector(".simulado-topo")'); await questaoPronta();
  const ids = await p.avaliar('simulado.ids'); igual(ids.length, 10, 'dez questões'); certo(!ids.includes(21) && !ids.includes(22), 'sem conjuntos');
  certo(new Set(ids.slice(0, 4).map(id => q(id).area)).size === 4, 'quatro áreas nas quatro primeiras');
  for (let n = 0; n < 3; n++) { const id = await idAtual(); await marcar(id, n === 0 ? errada(id) : q(id).correta); await p.clicar('#conferir'); await p.esperar(`${trocou}(${id})`, 8000, "troca de questão"); igual(await p.existe('.alternativa[data-correcao]'), false, 'sem correção durante'); }
  await p.recarregar(); await p.esperar('document.querySelector("#continuar")');
  certo((await p.texto('#conteudo')).includes('questão 4 de 10'), 'retomada no ponto certo');
  await p.clicar('#continuar'); await questaoPronta();
  for (let n = 3; n < 9; n++) { const id = await idAtual(); await marcar(id, q(id).correta); await p.clicar('#conferir'); await p.esperar(`document.querySelector(".resultado-simulado, #tentar") || ${trocou}(${id})`, 12000, "troca de questão"); }
  // Última resposta com o servidor fora e a página recarregada no meio do envio: não pode travar nem perder a rodada.
  await dormir(600); const ultima = await idAtual(); await marcar(ultima, q(ultima).correta);
  await p.s('Network.setBlockedURLs', {urls: ['*/api/questoes/*']});
  try { await p.clicar('#conferir'); await p.esperar('document.querySelector("h1")?.innerText.includes("Corrigindo")', 5000, 'correção em andamento'); await p.recarregar(); }
  finally { await p.s('Network.setBlockedURLs', {urls: []}); }
  await p.esperar('document.querySelector(".resultado-simulado, #tentar")', 20000, 'resultado depois de recarregar');
  if (await p.existe('#tentar')) await p.clicar('#tentar');
  await p.esperar('document.querySelector(".resultado-simulado")', 12000, 'resultado');
  certo(!(await p.avaliar('localStorage.getItem("pu.simulado.v2")')).includes('enviando'), 'envio em andamento não é gravado');
  certo((await p.texto('h1')).includes('Você acertou 9 de 10'), 'placar: ' + await p.texto('h1'));
  igual(await p.avaliar('document.querySelectorAll(".linha-resultado[data-acerto=false]").length'), 1, 'uma errada');
  if (CAPTURAS) await p.captura(path.join(CAPTURAS, 'simulado-390.png'));
  await p.clicar('.linha-resultado[data-acerto=false] [data-rever]'); await p.esperar('document.querySelector("#voltar-resultado")');
  igual(await p.avaliar(`[...document.querySelectorAll('.alternativa[data-correcao]')].map(a => a.dataset.correcao).sort()`), ['correta', 'errada'], 'revisão marcada');
  await p.clicar('#voltar-resultado'); await p.esperar('document.querySelector(".resultado-simulado")');
});
await item('conta: meta do dia, dispositivos e saída que limpa o aparelho', async () => {
  await p.avaliar('location.hash = "#conta"'); await p.esperar('document.querySelector("[data-revogar]")');
  await p.clicar('[data-meta="3"]'); igual(await p.avaliar('JSON.parse(localStorage.getItem("pu.prefs.v1." + painel.conta.id)).meta'), 3, 'meta guardada por conta');
  certo((await p.texto('#dispositivos')).includes('este dispositivo'), 'dispositivo atual');
  // Lembrete diário: arquivo de calendário gerado no aparelho, sem pedido ao servidor.
  await p.avaliar('(() => { window.__ics = null; const original = URL.createObjectURL; URL.createObjectURL = b => { b.text().then(t => { window.__ics = t; }); return original.call(URL, b); }; HTMLAnchorElement.prototype.click = function () {}; })()');
  await p.preencher('#hora-lembrete', '07:30'); await p.clicar('#criar-lembrete'); await p.esperar('window.__ics');
  const ics = await p.avaliar('window.__ics'); certo(ics.includes('RRULE:FREQ=DAILY') && /DTSTART:\d{8}T073000/.test(ics) && /DTEND:\d{8}T074000/.test(ics) && ics.includes('BEGIN:VALARM'), 'evento diário às 07:30');
  if (CAPTURAS) await p.captura(path.join(CAPTURAS, 'conta-390.png'));
  await p.clicar('#sair'); await p.esperar('document.querySelector("#acesso")');
  igual(await p.avaliar('[localStorage.getItem("pu.painel.v2"), localStorage.getItem("pu.questoes.v2"), localStorage.getItem("pu.simulado.v2")]'), [null, null, null], 'aparelho limpo');
  igual((await p.avaliar('fetch("/api/painel").then(r => r.status)')), 401, 'sessão encerrada no servidor');
});
await item('dados e segurança abre sem sessão e simulador de nota continua funcionando', async () => {
  await p.avaliar('location.hash = "#privacidade"'); await p.esperar('document.querySelector("h1")?.innerText.includes("Seus dados")');
  certo((await p.texto('#conteudo')).includes('Chutei'), 'texto atualizado');
  await cadastrar('Segunda'); await p.avaliar('location.hash = "#nota"'); await p.esperar('document.querySelector(".simulador")');
  certo(await p.semRolagemLateral(), 'simulador sem rolagem lateral');
});
await item('teclado no computador: letra marca, Enter confere e segue', async () => {
  await p.tamanho(1280, 900); await p.avaliar('location.hash = "#estudar"'); await questaoPronta();
  const id = await idAtual(); await p.tecla('abcde'[q(id).correta]);
  igual(await p.avaliar(`document.querySelector('input[name="alternativa-${id}"]:checked')?.value`), String(q(id).correta), 'letra marcou');
  await p.tecla('Enter'); await p.esperar('document.querySelector("#proxima")');
  await p.avaliar('document.activeElement.blur()'); await p.tecla('Enter'); await p.esperar(`${trocou}(${id})`, 8000, "troca de questão");
  if (CAPTURAS) await p.captura(path.join(CAPTURAS, 'estudar-1280.png'));
  certo(await p.semRolagemLateral(), 'sem rolagem lateral');
});
await item('telas de estudo sem rolagem lateral em 320, 768 e 390', async () => {
  for (const largura of [320, 768, 390]) { await p.tamanho(largura, 844); await dormir(120); for (const destino of ['#estudar', '#progresso', '#simulado', '#conta']) { await p.avaliar(`location.hash = "${destino}"`); await dormir(250); certo(await p.semRolagemLateral(), `rolagem lateral em ${destino} a ${largura}`); } }
  await p.avaliar('location.hash = "#estudar"'); await questaoPronta();
  await dormir(400);
  const medida = await p.avaliar('(() => { const b = document.querySelector(".barra-acao").getBoundingClientRect(), m = document.querySelector("#menu").getBoundingClientRect(); return {barra: Math.round(b.bottom), menu: Math.round(m.top), janela: innerHeight, rolagem: Math.round(scrollY)}; })()');
  certo(medida.barra <= medida.menu + 1, 'barra de ação acima do menu: ' + JSON.stringify(medida));
  if (CAPTURAS) await p.captura(path.join(CAPTURAS, 'estudar-390.png'), false);
});
await item('telas de estudo sem faixa que corre e sem movimento acima de 0,4 s', async () => {
  for (const destino of ['#estudar', '#progresso', '#simulado', '#conta']) {
    await p.avaliar(`location.hash = "${destino}"`); await dormir(250);
    igual(await p.avaliar('Boolean(document.querySelector(".faixa-corre, .selos-cartaz"))'), false, 'faixa ou selos em ' + destino);
  }
  await p.avaliar('location.hash = "#estudar"'); await questaoPronta();
  const tempos = await p.avaliar(`[...document.querySelectorAll("#conteudo > *, .alternativa, .barra-acao button")].flatMap(e => { const c = getComputedStyle(e); return [...c.animationDuration.split(","), ...c.transitionDuration.split(",")].map(t => parseFloat(t) * (t.trim().endsWith("ms") ? 0.001 : 1)); })`);
  certo(Math.max(...tempos) <= 0.4, 'movimento mais longo: ' + Math.max(...tempos) + ' s');
  igual(await p.avaliar('Boolean(document.querySelector(".questao .vira"))'), false, 'rótulo que vira fora da folha da questão');
});
// Identidade da entrada levada às telas de dentro (12/11/2026): mesmas duas fontes, contorno de 1 px na cor do texto,
// faixa de areia na largura toda no topo de cada tela, um selo só nas telas de passagem, nada na folha da questão.
await item('telas de dentro com a identidade da entrada: fontes, contorno, faixa, selo e movimento', async () => {
  const TEXTO = 'rgb(47, 52, 55)'; const AREIA = 'rgb(247, 246, 243)';
  for (const largura of [390, 1280]) {
    await p.tamanho(largura, 900); await dormir(120);
    for (const destino of ['#estudar', '#progresso', '#simulado', '#nota', '#conta', '#privacidade']) {
      await p.avaliar(`location.hash = "${destino}"`); await dormir(450);
      const m = await p.avaliar(`(() => {
        const c = (e, pseudo) => getComputedStyle(e, pseudo);
        const familias = new Set([...document.querySelectorAll('body *')].filter(e => e.getClientRects().length).map(e => c(e).fontFamily.split(',')[0].trim().replace(/"/g, '')));
        const topo = document.querySelector('#conteudo > h1:not(.oculto), .simulador > h1, #conteudo > .ritmo');
        const fundo = topo ? c(topo, '::before') : null; const titulo = document.querySelector('#conteudo > h1:not(.oculto), .simulador > h1');
        return {familias: [...familias].sort(), topo: c(document.querySelector('.topo')).borderBottomColor,
          faixa: fundo && fundo.backgroundColor, larguraFaixa: Boolean(fundo) && parseFloat(fundo.width) >= innerWidth - 20,
          selo: titulo ? c(titulo, '::after').backgroundImage.startsWith('url("data:image/svg') : null, seloTempo: titulo ? parseFloat(c(titulo, '::after').animationDuration) : 0,
          seloNaQuestao: [...document.querySelectorAll('.questao, .questao *')].some(e => c(e, '::after').backgroundImage.includes('data:image/svg')),
          corre: Boolean(document.querySelector('.faixa-corre')), lateral: document.documentElement.scrollWidth <= document.documentElement.clientWidth};
      })()`);
      igual(m.familias, ['Iowan Old Style', 'SF Pro Display'], `duas fontes da entrada em ${destino} a ${largura}`);
      igual(m.topo, TEXTO, `contorno do topo em ${destino}`);
      igual(m.faixa, AREIA, `faixa de areia no topo de ${destino}`); igual(m.larguraFaixa, true, `faixa na largura toda em ${destino} a ${largura}`);
      igual(m.selo, destino === '#estudar' ? null : true, `selo só nas telas de passagem (${destino})`);
      certo(m.seloTempo <= 0.4, `selo assenta em até 0,4 s em ${destino}`);
      igual(m.seloNaQuestao, false, `folha da questão sem selo em ${destino}`); igual(m.corre, false, `sem faixa que corre em ${destino}`);
      igual(m.lateral, true, `sem rolagem lateral em ${destino} a ${largura}`);
    }
  }
  igual(await p.avaliar('getComputedStyle(document.querySelector("#menu")).borderTopColor'), TEXTO, 'contorno do menu');
  await p.s('Emulation.setEmulatedMedia', {features: [{name: 'prefers-reduced-motion', value: 'reduce'}]});
  try { await dormir(100); igual(await p.avaliar('getComputedStyle(document.querySelector("#conteudo > h1:not(.oculto)"), "::after").animationName'), 'none', 'selo parado com movimento reduzido'); }
  finally { await p.s('Emulation.setEmulatedMedia', {features: []}); }
  await p.tamanho(390, 844); await p.avaliar('location.hash = "#estudar"'); await questaoPronta();
});
await item('duas contas não se misturam', async () => {
  igual(sql("SELECT COUNT(*) FROM respostas r JOIN contas c ON c.id=r.conta WHERE c.nome='Segunda'")[0][0], 1, 'respostas da segunda conta');
  igual(await p.avaliar('painel.progresso.total'), 1, 'painel da segunda conta');
});
await item('dia de estudo segue o horário de Brasília em qualquer fuso do aparelho', async () => {
  await p.s('Emulation.setTimezoneOverride', {timezoneId: 'Asia/Tokyo'});
  try {
    igual(await p.avaliar('FORMATO_DIA.format(new Date("2026-11-13T02:30:00Z"))'), '2026-11-12', 'data em Brasília');
    igual(await p.avaliar('diaDaSemana("2026-11-12")'), 3, 'quinta-feira');
    igual(await p.avaliar('hojeLocal()'), await p.avaliar('painel.estudo.data'), 'mesmo dia do servidor');
    // Painel recém-chegado do servidor nunca é zerado pelo relógio do aparelho; só o guardado envelhece.
    igual(await p.avaliar('normalizar({estudo: {data: "2000-01-01", hoje: {respostas: 4, acertos: 2}, semana: [4,0,0,0,0,0,0], diaDaSemana: 0, revisao: {vencidas: [], caderno: 0}}}).estudo.hoje.respostas'), 4, 'dado do servidor preservado');
    igual(await p.avaliar('normalizar({estudo: {data: "2000-01-01", hoje: {respostas: 4, acertos: 2}, semana: [4,0,0,0,0,0,0], diaDaSemana: 0, revisao: {vencidas: [], caderno: 0}}}, true).estudo.hoje.respostas'), 0, 'painel guardado vira o dia');
  } finally { await p.s('Emulation.setTimezoneOverride', {timezoneId: ''}); await p.s('Emulation.setTimezoneOverride', {timezoneId: FUSO_DE_DIA}); }
});
await item('painel pedido antes de uma resposta não sobrescreve o resultado dela', async () => {
  const antes = await p.avaliar('painel.progresso.total');
  await p.avaliar('(async () => { const pedido = atualizar(); aplicarResultado({progresso: {total: 77, acertos: 1}}); await pedido; })()');
  igual(await p.avaliar('painel.progresso.total'), antes, 'painel velho descartado e pedido de novo');
});
// ---------- Tema (automático, diurno, noturno, fuso) e sons de acerto e erro (frente funcoes, 14/11/2026) ----------
const PRETO = 'rgb(0, 0, 0)'; const BRANCO = 'rgb(255, 255, 255)';
const fundoDaPagina = () => p.avaliar('getComputedStyle(document.documentElement).backgroundColor');
const temaNaPagina = () => p.avaliar('document.documentElement.dataset.tema ?? null');
const escolherTema = async valor => { await p.clicar(`input[name="tema"][value="${valor}"]`); await p.esperar(`prefs.tema === "${valor}"`, 4000, 'tema ' + valor); };
const abrirConta = async () => { await p.avaliar('location.hash = "#conta"'); await p.esperar('document.querySelector("#fuso optgroup[data-outros]") && document.querySelector("#sons")', 8000, 'tela da conta com a lista de fusos'); };
const seta = async key => { for (const type of ['keyDown', 'keyUp']) await p.s('Input.dispatchKeyEvent', {type, key, code: key, windowsVirtualKeyCode: {ArrowLeft: 37, ArrowRight: 39}[key]}); };
const trocarFuso = async fuso => { await p.s('Emulation.setTimezoneOverride', {timezoneId: ''}).catch(() => {}); await p.s('Emulation.setTimezoneOverride', {timezoneId: fuso}); };
// Relógio simulado: só o Date da página anda deslocado; os temporizadores continuam os de verdade.
const relogioFalso = iso => p.avaliar(`(() => { const Real = window.__DataReal || Date; window.__DataReal = Real; const desvio = Date.parse(${JSON.stringify(iso)}) - Real.now();
  window.Date = class extends Real { constructor(...a) { if (a.length) super(...a); else super(Real.now() + desvio); } static now() { return Real.now() + desvio; } }; })()`);
const relogioReal = () => p.avaliar('(() => { if (window.__DataReal) { window.Date = window.__DataReal; delete window.__DataReal; } })()');
// Depois de recarregar, qualquer tela de dentro desenhada serve (a página recarrega no endereço em que estava).
const estudoPronto = () => p.esperar('!document.body.classList.contains("sem-sessao") && document.querySelector("#conteudo").childElementCount && !document.querySelector(".espera")', 8000, 'tela de dentro');
const escolherFuso = fuso => p.avaliar(`(() => { const s = document.querySelector("#fuso"); s.value = ${JSON.stringify(fuso)}; s.dispatchEvent(new Event("change", {bubbles: true})); return prefs.fuso; })()`);

await item('tema: padrão automático, fuso detectado do navegador e, sem ele, o relógio do aparelho', async () => {
  await abrirConta();
  igual(await p.avaliar('prefs.tema'), 'automatico', 'padrão');
  igual(await p.avaliar('document.querySelector("input[name=tema]:checked").value'), 'automatico', 'opção marcada');
  igual(await p.avaliar('document.querySelector("#bloco-fuso").hidden'), false, 'fuso visível no automático');
  igual(await p.avaliar('fusoDoNavegador()'), FUSO_DE_DIA, 'fuso do navegador');
  igual(await p.avaliar('document.querySelector("#fuso").value'), '', 'segue o do navegador');
  certo((await p.texto('#fuso option')).includes(FUSO_DE_DIA.replace(/_/g, ' ')), 'primeira opção com o fuso detectado');
  certo(new RegExp(`^Agora são \\d{2}:\\d{2} em ${FUSO_DE_DIA.replace(/_/g, ' ').replace(/[.*+?^${}()|[\]\\/]/g, '\\$&')} \\(UTC`).test(await p.texto('#hora-fuso')), 'hora no fuso: ' + await p.texto('#hora-fuso'));
  igual(await temaNaPagina(), 'diurno', 'dia no fuso do teste');
  await trocarFuso('Asia/Tokyo');
  try { igual(await p.avaliar('fusoDoNavegador()'), 'Asia/Tokyo', 'Tóquio detectado'); } finally { await trocarFuso(FUSO_DE_DIA); }
  const semFuso = await p.avaliar(`(() => { const original = Intl.DateTimeFormat.prototype.resolvedOptions;
    Intl.DateTimeFormat.prototype.resolvedOptions = function () { return {...original.call(this), timeZone: undefined}; };
    try { const agora = new Date(); return {fuso: fusoDoNavegador(), hora: horaNoFuso(fusoDoNavegador(), agora).hora === agora.getHours(), opcao: opcoesDeFuso().includes("Relógio deste aparelho")}; }
    finally { Intl.DateTimeFormat.prototype.resolvedOptions = original; } })()`);
  igual(semFuso, {fuso: '', hora: true, opcao: true}, 'relógio do aparelho');
  const custo = await p.avaliar('(() => { const t = performance.now(); opcoesDeFuso(); return performance.now() - t; })()');
  certo(custo < 20, 'lista curta de fusos em menos de 20 ms, veio ' + custo.toFixed(1));
  igual(await p.avaliar(`(() => { prefs.fuso = 'Asia/Tokyo'; verConta(); const s = document.querySelector('#fuso'); const antes = s.value; completarFusos(s); const r = [antes, s.value, s.querySelectorAll('option[value="Asia/Tokyo"]').length]; prefs.fuso = ''; verConta(); return r; })()`), ['Asia/Tokyo', 'Asia/Tokyo', 1], 'fuso escolhido mantido ao completar a lista');
});
await item('tema: noturno pinta o fundo de preto e diurno de branco; fuso só no automático; teclado e leitor de tela', async () => {
  await abrirConta(); await escolherTema('noturno');
  igual(await temaNaPagina(), 'noturno', 'tema'); igual(await fundoDaPagina(), PRETO, 'fundo preto');
  igual(await p.avaliar('getComputedStyle(document.querySelector(".topo")).backgroundColor'), PRETO, 'topo preto');
  igual(await p.avaliar('getComputedStyle(document.documentElement).colorScheme'), 'dark', 'color-scheme escuro');
  igual(await p.avaliar('document.querySelector("meta[name=theme-color]").content'), '#000000', 'theme-color');
  igual(await p.avaliar('document.querySelector("#bloco-fuso").hidden'), true, 'fuso escondido no noturno');
  await escolherTema('diurno');
  igual(await fundoDaPagina(), BRANCO, 'fundo branco'); igual(await p.avaliar('getComputedStyle(document.documentElement).colorScheme'), 'light', 'color-scheme claro');
  igual(await p.avaliar('document.querySelector("meta[name=theme-color]").content'), '#FFFFFF', 'theme-color diurno');
  igual(await p.avaliar('document.querySelector("#bloco-fuso").hidden'), true, 'fuso escondido no diurno');
  // Grupo de rádio: as setas trocam a opção e o tema entra na hora.
  await p.avaliar('document.querySelector("input[name=tema]:checked").focus()'); await seta('ArrowRight');
  await p.esperar('prefs.tema === "noturno"', 3000, 'seta para a direita'); igual(await fundoDaPagina(), PRETO, 'noturno pelo teclado');
  await seta('ArrowLeft'); await seta('ArrowLeft'); await p.esperar('prefs.tema === "automatico"', 3000, 'setas para a esquerda');
  igual(await p.avaliar('document.querySelector("#bloco-fuso").hidden'), false, 'fuso de volta no automático');
  igual(await nomeAcessivel('.escolha-tema'), 'Tema', 'grupo com nome'); igual(await nomeAcessivel('input[name="tema"][value="noturno"]'), 'Noturno', 'opção com nome');
  igual(await nomeAcessivel('#fuso'), 'Fuso horário', 'seletor de fuso com nome');
  igual(await nomeAcessivel('#sons'), 'Sons de acerto e erro', 'interruptor com nome');
  igual(await p.avaliar('[document.querySelector("#sons").getAttribute("role"), document.querySelector("#sons").getAttribute("aria-checked")]'), ['switch', 'true'], 'interruptor ligado por padrão');
  certo(await p.semRolagemLateral(), 'sem rolagem lateral');
});
await item('tema automático: relógio simulado ao meio-dia e às 22h em dois fusos, troca na virada sem recarregar', async () => {
  await abrirConta();
  try {
    for (const [fuso, instante, esperado, hora] of [['America/Sao_Paulo', '2026-11-14T15:00:00Z', 'diurno', '12:00'], ['America/Sao_Paulo', '2026-11-15T01:00:00Z', 'noturno', '22:00'], ['Asia/Tokyo', '2026-11-14T03:00:00Z', 'diurno', '12:00'], ['Asia/Tokyo', '2026-11-14T13:00:00Z', 'noturno', '22:00']]) {
      igual(await escolherFuso(fuso), fuso, 'fuso escolhido'); await relogioFalso(instante); await p.avaliar('(aplicarTema(), mostrarHoraDoFuso())');
      igual(await temaNaPagina(), esperado, `${fuso} às ${hora}`); igual(await fundoDaPagina(), esperado === 'diurno' ? BRANCO : PRETO, `cor em ${fuso} às ${hora}`);
      certo((await p.texto('#hora-fuso')).startsWith(`Agora são ${hora} em ${fuso.replace(/_/g, ' ')}`), 'hora mostrada: ' + await p.texto('#hora-fuso'));
    }
    // Virada das 18h em São Paulo: a página não recarrega e o tema troca sozinho.
    await escolherFuso('America/Sao_Paulo'); await p.avaliar('window.__semRecarregar = 1');
    await relogioFalso('2026-11-14T20:59:58.500Z'); await p.avaliar('aplicarTema()'); igual(await temaNaPagina(), 'diurno', 'antes das 18h');
    await p.esperar('document.documentElement.dataset.tema === "noturno"', 4000, 'troca às 18h');
    igual(await p.avaliar('window.__semRecarregar'), 1, 'sem recarregar'); certo((await p.texto('#hora-fuso')).startsWith('Agora são 18:00'), 'hora atualizada na virada');
    // Aba que volta a ficar visível confere de novo (o temporizador pode ter dormido com o aparelho).
    await relogioFalso('2026-11-14T15:00:00Z'); await p.avaliar('(clearTimeout(relogioTema), document.dispatchEvent(new Event("visibilitychange")))');
    igual(await temaNaPagina(), 'diurno', 'conferido ao voltar para a aba');
  } finally { await relogioReal(); await escolherFuso(''); await p.avaliar('aplicarTema()'); }
  igual(await p.avaliar('prefs.fuso'), '', 'volta ao fuso do navegador');
});
let atrasarApp = false;
p.aoEvento('Fetch.requestPaused', async ({requestId, request}) => {
  if (!atrasarApp || !/\/app\.js(\?|$)/.test(request.url)) return;
  await dormir(400); await p.s('Fetch.continueRequest', {requestId}).catch(() => {});
});
await item('tema: preferência guardada por conta, entra antes do primeiro quadro e a entrada fica sem tema', async () => {
  await abrirConta(); await escolherTema('noturno');
  igual(await p.avaliar('JSON.parse(localStorage.getItem("pu.prefs.v1." + painel.conta.id)).tema'), 'noturno', 'guardada por conta');
  const {identifier} = await p.s('Page.addScriptToEvaluateOnNewDocument', {source: `(() => {
    const registrar = nome => { if (window[nome]) return; const raiz = document.documentElement; window[nome] = {tema: raiz.dataset.tema || null, fundo: raiz.isConnected ? getComputedStyle(raiz).backgroundColor : null}; };
    requestAnimationFrame(() => { registrar('__primeiroQuadro'); window.__appNoPrimeiroQuadro = typeof window.aplicarTema; });
    new MutationObserver(() => { const c = document.querySelector('#conteudo'); if (c && [...c.children].some(x => !x.matches('.entrada[data-estatica]'))) registrar('__primeiraTela'); }).observe(document, {childList: true, subtree: true});
  })()`});
  // O app.js chega 400 ms depois do resto: o navegador desenha antes dele, como numa rede lenta. Sem atraso o quadro sem
  // app.js só acontecia em 3 de 40 recargas e o item oscilava; o tema-inicial.js (síncrono no <head>) cobre esse quadro.
  atrasarApp = true; await p.s('Fetch.enable', {patterns: [{urlPattern: '*/app.js*'}]});
  try { await p.recarregar(); await estudoPronto(); } finally { await p.s('Fetch.disable'); atrasarApp = false; await p.s('Page.removeScriptToEvaluateOnNewDocument', {identifier}); }
  igual(await p.avaliar('window.__appNoPrimeiroQuadro'), 'undefined', 'primeiro quadro desenhado antes do app.js');
  igual(await p.avaliar('window.__primeiraTela'), {tema: 'noturno', fundo: PRETO}, 'primeira tela de dentro já no noturno');
  igual(await p.avaliar('window.__primeiroQuadro'), {tema: 'noturno', fundo: PRETO}, 'primeiro quadro sem clarão');
  igual(await temaNaPagina(), 'noturno', 'persiste ao recarregar');
  await abrirConta(); await p.clicar('#sair'); await p.esperar('document.querySelector("#acesso")');
  igual(await temaNaPagina(), null, 'entrada sem tema'); igual(await p.avaliar('getComputedStyle(document.documentElement).colorScheme'), 'light', 'entrada clara');
  igual(await p.avaliar('getComputedStyle(document.querySelector(".faixa-papel")).backgroundColor'), BRANCO, 'faixa da entrada igual');
  igual(await p.avaliar('document.querySelector("meta[name=theme-color]").content'), '#FFFFFF', 'theme-color da entrada (o do index.html, branco pela identidade de 14/11)');
  await cadastrar('Terceira');
  igual(await p.avaliar('prefs.tema'), 'automatico', 'conta nova no padrão'); igual(await temaNaPagina(), 'diurno', 'conta nova no automático de dia');
  await abrirConta(); await p.clicar('#sair'); await p.esperar('document.querySelector("#acesso")');
  await p.preencher('#email', 'segunda@example.com'); await p.preencher('#senha', 'Senha longa de teste 123!'); await p.clicar('#acesso button[type=submit]'); await estudoPronto();
  igual(await p.avaliar('prefs.tema'), 'noturno', 'a outra conta volta no noturno'); igual(await temaNaPagina(), 'noturno', 'noturno de volta');
});
// Contraste medido no próprio Chrome: pares por variável e varredura de todo texto visível de cada tela.
const PARES_NOTURNO = [
  ...['--fundo', '--painel', '--cartao', '--folha', '--barra', '--suave', '--verde-fundo', '--vermelho-fundo', '--amarelo-fundo', '--azul-fundo'].flatMap(f => [['--texto', f], ['--secundario', f]]),
  ['--texto-invertido', '--destaque'], ['--texto-invertido', '--destaque-passar'], ['--texto-invertido', '--texto'], ['--texto-invertido', '--esperando'],
  ['--texto-acerto', '--verde-fundo'], ['--texto-engano', '--vermelho-fundo'], ['--texto-dica', '--azul-fundo'], ['--texto-revisao', '--amarelo-fundo'],
  ['--verde', '--verde-fundo'], ['--vermelho', '--vermelho-fundo'], ['--verde', '--fundo'], ['--vermelho', '--fundo'], ['--azul', '--fundo'],
  ['--texto-sobre-cor', '--verde'], ['--texto-sobre-cor', '--vermelho'],
  ['--foco', '--fundo'], ['--foco', '--folha'], ['--foco', '--cartao'], ['--foco', '--suave'],
  ['--texto', '--fundo'], ['--linha', '--fundo'], ['--linha', '--folha'], ['--fio', '--fundo'], ['--fio', '--folha'], ['--fio', '--cartao'], ['--divisa', '--folha'],
  ['--verde', '--folha'], ['--vermelho', '--folha'], ['--amarelo', '--folha'], ['--amarelo', '--cartao']
];
const CONTA_CONTRASTE = `const cor = t => (t.match(/[\\d.]+/g) || []).map(Number);
  const lum = ([r, g, b]) => [r, g, b].map(c => { c /= 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }).reduce((s, c, i) => s + c * [0.2126, 0.7152, 0.0722][i], 0);
  const razao = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m); return Math.round((x + 0.05) / (y + 0.05) * 100) / 100; };`;
const varrerContraste = () => p.avaliar(`(() => { ${CONTA_CONTRASTE}
  const fundo = e => { for (let x = e; x; x = x.parentElement) { const v = cor(getComputedStyle(x).backgroundColor); if (v.length === 3 || v[3] > 0.5) return v.slice(0, 3); } return [255, 255, 255]; };
  const fracos = [];
  for (const e of document.querySelectorAll('body *')) {
    if (!e.getClientRects().length || e.closest('.oculto, [hidden], button:disabled, option, optgroup, script, style')) continue;
    if (![...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
    const c = getComputedStyle(e); if (c.visibility !== 'visible' || Number(c.opacity) < 1) continue;
    const r = razao(cor(c.color).slice(0, 3), fundo(e));
    if (r < 4.5) fracos.push(e.tagName + '.' + e.className + ' "' + e.textContent.trim().slice(0, 30) + '" ' + r);
  }
  return fracos; })()`);
await item('tema noturno: contraste AA (4,5:1) em todo par de texto e fundo, com acerto, erro, foco e bordas', async () => {
  igual(await temaNaPagina(), 'noturno', 'no noturno');
  const medidas = await p.avaliar(`(() => { ${CONTA_CONTRASTE}
    const sonda = document.createElement('span'); document.body.append(sonda);
    const rgb = v => { sonda.style.color = 'var(' + v + ')'; return cor(getComputedStyle(sonda).color).slice(0, 3); };
    const r = ${JSON.stringify(PARES_NOTURNO)}.map(([a, b]) => [a, b, razao(rgb(a), rgb(b))]); sonda.remove(); return r; })()`);
  igual(medidas.filter(([, , v]) => v < 4.5), [], 'pares abaixo de 4,5:1');
  certo(medidas.length === PARES_NOTURNO.length, 'todos os pares medidos');
  // Questão corrigida com erro (certa e escolhida marcadas), depois com acerto, e as telas de passagem.
  await p.avaliar('location.hash = "#estudar"'); await abrir(9); await marcar(9, errada(9)); await p.clicar('#conferir'); await p.esperar('document.querySelector("#ver-resposta")');
  igual(await varrerContraste(), [], 'segunda tentativa'); await p.clicar('#ver-resposta'); await p.esperar('document.querySelector("#proxima")'); await dormir(450);
  igual(await varrerContraste(), [], 'questão corrigida com erro');
  await abrir(10); await marcar(10, q(10).correta); await p.clicar('#conferir'); await p.esperar('document.querySelector("#proxima")'); await dormir(450);
  igual(await varrerContraste(), [], 'questão corrigida com acerto');
  for (const destino of ['#progresso', '#simulado', '#nota', '#conta', '#privacidade']) { await p.avaliar(`location.hash = "${destino}"`); await dormir(500); igual(await varrerContraste(), [], 'texto em ' + destino); }
  await abrirConta(); await p.avaliar('document.querySelector("input[name=tema]:checked").focus()'); await seta('ArrowRight'); await seta('ArrowLeft');
  const foco = await p.avaliar(`(() => { ${CONTA_CONTRASTE} const e = document.querySelector('.opcao-tema:has(input:focus-visible)'); if (!e) return null; const c = getComputedStyle(e); return [c.outlineStyle, razao(cor(c.outlineColor), cor(getComputedStyle(document.documentElement).backgroundColor))]; })()`);
  certo(foco && foco[0] === 'solid' && foco[1] >= 4.5, 'contorno de foco visível e com contraste: ' + JSON.stringify(foco));
  await escolherTema('noturno');
});
await item('tema noturno: figura da prova sobre cartão claro, sem inverter as cores', async () => {
  await p.avaliar('location.hash = "#estudar"'); await abrir(5);
  await p.esperar('document.querySelector(".figura img")?.naturalWidth === 120', 8000, 'figura carregada');
  const figura = await p.avaliar('(() => { const c = getComputedStyle(document.querySelector(".figura img")); return [c.backgroundColor, parseFloat(c.paddingTop) > 0, c.filter]; })()');
  igual(figura, [BRANCO, true, 'none'], 'cartão branco, sem filtro');
});
await item('sons: acerto e erro na correção imediata; nada no simulado, na revisão dele nem com o interruptor desligado', async () => {
  await p.avaliar(`(() => { window.__sons = []; window.__chamadas = 0;
    const desenhar = som.desenhar, tocar = som.tocar;
    som.desenhar = (contexto, tipo, ...resto) => { window.__sons.push(tipo); return desenhar.call(som, contexto, tipo, ...resto); };
    som.tocar = tipo => { window.__chamadas++; return tocar.call(som, tipo); }; })()`);
  const sons = () => p.avaliar('window.__sons');
  await p.avaliar('location.hash = "#estudar"');
  await abrir(11); await marcar(11, q(11).correta); await p.clicar('#conferir'); await p.esperar('document.querySelector("#proxima")');
  igual(await sons(), ['acerto'], 'acerto');
  await abrir(12); await marcar(12, errada(12)); await p.clicar('#conferir'); await p.esperar('document.querySelector("#ver-resposta")');
  igual(await sons(), ['acerto', 'erro'], 'erro na primeira tentativa');
  await marcar(12, q(12).correta); await p.esperar('document.querySelector("#proxima")');
  igual(await sons(), ['acerto', 'erro', 'acerto'], 'acerto na segunda tentativa');
  await abrir(13); await marcar(13, errada(13)); await p.clicar('#conferir'); await p.clicar('#ver-resposta'); await p.esperar('document.querySelector("#proxima")');
  igual(await sons(), ['acerto', 'erro', 'acerto', 'erro'], '"Ver resposta" não toca de novo');
  await abrir(21); await marcar(21, q(21).correta); await marcar(22, errada(22)); await p.clicar('#conferir'); await p.esperar('document.querySelector("#proxima")');
  igual((await sons()).at(-1), 'erro', 'conjunto com uma errada');
  // Interruptor desligado: nada toca; ligar de novo toca o de acerto como amostra.
  await abrirConta(); await p.clicar('#sons');
  igual(await p.avaliar('[document.querySelector("#sons").getAttribute("aria-checked"), JSON.parse(localStorage.getItem("pu.prefs.v1." + painel.conta.id)).sons]'), ['false', false], 'desligado e guardado');
  const antes = (await sons()).length;
  await p.avaliar('location.hash = "#estudar"'); await abrir(14); await marcar(14, errada(14)); await p.clicar('#conferir'); await p.clicar('#ver-resposta'); await p.esperar('document.querySelector("#proxima")');
  igual((await sons()).length, antes, 'sem som com o interruptor desligado');
  await abrirConta(); await p.clicar('#sons'); igual((await sons()).slice(antes), ['acerto'], 'amostra ao ligar');
  // Simulado: correção só no fim, sem som; rever uma questão do resultado também não toca.
  const chamadas = await p.avaliar('window.__chamadas'); const tocados = (await sons()).length;
  await p.avaliar('location.hash = "#simulado"'); await p.clicar('#comecar'); await p.esperar('document.querySelector(".simulado-topo")'); await questaoPronta();
  for (let n = 0; n < 10; n++) { const id = await idAtual(); await marcar(id, n % 2 ? q(id).correta : errada(id)); await p.clicar('#conferir'); await p.esperar(`document.querySelector(".resultado-simulado, #tentar") || ${trocou}(${id})`, 12000, 'troca no simulado'); }
  await p.esperar('document.querySelector(".resultado-simulado, #tentar")', 12000, 'resultado'); if (await p.existe('#tentar')) await p.clicar('#tentar');
  await p.esperar('document.querySelector(".resultado-simulado")', 12000, 'resultado do simulado');
  await p.clicar('.linha-resultado[data-acerto=false] [data-rever]'); await p.esperar('document.querySelector("#voltar-resultado")');
  igual([await p.avaliar('window.__chamadas'), (await sons()).length], [chamadas, tocados], 'simulado e revisão sem som');
  await p.clicar('#voltar-resultado'); await p.esperar('document.querySelector(".resultado-simulado")');
  // Navegador sem Web Audio: silêncio, sem erro.
  igual(await p.avaliar(`(() => { const guardado = [window.AudioContext, window.webkitAudioContext, som.contexto, som.saida]; window.AudioContext = undefined; window.webkitAudioContext = undefined; som.contexto = null; som.saida = null;
    try { som.preparar(); return [som.contexto, som.tocar('acerto')]; } finally { [window.AudioContext, window.webkitAudioContext, som.contexto, som.saida] = guardado; } })()`), [null, false], 'sem Web Audio');
});
// Caso real (teste-só-com-falso): o contexto nasce num clique de verdade, roda no Chrome sem janela e o som sai na saída de áudio.
await item('som de verdade: contexto de áudio rodando no Chrome sem janela, com sinal na saída e cada som abaixo de 400 ms', async () => {
  await p.recarregar(); await estudoPronto();
  igual(await p.avaliar('som.contexto'), null, 'contexto só depois do gesto');
  await p.avaliar(`(() => { const preparar = som.preparar; window.__pico = 0;
    som.preparar = () => { preparar(); if (som.contexto && !window.__analisador) { const a = som.contexto.createAnalyser(); a.fftSize = 2048; som.saida.connect(a); window.__analisador = a;
      const dados = new Float32Array(a.fftSize); const inicio = performance.now();
      const medir = () => { a.getFloatTimeDomainData(dados); for (const v of dados) window.__pico = Math.max(window.__pico, Math.abs(v)); if (performance.now() - inicio < 4000) setTimeout(medir, 8); }; medir(); } }; })()`);
  await abrir(15);
  const centro = async seletor => p.avaliar(`(() => { const e = document.querySelector(${JSON.stringify(seletor)}); e.scrollIntoView({block: "center"}); const r = e.getBoundingClientRect(); return {x: r.x + r.width / 2, y: r.y + r.height / 2}; })()`);
  const tocarNaTela = async seletor => { const {x, y} = await centro(seletor); for (const type of ['mousePressed', 'mouseReleased']) await p.s('Input.dispatchMouseEvent', {type, x, y, button: 'left', clickCount: 1}); };
  await tocarNaTela(`label.alternativa:has(input[name="alternativa-15"][value="${q(15).correta}"])`); await p.esperar('!document.querySelector("#conferir").disabled', 3000, 'Conferir liberado');
  await tocarNaTela('#conferir'); await p.esperar('document.querySelector("#proxima")');
  await p.esperar('window.__pico > 0.01', 4000, 'sinal na saída de áudio');
  const real = await p.avaliar('({estado: som.contexto.state, tempo: som.contexto.currentTime > 0, pico: Math.round(window.__pico * 1000) / 1000})');
  igual([real.estado, real.tempo], ['running', true], 'contexto rodando'); certo(real.pico < 0.4, 'volume moderado na saída: ' + real.pico);
  const medidas = await p.avaliar(`(async () => { const r = {}; for (const tipo of ["acerto", "erro"]) { const c = new OfflineAudioContext(1, 48000, 48000); som.desenhar(c, tipo, c.destination, 0); const d = (await c.startRendering()).getChannelData(0);
    let ultimo = 0, pico = 0; d.forEach((v, i) => { const a = Math.abs(v); if (a > 0.001) ultimo = i; if (a > pico) pico = a; }); r[tipo] = {duracao: ultimo / 48000, pico}; } return r; })()`);
  for (const tipo of ['acerto', 'erro']) { certo(medidas[tipo].duracao > 0.15 && medidas[tipo].duracao < 0.4, `${tipo} com ${medidas[tipo].duracao} s`); certo(medidas[tipo].pico > 0.03 && medidas[tipo].pico < 0.35, `${tipo} com pico ${medidas[tipo].pico}`); }
  const notas = await p.avaliar('[SONS.acerto.notas.map(n => n[0]), SONS.erro.notas.map(n => n[0])]');
  certo(notas[0][1] > notas[0][0], 'acerto sobe'); certo(Math.max(...notas[1]) < Math.min(...notas[0]), 'erro mais grave que o acerto');
});
await item('capturas da conta e da questão corrigida em diurno e noturno, em 390, 768 e 1440', async () => {
  for (const tema of ['diurno', 'noturno']) {
    await abrirConta(); await escolherTema(tema);
    for (const largura of [390, 768, 1440]) {
      await p.tamanho(largura, largura < 800 ? 844 : 900); await abrirConta(); await dormir(500);
      certo(await p.semRolagemLateral(), `conta sem rolagem lateral em ${largura}`);
      if (CAPTURAS) await p.captura(path.join(CAPTURAS, `tema-conta-${tema}-${largura}.png`));
      await p.avaliar('location.hash = "#estudar"'); const id = [16, 17, 18, 19, 20, 23, 24][['diurno', 'noturno'].indexOf(tema) * 3 + [390, 768, 1440].indexOf(largura)];
      await abrir(id); await marcar(id, errada(id)); await p.clicar('#conferir'); await p.clicar('#ver-resposta'); await p.esperar('document.querySelector("#proxima")'); await dormir(500);
      certo(await p.semRolagemLateral(), `correção sem rolagem lateral em ${largura}`);
      if (CAPTURAS) await p.captura(path.join(CAPTURAS, `tema-correcao-${tema}-${largura}.png`));
    }
  }
  await p.tamanho(390, 844); await abrirConta(); await escolherTema('automatico'); await dormir(300);
  certo(await p.avaliar('!document.querySelector("#bloco-fuso").hidden'), 'fuso no automático');
  if (CAPTURAS) await p.captura(path.join(CAPTURAS, 'tema-conta-automatico-390.png'));
});
const errosLocais = p.erros.filter(e => !/favicon|401 \(Unauthorized\)|ERR_INTERNET_DISCONNECTED|ERR_BLOCKED_BY_CLIENT|Failed to fetch/.test(e));
await item('nenhum erro de JavaScript nem recurso bloqueado pela política de conteúdo', async () => { igual(errosLocais, [], 'erros'); });
// Depois da conta de erros: os pedidos recusados de propósito abaixo deixam aviso de 404 no console.
await item('identidade de 14/11: logo da pata no topo, fontes servidas pelo site e variáveis de cor', async () => {
  const m = await p.avaliar(`(async () => {
    const svg = document.querySelector('.topo .simbolo svg'); const caminho = svg && svg.querySelector('path');
    const fonte = await fetch('/fontes/pu-texto.woff2');
    const recusas = await Promise.all(['/fontes/nao-existe.woff2', '/fontes/..%2Fservidor.py', '/fontes/sub/pu-texto.woff2', '/ilustracoes/x.js', '/servidor.py', '/fontes/pu-texto.svg', '/ilustracoes/pu-texto.woff2'].map(async u => (await fetch(u)).status));
    await document.fonts.load('16px "Atkinson Hyperlegible Next"');
    const raiz = getComputedStyle(document.documentElement);
    return {logo: Boolean(caminho) && caminho.getAttribute('fill-rule') === 'evenodd' && caminho.getAttribute('d').startsWith('M256 0a256'),
      largura: Math.round(svg.getBoundingClientRect().width), cor: getComputedStyle(svg).color,
      fonte: [fonte.status, fonte.headers.get('content-type')], recusas,
      carregada: [...document.fonts].some(f => f.family.replace(/"/g, '') === 'Atkinson Hyperlegible Next' && f.status === 'loaded'),
      variaveis: ['--marca', '--azul-mar', '--roxo-ipe-noite', '--fonte-texto'].map(v => raiz.getPropertyValue(v).trim().split(',')[0])};
  })()`);
  igual(m.logo, true, 'círculo com a pata vazada no topo'); igual(m.largura, 32, 'símbolo de 32 px'); igual(m.cor, 'rgb(0, 0, 0)', 'círculo preto no topo');
  igual(m.fonte, [200, 'font/woff2'], 'fonte servida pelo próprio site'); igual(m.recusas, [404, 404, 404, 404, 404, 404, 404], 'só nomes simples, woff2 em fontes/ e webp ou png em ilustracoes/');
  const expressoes = ['app/servidor.py', 'ambiente/servidor.py', 'gerenciador/servidor.py'].map(f => (fs.readFileSync(path.join(RAIZ, f), 'utf8').match(/r'(\/\(\?:fontes\/[^']+)'/) || [])[1]);
  certo(expressoes[0] && expressoes.every(e => e === expressoes[0]), 'mesma expressão de arquivos estáticos nos três servidores: ' + JSON.stringify(expressoes));
  igual(m.carregada, true, 'fonte carrega com a política de conteúdo');
  igual(m.variaveis, ['#000000', '#2747F5', '#A78BFF', '"Atkinson Hyperlegible Next"'], 'variáveis de cor e de fonte da direção nova');
});

// ---------- Entrada pública: GitHub Pages + intermediário (simulado dentro do Chrome) ----------
await p.fechar();
p = await chrome.novaPagina({largura: 390, altura: 844});
await p.s('Emulation.setTimezoneOverride', {timezoneId: FUSO_DE_DIA});
const fila = new Map(); let pedidosPublicos = 0;
await p.s('Fetch.enable', {patterns: [{urlPattern: INTERMEDIARIO + '/*'}]});
const cors = [{name: 'Access-Control-Allow-Origin', value: URL_PUBLICA}, {name: 'Access-Control-Allow-Headers', value: 'Content-Type, Authorization'}, {name: 'Access-Control-Allow-Methods', value: 'GET, POST, OPTIONS'}, {name: 'Content-Type', value: 'application/json'}];
const responderFetch = (requestId, status, corpo) => p.s('Fetch.fulfillRequest', {requestId, responseCode: status, responseHeaders: cors, body: Buffer.from(JSON.stringify(corpo)).toString('base64')});
const PERMITIDO = (metodo, caminho) => (metodo === 'GET' && ['/api/configuracao', '/api/painel', '/api/dispositivos'].includes(caminho)) || (metodo === 'POST' && ['/api/entrar', '/api/cadastro', '/api/sair', '/api/dispositivos'].includes(caminho)) || (['GET', 'POST'].includes(metodo) && /^\/api\/questoes\/[1-9][0-9]{0,5}$/.test(caminho));
const recusados = []; const maiores = [];
p.aoEvento('Fetch.requestPaused', async ({requestId, request}) => {
  try {
    const u = new URL(request.url);
    if (request.method === 'OPTIONS') return await p.s('Fetch.fulfillRequest', {requestId, responseCode: 204, responseHeaders: cors});
    if (u.pathname === '/pedido') {
      const corpo = JSON.parse(request.postData); pedidosPublicos++;
      // Mesma lista de operações do intermediário publicado: a interface não pode depender de rota nova.
      if (!PERMITIDO(corpo.metodo, corpo.caminho)) { recusados.push(`${corpo.metodo} ${corpo.caminho}`); return await responderFetch(requestId, 400, {erro: 'Operação não permitida.'}); }
      const r = await fetch(URL_LOCAL + corpo.caminho, {method: corpo.metodo, headers: {Origin: URL_LOCAL, 'Content-Type': 'application/json', Cookie: 'sessao=' + (corpo.token || '')}, body: corpo.metodo === 'POST' ? JSON.stringify(corpo.dados || {}) : undefined});
      const dados = await r.json();
      if (['/api/entrar', '/api/cadastro'].includes(corpo.caminho)) { const achado = (r.headers.get('set-cookie') || '').match(/sessao=([^;]+)/); if (achado) dados.sessao = achado[1]; }
      const resultado = {status: r.status, dados}; const tamanho = Buffer.byteLength(JSON.stringify(resultado));
      if (tamanho > 100000) maiores.push(`${corpo.caminho}: ${tamanho}`);
      const id = crypto.randomUUID(); fila.set(id, resultado);
      return await responderFetch(requestId, 202, {id, recibo: 'recibo-' + id});
    }
    if (u.pathname.startsWith('/resultado/')) { const id = u.pathname.split('/').pop(); const r = fila.get(id); fila.delete(id); return await responderFetch(requestId, r ? 200 : 404, r || {erro: 'Solicitação expirada.'}); }
    await responderFetch(requestId, 404, {erro: 'Operação não encontrada.'});
  } catch (e) { await p.s('Fetch.failRequest', {requestId, errorReason: 'Failed'}).catch(() => {}); }
});
await item('entrada pública: cadastro pelo intermediário cai direto na questão', async () => {
  await p.ir(URL_PUBLICA); await p.esperar('document.querySelector("#acesso")');
  igual(await p.avaliar('document.documentElement.dataset.publico'), '1', 'modo público');
  await p.clicar('#trocar'); await p.preencher('#nome', 'Publica'); await p.preencher('#email', 'publica@example.com'); await p.preencher('#senha', 'Senha longa de teste 123!');
  await p.clicar('#acesso button[type=submit]'); await questaoPronta();
  certo(/^[A-Za-z0-9_-]{20,100}$/.test(await p.avaliar('JSON.parse(localStorage.getItem("pu.sessao.v1")).token')), 'sessão guardada sem senha');
  certo(!(await p.avaliar('JSON.stringify(localStorage)')).includes('Senha longa'), 'senha fora do aparelho');
});
await item('entrada pública: responder e seguir gasta uma viagem só', async () => {
  await dormir(1200); const antes = pedidosPublicos;
  await responder(); await seguinte(); await questaoPronta();
  const gasto = pedidosPublicos - antes; certo(gasto <= 2, 'viagens para responder e abrir a próxima: ' + gasto);
  await dormir(800);
});
await item('entrada pública: recarregar mantém a sessão e abre na questão', async () => {
  await p.recarregar(); await questaoPronta(); igual(await hoje(), '1 de 5', 'ritmo preservado');
  await p.avaliar('location.hash = "#conta"'); await p.esperar('document.querySelector("[data-revogar]")');
  await p.clicar('#sair'); await p.esperar('document.querySelector("#acesso")');
  igual(await p.avaliar('localStorage.getItem("pu.sessao.v1")'), null, 'sessão apagada ao sair');
});
await item('entrada pública: só operações aceitas pelo intermediário e respostas abaixo de 100 KB', async () => { igual(recusados, [], 'operações recusadas'); igual(maiores, [], 'respostas grandes'); });
await item('entrada pública: logo da pata no topo, ícones do manifesto e as quatro fontes servidas pelo próprio site', async () => {
  // A política de conteúdo da entrada só deixa o navegador conversar com o intermediário: manifesto e ícones são conferidos daqui, como o GitHub Pages os serve.
  const pedir = async u => (await fetch(new URL(u, URL_PUBLICA + '/'))).status;
  const manifesto = await (await fetch(URL_PUBLICA + '/manifest.webmanifest')).json();
  igual(await Promise.all(manifesto.icons.map(i => pedir(i.src))), [200, 200, 200, 200], 'ícones do manifesto');
  igual(manifesto.icons.filter(i => i.purpose === 'maskable').length, 1, 'um ícone com máscara');
  const m = await p.avaliar(`(async () => {
    for (const f of ['16px "Atkinson Hyperlegible Next"', 'italic 16px "Atkinson Hyperlegible Next"', '700 40px "Bricolage Grotesque"', '20px "Newsreader"', '16px "JetBrains Mono"']) await document.fonts.load(f);
    return {favicon: document.querySelector('link[rel=icon]').getAttribute('href'), apple: document.querySelector('link[rel=apple-touch-icon]').getAttribute('href'),
      carregadas: [...new Set([...document.fonts].filter(f => f.status === 'loaded').map(f => f.family.replace(/"/g, '')))].sort(),
      logo: Boolean(document.querySelector('.topo .simbolo svg path[fill-rule=evenodd]'))};
  })()`);
  igual(m.logo, true, 'logo da pata no topo'); igual([await pedir(m.favicon), await pedir(m.apple)], [200, 200], 'favicon e ícone da tela inicial');
  igual(m.carregadas, ['Atkinson Hyperlegible Next', 'Bricolage Grotesque', 'JetBrains Mono', 'Newsreader'], 'fontes carregadas');
});
await item('entrada pública sem erro de JavaScript', async () => { igual(p.erros.filter(e => !/favicon/.test(e)), [], 'erros'); });

await chrome.fechar(); servidor.kill(); estatico.close(); fs.rmSync(pasta, {recursive: true, force: true});
const falhas = resultados.filter(([, ok]) => !ok).length;
console.log(`\n${resultados.length - falhas} de ${resultados.length} itens passaram.`);
process.exit(falhas ? 1 : 0);
