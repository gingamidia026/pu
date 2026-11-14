'use strict';
/* Pé na Universidade (PU): interface de estudo.
   Dominique-Oliveira-Claude🤖🧡, 12/11/2026, a pedido de Dominique Oliveira. Desenho em docs/PLATAFORMA-FLUIDA.md.
   Princípios: abrir já na questão, sessões curtas com ponto de parada, revisão espaçada dos erros,
   retorno imediato e nenhuma decisão obrigatória antes de começar. O gabarito continua só no servidor. */
const conteudo = document.querySelector('#conteudo');
const aviso = document.querySelector('#aviso');
const menu = document.querySelector('#menu');
const publico = document.documentElement.dataset.publico === '1';
const conexao = window.ENEM_PUBLICO || {};
const $ = (seletor, raiz = document) => raiz.querySelector(seletor);
const $$ = (seletor, raiz = document) => [...raiz.querySelectorAll(seletor)];
const escapar = valor => String(valor).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const letra = indice => String.fromCharCode(65 + indice);
const plural = (n, um, varios) => `${n} ${n === 1 ? um : varios}`;

// ---------- Armazenamento no navegador (nunca a senha nem o gabarito) ----------
const CHAVES = {sessao:'pu.sessao.v1', dispositivo:'pu.dispositivo.v1', painel:'pu.painel.v2', prefs:'pu.prefs.v1', questoes:'pu.questoes.v2', simulado:'pu.simulado.v2'};
const guarda = {
  ler(chave, padrao = null) { try { const v = localStorage.getItem(chave); return v === null ? padrao : JSON.parse(v); } catch { return padrao; } },
  gravar(chave, valor) { try { localStorage.setItem(chave, JSON.stringify(valor)); } catch { /* Armazenamento bloqueado: segue só na página. */ } },
  apagar(chave) { try { localStorage.removeItem(chave); } catch { /* idem */ } }
};
let sessao = '';
let dispositivo = '';
try { dispositivo = localStorage.getItem(CHAVES.dispositivo) || ''; } catch { /* idem */ }
function guardarSessao(token) {
  sessao = token;
  if (token) guarda.gravar(CHAVES.sessao, {token, expira: Date.now() + 30 * 86400000});
  else guarda.apagar(CHAVES.sessao);
}
if (publico) {
  const salva = guarda.ler(CHAVES.sessao);
  if (salva && salva.expira > Date.now() && /^[A-Za-z0-9_-]{20,100}$/.test(salva.token || '')) sessao = salva.token;
  else guardarSessao('');
}
// Preferências ficam separadas por conta, para não passarem de uma pessoa a outra no mesmo aparelho.
// tema: automatico, diurno ou noturno; fuso: vazio segue o do navegador; sons: acerto e erro na correção imediata.
const PREFS_PADRAO = {meta: 5, foco: null, alvo: null, dicaChute: false, atalhos: true, semCronometro: false, tema: 'automatico', fuso: '', sons: true};
let prefs = {...PREFS_PADRAO};
const chavePrefs = () => `${CHAVES.prefs}.${painel?.conta?.id ?? 0}`;
function carregarPrefs() {
  prefs = {...PREFS_PADRAO, ...(guarda.ler(chavePrefs()) || {})};
  if (![3, 5, 10, 20].includes(prefs.meta)) prefs.meta = 5;
  if (!Object.hasOwn(TEMAS, prefs.tema)) prefs.tema = 'automatico';
  if (prefs.fuso && !fusoValido(prefs.fuso)) prefs.fuso = '';
  // O tema entra aqui, antes de qualquer tela de dentro ser desenhada.
  aplicarTema();
}
const salvarPrefs = () => { if (painel?.conta) guarda.gravar(chavePrefs(), prefs); };

// ---------- Estado ----------
let painel = null;
let cadastro = false;
const questoes = new Map();   // id → questão sem gabarito
const imagens = new Map();    // hash → promessa do endereço data:
const estado = {modo: 'misturado', primeira: null, puladas: new Set(), feitasSessao: new Set(), marcadas: {}, vez: 0, versao: 0, atual: null, aoTeclar: null};
let simulado = guarda.ler(CHAVES.simulado);
const enviosSimulado = new Map();   // id → envio em andamento; só na memória, nunca gravado
let relogio = null;

// ---------- Tema das telas de dentro: automático, diurno ou noturno (pedido de Dominique, 14/11/2026) ----------
// Só com a conta aberta: a página de entrada não muda. O tema vai em data-tema no <html> e as cores saem das variáveis
// do bloco de temas no fim do estilo.css. No automático, diurno das 6h às 18h e noturno das 18h às 6h no fuso escolhido.
// Fuso padrão: o do navegador; sem ele, o relógio do aparelho. O horário de verão fica por conta do Intl.
const TEMAS = {automatico: 'Automático', diurno: 'Diurno', noturno: 'Noturno'};
const COR_DA_BARRA = {diurno: '#FFFFFF', noturno: '#000000'};
const corDaBarra = document.querySelector('meta[name="theme-color"]');
const corDaEntrada = corDaBarra?.getAttribute('content') || '';
let relogioTema = null;
function fusoValido(fuso) {
  if (!fuso || typeof fuso !== 'string') return false;
  try { new Intl.DateTimeFormat('en-US', {timeZone: fuso}); return true; } catch { return false; }
}
function fusoDoNavegador() {
  try { const fuso = Intl.DateTimeFormat().resolvedOptions().timeZone; return fusoValido(fuso) ? fuso : ''; } catch { return ''; }
}
// Fuso em vigor: o escolhido nas configurações; senão o do navegador. Vazio quer dizer o relógio do aparelho.
const fusoEmVigor = () => fusoValido(prefs.fuso) ? prefs.fuso : fusoDoNavegador();
function horaNoFuso(fuso, agora = new Date()) {
  if (fuso) {
    try {
      const partes = new Intl.DateTimeFormat('en-US', {timeZone: fuso, hour: 'numeric', minute: 'numeric', hourCycle: 'h23'}).formatToParts(agora);
      const valor = tipo => Number(partes.find(p => p.type === tipo)?.value);
      if (Number.isFinite(valor('hour'))) return {hora: valor('hour') % 24, minuto: valor('minute')};
    } catch { /* cai no relógio do aparelho */ }
  }
  return {hora: agora.getHours(), minuto: agora.getMinutes()};
}
function temaEmVigor(agora = new Date()) {
  if (prefs.tema === 'diurno' || prefs.tema === 'noturno') return prefs.tema;
  const {hora} = horaNoFuso(fusoEmVigor(), agora);
  return hora >= 6 && hora < 18 ? 'diurno' : 'noturno';
}
// Deslocamento do fuso em relação ao UTC, para conferir na tela ("UTC−3").
function deslocamento(fuso, agora = new Date()) {
  let minutos = -agora.getTimezoneOffset();
  if (fuso) {
    try {
      const nome = new Intl.DateTimeFormat('en-US', {timeZone: fuso, timeZoneName: 'shortOffset'}).formatToParts(agora).find(p => p.type === 'timeZoneName')?.value || '';
      const achado = nome.match(/^GMT(?:([+-])(\d{1,2})(?::(\d{2}))?)?$/);
      if (achado) minutos = achado[1] ? (achado[1] === '-' ? -1 : 1) * (Number(achado[2]) * 60 + Number(achado[3] || 0)) : 0;
    } catch { /* fica o do aparelho */ }
  }
  const h = Math.floor(Math.abs(minutos) / 60); const m = Math.abs(minutos) % 60;
  return `UTC${minutos < 0 ? '−' : '+'}${h}${m ? ':' + String(m).padStart(2, '0') : ''}`;
}
const nomeDoFuso = fuso => fuso.replace(/_/g, ' ');
function aplicarTema() {
  clearTimeout(relogioTema); relogioTema = null;
  const raiz = document.documentElement;
  if (!painel?.conta) { delete raiz.dataset.tema; if (corDaBarra) corDaBarra.setAttribute('content', corDaEntrada); return; }
  const efetivo = temaEmVigor();
  if (raiz.dataset.tema !== efetivo) raiz.dataset.tema = efetivo;
  if (corDaBarra) corDaBarra.setAttribute('content', COR_DA_BARRA[efetivo]);
  // No automático, confere de novo na virada de cada minuto: a troca das 6h e das 18h acontece sem recarregar.
  // Todo fuso é múltiplo de 15 min, então a virada do minuto é a mesma em qualquer um.
  if (prefs.tema === 'automatico' || $('#hora-fuso')) relogioTema = setTimeout(() => { aplicarTema(); mostrarHoraDoFuso(); }, 60000 - Date.now() % 60000 + 25);
}
function mostrarHoraDoFuso() {
  const destino = $('#hora-fuso'); if (!destino) return;
  const fuso = fusoEmVigor(); const {hora, minuto} = horaNoFuso(fuso);
  const agora = `${String(hora).padStart(2, '0')}:${String(minuto).padStart(2, '0')}`;
  const proximo = temaEmVigor() === 'diurno' ? 'Fica no diurno até as 18h.' : 'Fica no noturno até as 6h.';
  destino.textContent = `Agora são ${agora} ${fuso ? `em ${nomeDoFuso(fuso)} (${deslocamento(fuso)})` : `no relógio deste aparelho (${deslocamento('')})`}. ${proximo}`;
}
// Fusos do Brasil primeiro; depois todos os que o navegador conhece. A lista completa (perto de 420 fusos, uns 70 ms)
// entra depois de a tela aparecer e fica guardada para as próximas vezes.
const FUSOS_DO_BRASIL = ['America/Sao_Paulo', 'America/Noronha', 'America/Bahia', 'America/Fortaleza', 'America/Recife', 'America/Maceio', 'America/Araguaina', 'America/Belem', 'America/Santarem', 'America/Campo_Grande', 'America/Cuiaba', 'America/Porto_Velho', 'America/Boa_Vista', 'America/Manaus', 'America/Eirunepe', 'America/Rio_Branco'];
const opcaoDeFuso = fuso => `<option value="${escapar(fuso)}">${escapar(nomeDoFuso(fuso))} (${deslocamento(fuso)})</option>`;
let outrosFusos = null;
function opcoesDeFuso() {
  const detectado = fusoDoNavegador();
  const brasil = FUSOS_DO_BRASIL.filter(fusoValido);
  const escolhido = prefs.fuso && !brasil.includes(prefs.fuso) ? `<optgroup label="Escolhido">${opcaoDeFuso(prefs.fuso)}</optgroup>` : '';
  const primeira = `<option value="">${detectado ? `Do navegador: ${escapar(nomeDoFuso(detectado))} (${deslocamento(detectado)})` : `Relógio deste aparelho (${deslocamento('')})`}</option>`;
  return `${primeira}<optgroup label="Brasil">${brasil.map(opcaoDeFuso).join('')}</optgroup>${escolhido}`;
}
function completarFusos(seletor) {
  if (!seletor?.isConnected || seletor.querySelector('optgroup[data-outros]')) return;
  if (outrosFusos === null) {
    let todos = []; try { todos = Intl.supportedValuesOf('timeZone'); } catch { /* navegador antigo: só o Brasil e o UTC */ }
    outrosFusos = [...new Set([...todos, 'UTC'])].filter(f => !FUSOS_DO_BRASIL.includes(f)).sort().map(opcaoDeFuso).join('');
  }
  seletor.insertAdjacentHTML('beforeend', `<optgroup label="Outros fusos" data-outros>${outrosFusos}</optgroup>`);
  // O fuso escolhido fora do Brasil só sai do grupo próprio se estiver na lista completa (nomes antigos não estão).
  if ([...seletor.querySelectorAll('optgroup[data-outros] option')].some(o => o.value === prefs.fuso)) $('optgroup[label="Escolhido"]', seletor)?.remove();
  seletor.value = prefs.fuso;
}
document.addEventListener('visibilitychange', () => { if (!document.hidden) { aplicarTema(); mostrarHoraDoFuso(); } });

// ---------- Sons de acerto e erro (Web Audio, sem arquivo de áudio e sem código de terceiros) ----------
// Tocam só quando a correção aparece na hora, no estudo. O simulado, a revisão do simulado e a questão já corrigida ficam
// sem som. O contexto de áudio nasce ou é retomado no gesto de responder: o navegador só libera áudio depois de um gesto,
// e a correção chega segundos depois, pela rede. Navegador sem Web Audio fica em silêncio, sem erro.
const SONS = {
  // Cada nota: [frequência em Hz, início em s, duração em s]. Acerto: mi5 e si5, subindo. Erro: ré4 e si3, mais grave e suave.
  acerto: {forma: 'sine', volume: 0.16, corte: 6000, notas: [[659.25, 0, 0.14], [987.77, 0.08, 0.26]]},
  erro: {forma: 'triangle', volume: 0.15, corte: 1400, notas: [[293.66, 0, 0.16], [246.94, 0.1, 0.24]]}
};
const som = {
  contexto: null, saida: null,
  preparar() {
    if (prefs.sons === false) return;
    try {
      const Contexto = window.AudioContext || window.webkitAudioContext; if (!Contexto) return;
      if (!som.contexto) { som.contexto = new Contexto(); som.saida = som.contexto.createGain(); som.saida.gain.value = 0.7; som.saida.connect(som.contexto.destination); }
      if (som.contexto.state === 'suspended') som.contexto.resume().catch(() => {});
    } catch { som.contexto = null; som.saida = null; }
  },
  // Desenha o som num contexto qualquer (o do navegador ou um OfflineAudioContext do teste). Devolve quando termina.
  desenhar(contexto, tipo, destino, inicio) {
    const {forma, volume, corte, notas} = SONS[tipo];
    const filtro = contexto.createBiquadFilter(); filtro.type = 'lowpass'; filtro.frequency.value = corte; filtro.connect(destino);
    let fim = inicio;
    for (const [frequencia, atraso, duracao] of notas) {
      const t = inicio + atraso; const oscilador = contexto.createOscillator(); const ganho = contexto.createGain();
      oscilador.type = forma; oscilador.frequency.setValueAtTime(frequencia, t);
      ganho.gain.setValueAtTime(0.0001, t); ganho.gain.linearRampToValueAtTime(volume, t + 0.012); ganho.gain.exponentialRampToValueAtTime(0.0001, t + duracao);
      oscilador.connect(ganho); ganho.connect(filtro); oscilador.start(t); oscilador.stop(t + duracao + 0.01);
      fim = Math.max(fim, t + duracao + 0.01);
    }
    return fim;
  },
  tocar(tipo) {
    if (prefs.sons === false || !SONS[tipo] || !som.contexto) return false;
    try {
      if (som.contexto.state === 'suspended') som.contexto.resume().catch(() => {});
      som.desenhar(som.contexto, tipo, som.saida, som.contexto.currentTime + 0.01);
      return true;
    } catch { return false; }
  }
};

// ---------- Transporte ----------
function mensagemErro(e) {
  if (e instanceof TypeError || ['TimeoutError', 'AbortError'].includes(e.name)) return 'Não foi possível conectar ao PU. Verifique sua conexão e tente novamente.';
  return e.message || 'Não foi possível concluir. Tente novamente.';
}
async function transportar(caminho, dados) {
  if (!publico) {
    const resposta = await fetch(caminho, dados === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(dados)});
    return {status: resposta.status, dados: await resposta.json()};
  }
  if (!conexao.habilitado || !/^https:\/\/[^/]+$/.test(conexao.intermediario || '')) throw new Error('O acesso público está em configuração. Ainda não é possível entrar.');
  const envio = await fetch(conexao.intermediario + '/pedido', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({metodo: dados === undefined ? 'GET' : 'POST', caminho, dados, token: sessao}), signal: AbortSignal.timeout(12000)});
  const recibo = await envio.json();
  if (!envio.ok) throw new Error(recibo.erro || 'A plataforma está temporariamente indisponível.');
  const inicio = Date.now(); let consultas = 0;
  while (Date.now() - inicio < 30000) {
    // O conector leva perto de 1 s para buscar e devolver o pedido: a primeira consulta espera esse tempo,
    // as seguintes são curtas e depois espaçam, para não gastar a cota do intermediário à toa.
    await new Promise(r => setTimeout(r, consultas++ === 0 ? 900 : Date.now() - inicio < 4000 ? 250 : 600));
    const resposta = await fetch(conexao.intermediario + '/resultado/' + recibo.id, {headers: {Authorization: 'Bearer ' + recibo.recibo}, signal: AbortSignal.timeout(10000)});
    const corpo = await resposta.json();
    if (resposta.status === 202) continue;
    if (!resposta.ok) throw new Error(corpo.erro || 'Não foi possível consultar a resposta.');
    return corpo;
  }
  throw new Error('A resposta demorou mais que o esperado. Tente novamente.');
}
async function api(caminho, dados) {
  const resposta = await transportar(caminho, dados);
  const resultado = resposta.dados;
  if (resposta.status >= 400) {
    if (resposta.status === 401 && !['/api/entrar', '/api/cadastro'].includes(caminho)) { encerrarLocal(); verEntrada(); }
    const falha = new Error(resultado.erro || 'Não foi possível concluir. Tente novamente.');
    falha.status = resposta.status;
    throw falha;
  }
  if (resultado.dispositivo) { dispositivo = resultado.dispositivo; try { localStorage.setItem(CHAVES.dispositivo, dispositivo); } catch { /* idem */ } delete resultado.dispositivo; }
  if (resultado.sessao) { guardarSessao(resultado.sessao); delete resultado.sessao; }
  if (caminho === '/api/sair') guardarSessao('');
  return resultado;
}
function erro(e) { aviso.className = 'falha'; aviso.textContent = mensagemErro(e); }
function informar(texto, falha = false) { aviso.className = falha ? 'falha' : ''; aviso.textContent = texto; }
/* Limpa o aparelho. Na saída pedida pela pessoa, apaga também o simulado; quando é a sessão que venceu,
   o simulado em andamento fica guardado e volta se a mesma conta entrar de novo. */
function encerrarLocal(saida = false) {
  pararRelogio(); painel = null;
  guardarSessao('');
  [CHAVES.painel, CHAVES.questoes].forEach(guarda.apagar);
  if (saida) { simulado = null; guarda.apagar(CHAVES.simulado); enviosSimulado.clear(); }
  questoes.clear(); imagens.clear(); prefs = {...PREFS_PADRAO}; aplicarTema();
  Object.assign(estado, {modo: 'misturado', primeira: null, puladas: new Set(), feitasSessao: new Set(), marcadas: {}, atual: null, versao: estado.versao + 1});
  if (window.PUSimulador) PUSimulador.limpar();
}

// ---------- Texto das questões ----------
const MIDIA = /^\[\[midia:\d+\]\]$/;
const INICIO_FONTE = /^(Disponível em:|Acesso em:|[A-ZÀ-Ý][A-ZÀ-Ý'’.\- ]+(,| et al\.))/;
/* As linhas vêm quebradas como no PDF da prova. Linha que enche a coluna continua na seguinte;
   linhas curtas seguidas são versos ou listas e ficam como estão; referência e comando ganham bloco próprio. */
function refluir(texto) {
  let linhas = String(texto || '').split('\n').map(l => l.trim());
  // Textos com linhas numeradas (1, 2, 3… sozinhos entre as linhas): o número vira marca pequena no começo da linha seguinte.
  const numeradas = linhas.map((l, i) => /^\d{1,3}$/.test(l) ? i : -1).filter(i => i >= 0);
  if (numeradas.length >= 3 && numeradas.every((i, n) => n === 0 || Number(linhas[i]) === Number(linhas[numeradas[n - 1]]) + 1)) {
    const juntas = [];
    for (let i = 0; i < linhas.length; i++) {
      if (numeradas.includes(i) && linhas[i + 1]) { juntas.push(`\u27E6${linhas[i]}\u27E7${linhas[i + 1]}`); i++; } else juntas.push(linhas[i]);
    }
    linhas = juntas;
  }
  const tamanhos = linhas.filter(l => l && !MIDIA.test(l)).map(l => l.length).sort((a, b) => b - a);
  const largura = tamanhos.length >= 3 ? tamanhos[1] : 0;
  const cheia = l => largura > 0 && l.length >= largura * .72;
  const blocos = []; let atual = null;
  const fechar = () => { if (atual) { blocos.push({tipo: atual.tipo, texto: atual.texto}); atual = null; } };
  const abrir = (tipo, l) => { fechar(); atual = {tipo, texto: l, ultima: l}; };
  for (const l of linhas) {
    if (!l) { fechar(); continue; }
    if (MIDIA.test(l)) { fechar(); blocos.push({tipo: 'midia', texto: l}); continue; }
    if (atual && atual.tipo === 'fonte') {
      if (/^(Acesso em:|Disponível em:)/.test(l) || (cheia(atual.ultima) && !/(\((adaptado|fragmento)\)|\d{4})\.$/.test(atual.ultima))) { atual.texto += ' ' + l; atual.ultima = l; continue; }
    }
    if (INICIO_FONTE.test(l) && !(atual && atual.tipo === 'p' && cheia(atual.ultima) && !/[.!?…”"]$/.test(atual.ultima))) { abrir('fonte', l); continue; }
    if (atual && atual.tipo === 'p') {
      const fimDeFrase = /[.!?…”"]$/.test(atual.ultima);
      if (cheia(atual.ultima)) {
        if (fimDeFrase && /^[A-ZÀ-Ý“"—–-]/.test(l) && atual.ultima.length < largura * .93) { abrir('p', l); continue; }
        atual.texto += ' ' + l; atual.ultima = l; continue;
      }
      if (!cheia(l) && largura > 0) { atual.texto += '\n' + l; atual.ultima = l; continue; }
      if (!fimDeFrase && largura === 0) { atual.texto += ' ' + l; atual.ultima = l; continue; }
    }
    abrir('p', l);
  }
  fechar();
  const paragrafos = blocos.filter(b => b.tipo === 'p');
  if (paragrafos.length && blocos.length > 1) paragrafos[paragrafos.length - 1].tipo = 'comando';
  return blocos;
}
const comMidia = (texto, item) => escapar(texto).replace(/\[\[midia:(\d+)\]\]/g, (_, i) => `<span class="midia" data-midia="${item.id}-${Number(i)}"></span>`).replace(/\u27E6(\d+)\u27E7/g, '<sup class="linha">$1</sup>');
function enunciadoHtml(texto, item) {
  return refluir(texto).map(b => b.tipo === 'midia' ? `<div class="figura">${comMidia(b.texto, item)}</div>` : `<p class="${b.tipo === 'p' ? 'paragrafo' : b.tipo}">${comMidia(b.texto, item).replace(/\n/g, '<br>')}</p>`).join('');
}
const alternativaHtml = (texto, item) => comMidia(String(texto || '').split('\n').map(l => l.trim()).filter(Boolean).join(' '), item);
const SEM_SOLUCAO = /Ainda não há solução comentada/;
// Enquanto o banco não tem solução comentada, oferece a busca da resolução fora do PU, pelo começo do enunciado.
function buscaResolucao(item) {
  const trecho = String(item.enunciado || '').replace(/\[\[midia:\d+\]\]/g, ' ').replace(/\s+/g, ' ').trim().split(' ').slice(0, 12).join(' ');
  const consulta = `Enem ${item.ano || ''} resolução comentada ${trecho}`.replace(/\s+/g, ' ').trim();
  return `<p class="apoio"><a href="https://www.google.com/search?q=${encodeURIComponent(consulta)}" target="_blank" rel="noopener noreferrer">Buscar a resolução desta questão</a> <span class="secundario">abre o Google em outra aba; o conteúdo é de terceiros.</span></p>`;
}

// ---------- Painel e ritmo ----------
// O dia de estudo segue o horário de Brasília, o mesmo do servidor, em qualquer fuso do aparelho.
const FORMATO_DIA = new Intl.DateTimeFormat('en-CA', {timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit', day: '2-digit'});
const hojeLocal = () => FORMATO_DIA.format(new Date());
const diaDaSemana = data => (new Date(data + 'T12:00:00Z').getUTCDay() + 6) % 7;
const num = n => Number(n).toLocaleString('pt-BR', {maximumFractionDigits: 1});
function normalizar(dados, guardado = false) {
  // Tolera servidor antigo durante a troca de versão e a virada do dia no painel guardado.
  dados.densidade ||= {concluidas: 0, feitas: 0, total: 0, proxima: null, materias: [], base: ''};
  dados.densidade.pendentes ||= dados.densidade.proxima ? [dados.densidade.proxima] : [];
  dados.estudo ||= {data: hojeLocal(), hoje: {respostas: 0, acertos: 0}, semana: [0, 0, 0, 0, 0, 0, 0], diaDaSemana: diaDaSemana(hojeLocal()), revisao: {vencidas: [], caderno: 0, intervalos: [1, 3, 7]}};
  dados.indice ||= {materias: [], curtas: [], conjuntos: []};
  dados.perfil ||= {assuntos: [], mediaGeral: null, atualizada: '', periodo: ''};
  dados.progresso ||= {total: 0, acertos: 0};
  // Só o painel guardado no aparelho envelhece; o que acaba de chegar do servidor vale como veio.
  if (guardado && dados.estudo.data < hojeLocal()) {
    const dia = diaDaSemana(hojeLocal());
    if (dia < dados.estudo.diaDaSemana || Date.parse(hojeLocal()) - Date.parse(dados.estudo.data) > 6 * 86400000) dados.estudo.semana = [0, 0, 0, 0, 0, 0, 0];
    Object.assign(dados.estudo, {data: hojeLocal(), hoje: {respostas: 0, acertos: 0}, diaDaSemana: dia});
  }
  return dados;
}
function guardarPainel() { guarda.gravar(CHAVES.painel, {...painel, questoes: undefined, inicial: undefined}); }
function receberPainel(dados) {
  painel = normalizar(dados);
  carregarPrefs();
  if (simulado && simulado.conta !== painel.conta.id) { simulado = null; guarda.apagar(CHAVES.simulado); enviosSimulado.clear(); }
  if (painel.inicial) { lembrarQuestao(painel.inicial); if (!estado.atual) estado.primeira = painel.inicial.id; }
  guardarPainel();
  menu.hidden = false; document.body.classList.remove('sem-sessao');
  acertarAlvo();
}
function acertarAlvo() {
  const respostas = painel.estudo.hoje.respostas;
  if (!prefs.alvo || prefs.alvo.data !== painel.estudo.data) prefs.alvo = {data: painel.estudo.data, valor: prefs.meta};
  if (respostas < prefs.meta) prefs.alvo.valor = prefs.meta;
  salvarPrefs();
}
async function atualizar() {
  // Painel pedido antes de uma resposta chegar já nasce velho: descarta e pede de novo.
  for (let tentativa = 0; tentativa < 3; tentativa++) {
    const versao = estado.versao; const dados = await api('/api/painel');
    if (versao === estado.versao) return receberPainel(dados);
  }
}
function aplicarResultado(r) {
  estado.versao++;
  if (r.acompanhamento) { painel.densidade = r.acompanhamento.densidade; painel.perfil = r.acompanhamento.perfil; }
  if (r.progresso) painel.progresso = r.progresso;
  if (r.estudo) painel.estudo = r.estudo;
  painel.inicial = null;
  normalizar(painel); guardarPainel();
}
function lembrarQuestao(q) {
  questoes.set(q.id, q);
  // Guarda poucas questões sem figura: a primeira do próximo dia abre sem esperar a rede.
  if (!(q.grupoQuestoes || [q]).some(item => (item.imagens || []).length)) {
    const salvas = (guarda.ler(CHAVES.questoes) || []).filter(x => x.id !== q.id);
    salvas.push(q);
    guarda.gravar(CHAVES.questoes, salvas.slice(-8));
  }
}
async function obterQuestao(id) {
  if (!questoes.has(id)) lembrarQuestao(await api('/api/questoes/' + id));
  return questoes.get(id);
}
const itensDe = q => q.grupoQuestoes || [q];
// O intermediário limita os pedidos por minuto de cada rede: no limite, espera e tenta de novo em vez de falhar.
async function parteDaFigura(id, indice, parte) {
  for (let tentativa = 0; ; tentativa++) {
    try { return await api('/api/questoes/' + id, {acao: 'imagem', indice, parte}); }
    catch (e) { if (e.status !== 429 || tentativa >= 3) throw e; await new Promise(r => setTimeout(r, 5000 * (tentativa + 1))); }
  }
}
function carregarImagem(item, indice) {
  const info = item.imagens[indice];
  const chave = info.hash || `${item.id}-${indice}`;
  if (!imagens.has(chave)) {
    const promessa = (async () => {
      const blocos = [];
      for (let inicio = 0; inicio < info.partes; inicio += 5) {
        const partes = await Promise.all(Array.from({length: Math.min(5, info.partes - inicio)}, (_, j) => parteDaFigura(item.id, indice, inicio + j)));
        partes.forEach(parte => blocos.push(parte.bloco));
      }
      return 'data:image/png;base64,' + blocos.join('');
    })();
    promessa.catch(() => imagens.delete(chave));
    imagens.set(chave, promessa);
    if (imagens.size > 14) imagens.delete(imagens.keys().next().value);
  }
  return imagens.get(chave);
}
// Deixa a próxima questão e as figuras dela prontas enquanto a atual é lida.
async function adiantar(id) {
  try {
    const q = await obterQuestao(id);
    for (const item of itensDe(q)) (item.imagens || []).forEach((_, i) => carregarImagem(item, i).catch(() => {}));
  } catch { /* Sem pressa: a questão é pedida de novo quando for a vez dela. */ }
}

// ---------- Fila de estudo ----------
function idsDoFoco(foco) {
  const ids = new Set();
  for (const m of painel.indice.materias) if (m.nome === foco.materia) for (const t of m.topicos) if (!foco.topico || t.nome === foco.topico) t.ids.forEach(i => ids.add(i));
  return ids;
}
function filaDeEstudo() {
  const feita = i => estado.feitasSessao.has(i);
  let novas = (painel.densidade.pendentes || []).filter(i => !feita(i));
  let revisoes = (painel.estudo.revisao.vencidas || []).filter(i => !feita(i));
  if (prefs.foco) {
    const ids = idsDoFoco(prefs.foco);
    novas = novas.filter(i => ids.has(i)); revisoes = revisoes.filter(i => ids.has(i));
    // Assunto já percorrido nesta densidade: permite refazer, deixando de fora o que acabou de ser feito.
    if (!novas.length) novas = [...ids].filter(i => !feita(i) && !revisoes.includes(i));
  }
  if (estado.modo === 'revisao') novas = [];
  let fila = []; let r = 0, n = 0;
  // Uma revisão a cada duas questões novas: os erros voltam sem tomar a sessão inteira.
  while (r < revisoes.length || n < novas.length) {
    if (r < revisoes.length) fila.push(revisoes[r++]);
    for (let k = 0; k < 2 && n < novas.length; k++) fila.push(novas[n++]);
  }
  fila = [...new Set(fila)];
  if (estado.primeira && fila.includes(estado.primeira)) fila = [estado.primeira, ...fila.filter(i => i !== estado.primeira)];
  return [...fila.filter(i => !estado.puladas.has(i)), ...fila.filter(i => estado.puladas.has(i))];
}
function aquecimento() {
  const curtas = new Set(painel.indice.curtas);
  return (painel.densidade.pendentes || []).find(i => curtas.has(i)) ?? null;
}

// ---------- Tela ----------
function tela(html) {
  pararRelogio(); estado.aoTeclar = null; estado.atual = null; estado.vez++;
  informar(''); conteudo.innerHTML = html;
  conteudo.classList.remove('entrou'); void conteudo.offsetWidth; conteudo.classList.add('entrou');
}
function subir() { window.scrollTo(0, 0); }
// Botão que vira: o rótulo sai girando e uma cópia entra por baixo (só com ponteiro fino ou foco pelo teclado, regras no estilo.css).
// A cópia tem aria-hidden e fica com visibility: hidden fora do movimento, então nem o nome acessível nem o innerText duplicam.
// Fica fora da folha da questão e do marco da meta: nas telas de estudo nenhum movimento passa de 0,4 s.
const VIRA = 'button:not(.discreto):not(.texto-botao):not(.ficha), a.botao:not(.discreto), #menu a > span';
function prepararViradas(raiz) {
  for (const alvo of raiz.querySelectorAll(VIRA)) {
    if (alvo.closest('.questao, .marco') || alvo.childNodes.length !== 1 || alvo.firstChild.nodeType !== Node.TEXT_NODE) continue;
    const texto = alvo.textContent.trim(); if (!texto) continue;
    const vira = document.createElement('span'); vira.className = 'vira';
    const primeiro = document.createElement('span'); primeiro.className = 'vira-a'; primeiro.textContent = texto;
    const segundo = document.createElement('span'); segundo.className = 'vira-b'; segundo.setAttribute('aria-hidden', 'true'); segundo.textContent = texto;
    vira.append(primeiro, segundo); alvo.replaceChildren(vira);
  }
}
new MutationObserver(() => prepararViradas(conteudo)).observe(conteudo, {childList: true, subtree: true});
prepararViradas(menu);
const anuncio = document.createElement('p'); anuncio.id = 'anuncio'; anuncio.className = 'oculto'; anuncio.setAttribute('role', 'status'); anuncio.setAttribute('aria-live', 'polite'); document.body.append(anuncio);
function anunciar(texto) { anuncio.textContent = ''; setTimeout(() => { anuncio.textContent = texto; }, 60); }
const mostrar = elemento => elemento?.scrollIntoView({block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
function marcarMenu(destino) { $$('a', menu).forEach(a => { if (a.hash === destino) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); }); }

// ---------- Entrada ----------
const DEMONSTRACAO = {
  id: 0, materia: 'Física', titulo: 'Enem 2024 · Questão 106', correta: 3, imagens: [],
  fonte: 'https://download.inep.gov.br/enem/provas_e_gabaritos/2024_PV_impresso_D2_CD7.pdf',
  enunciado: 'Em aeroportos, por razões de segurança, os passageiros devem ter suas bagagens de mão examinadas antes do embarque, passando-as em esteiras para sua inspeção por aparelhos de raios X. Nessas inspeções, os passageiros são orientados a retirar seus computadores portáteis (notebooks ou laptops) de malas, mochilas ou bolsas para passá-los isoladamente pela esteira.\n\nQue explicação física justifica esse procedimento?',
  alternativas: [
    'Os raios X não interagem com os componentes metálicos do computador, o que impede a formação de imagens.',
    'Os raios X desmagnetizam o disco rígido do computador, quando refratados pelos componentes metálicos das bagagens de mão.',
    'Os raios X aquecem os materiais metálicos encontrados em bagagens de mão, quando refletidos pelos componentes do computador.',
    'Os raios X não atravessam os componentes densos do computador, o que impede a visualização de objetos que estão à frente ou atrás deles.',
    'Os raios X ionizam os materiais metálicos normalmente encontrados em bagagens de mão, quando difratados pelos componentes do computador.'
  ]
};
// Página de entrada (direção de 14/11/2026). O texto da apresentação mora no index.html, num bloco igual nos dois arquivos
// (o teste confere), para a busca ler sem JavaScript. O bloco fica escondido até aqui: com sessão guardada, a questão abre
// sem mostrar a apresentação antes. O molde é lido uma vez, antes de qualquer tela; os lugares com data-lugar são
// preenchidos abaixo (faixa que corre, questão de demonstração, provas no ar e formulário).
const MOLDE_ENTRADA = (() => {
  const bloco = conteudo.querySelector('.entrada[data-estatica]'); if (!bloco) return '';
  const copia = bloco.cloneNode(true); copia.removeAttribute('data-estatica'); return copia.outerHTML;
})();
// Sem o bloco (index.html antigo), a entrada fica só com o título, a demonstração e o formulário.
const MOLDE_RESERVA = `<div class="entrada"><div class="faixa faixa-papel"><section class="apresentacao" id="apresentacao"><h1>Estude para o Enem uma questão por vez.</h1></section></div>
<div data-lugar="faixa-que-corre"></div><div class="faixa faixa-areia"><section class="experimente" id="experimente"><h2 id="titulo-experimente">Experimente uma questão</h2><div data-lugar="demonstracao"></div></section></div>
<div class="faixa faixa-sol-claro"><section class="chamada" id="entrar"><div class="formulario" data-lugar="formulario"></div></section></div></div>`;
// Provas no ar: fonte única da lista "Provas no PU" da entrada. Conferido em 14/11/2026 no catálogo publicado (.catalogo/atual.json):
// 356 questões, Enem 2024 (179) e Enem 2025 (177). Uma edição só entra aqui depois de publicada no catálogo.
const PROVAS_NO_AR = [{prova: 'Enem', edicao: 2024, questoes: 179}, {prova: 'Enem', edicao: 2025, questoes: 177}];
function provasHtml() {
  const total = PROVAS_NO_AR.reduce((soma, p) => soma + p.questoes, 0);
  return `<p class="numero-cartaz"><strong>${total.toLocaleString('pt-BR')}</strong><span>questões oficiais no banco</span></p>
<ul class="provas-lista">${PROVAS_NO_AR.map(p => `<li><strong>${escapar(p.prova)} ${p.edicao}</strong><span>${plural(p.questoes, 'questão', 'questões')}</span></li>`).join('')}</ul>`;
}
// Faixa que corre: frases que a entrada já diz, em caixa alta com até três palavras (identidade de 14/11/2026).
// A cópia fica fora da leitura de tela; parada com movimento reduzido.
const FRASES_FAIXA = ['Questões oficiais', 'Uma por vez', 'Revisão espaçada', 'Meta pequena', 'Simulado curto', 'Progresso por matéria'];
function faixaQueCorre() {
  const lista = copia => `<ul class="frases"${copia ? ' aria-hidden="true"' : ' aria-label="O que o PU oferece"'}>${[...FRASES_FAIXA, ...FRASES_FAIXA].map(f => `<li>${f}</li>`).join('')}</ul>`;
  // Botão de pausa: no celular não há ponteiro para parar a faixa (WCAG 2.2.2).
  return `<div class="faixa-corre"><div class="trilho">${lista(false)}${lista(true)}</div><button type="button" class="discreto pausar-faixa" aria-pressed="false">Pausar</button></div>`;
}
// Cerca de 40 px por segundo, qualquer que seja a largura das frases.
function ajustarFaixa() { const trilho = $('.trilho'); if (trilho) trilho.style.animationDuration = `${Math.max(20, trilho.firstElementChild.offsetWidth / 40).toFixed(1)}s`; }
window.addEventListener('resize', ajustarFaixa);
function preencherLugar(nome, html, trocar = false) { const lugar = $(`#conteudo [data-lugar="${nome}"]`); if (!lugar) return null; if (trocar) { lugar.outerHTML = html; return null; } lugar.innerHTML = html; return lugar; }
// Leva ao formulário (link "Entrar" do topo, #entrar, #criar-conta e ?criar-conta) e põe o foco no primeiro campo.
function irAoFormulario() {
  // Salto direto: a página é longa e a rolagem suave levaria mais de um segundo.
  $('#entrar')?.scrollIntoView({block: 'start'});
  $('#acesso input')?.focus({preventScroll: true});
}
function verEntrada({rolar = false} = {}) {
  menu.hidden = true; document.body.classList.add('sem-sessao');
  // Já na entrada, só o formulário muda: a questão de demonstração respondida e a posição da página ficam.
  if (!$('#conteudo > .entrada:not([data-estatica])')) {
    tela(MOLDE_ENTRADA || MOLDE_RESERVA);
    preencherLugar('faixa-que-corre', faixaQueCorre(), true);
    preencherLugar('provas', provasHtml());
    desenharDemonstracao();
    ajustarFaixa(); document.fonts?.ready.then(ajustarFaixa);
    const pausar = $('.pausar-faixa');
    if (pausar) pausar.onclick = () => { const parada = pausar.getAttribute('aria-pressed') !== 'true'; pausar.setAttribute('aria-pressed', String(parada)); pausar.textContent = parada ? 'Seguir' : 'Pausar'; $('.faixa-corre').classList.toggle('parada', parada); };
  }
  desenharFormulario();
  if (rolar) irAoFormulario();
}
function desenharDemonstracao() {
  const q = DEMONSTRACAO;
  const lugar = preencherLugar('demonstracao', `<p class="rotulo">${escapar(q.materia)} · ${escapar(q.titulo)} · demonstração, não fica registrada</p>
<div class="enunciado">${enunciadoHtml(q.enunciado, q)}</div>
<fieldset id="demonstracao"><legend>Toque na alternativa que você marcaria</legend>${q.alternativas.map((a, i) => `<label class="alternativa"><input type="radio" name="demonstracao" value="${i}"><span class="letra">${letra(i)}</span><span class="texto">${escapar(a)}</span></label>`).join('')}</fieldset>
<div id="retorno-demonstracao" class="retorno" aria-live="polite"></div>
<p class="fonte"><a href="${escapar(q.fonte)}" target="_blank" rel="noopener noreferrer">Prova original no site do Inep</a></p>`);
  if (!lugar) return;
  $('#demonstracao').onchange = evento => {
    const escolhida = Number(evento.target.value); const campo = $('#demonstracao');
    $$('.alternativa', campo).forEach((alternativa, i) => { if (i === q.correta) alternativa.dataset.correcao = 'correta'; else if (i === escolhida) alternativa.dataset.correcao = 'errada'; });
    campo.disabled = true;
    const certa = escolhida === q.correta;
    $('#retorno-demonstracao').innerHTML = `<p class="${certa ? 'acerto' : 'engano'}"><strong>${certa ? 'Certa!' : `Não foi essa. A certa é a ${letra(q.correta)}.`}</strong> ${certa ? 'No PU, cada resposta entra no seu progresso por matéria e assunto.' : 'No PU, uma questão errada volta na revisão no dia seguinte, até você acertar com segurança.'}</p><button type="button" id="quero-conta">Criar minha conta</button>`;
    // O rádio com foco ficou desativado: o foco vai para o retorno, que o leitor de tela lê em seguida.
    $('#retorno-demonstracao').setAttribute('tabindex', '-1'); $('#retorno-demonstracao').focus({preventScroll: true});
    $('#quero-conta').onclick = () => { cadastro = true; desenharFormulario(); irAoFormulario(); };
  };
}
function desenharFormulario() {
  const indisponivel = publico && !conexao.habilitado;
  // Trocar entre entrar e criar conta não apaga o que já foi digitado.
  const digitado = {nome: $('#nome')?.value || '', email: $('#email')?.value || ''};
  if (!preencherLugar('formulario', `<h3 id="titulo-acesso">${cadastro ? 'Crie sua conta' : 'Entre para estudar'}</h3>
${indisponivel ? '<p class="nota" role="status">O acesso público está em configuração. Ainda não é possível entrar.</p>' : ''}
<form id="acesso" aria-labelledby="titulo-acesso">
${cadastro ? '<label for="nome">Como você se chama?</label><input id="nome" name="nome" autocomplete="name" minlength="2" maxlength="80" required>' : ''}
<label for="email">E-mail</label><input id="email" name="email" type="${cadastro ? 'email' : 'text'}" autocomplete="username" maxlength="232" spellcheck="false" autocapitalize="none" required>
<label for="senha">Senha</label><input id="senha" name="senha" type="password" autocomplete="${cadastro ? 'new-password' : 'current-password'}" minlength="${cadastro ? 12 : 1}" maxlength="128" required>
<small>${cadastro ? 'Use de 12 a 128 caracteres. Uma frase curta funciona bem.' : 'Este aparelho continua conectado por 30 dias.'}</small>
<button type="submit" ${indisponivel ? 'disabled' : ''}>${cadastro ? 'Criar conta' : 'Entrar'}</button>
<p id="erro-acesso" class="erro-campo" role="alert"></p>
</form>
<button class="discreto troca" id="trocar" type="button">${cadastro ? 'Já tenho uma conta' : 'Quero criar uma conta'}</button>`)) return;
  for (const [campo, valor] of Object.entries(digitado)) { const e = $('#' + campo); if (e && valor) e.value = valor; }
  $('#trocar').onclick = () => { cadastro = !cadastro; desenharFormulario(); $('#acesso input').focus(); };
  $('#acesso').onsubmit = async evento => {
    evento.preventDefault();
    const form = evento.currentTarget; const botao = $('button', form); const campoErro = $('#erro-acesso');
    botao.disabled = true; botao.setAttribute('aria-busy', 'true'); campoErro.textContent = ''; botao.textContent = cadastro ? 'Criando conta…' : 'Entrando…';
    try {
      const entrada = await api(cadastro ? '/api/cadastro' : '/api/entrar', {...Object.fromEntries(new FormData(form)), dispositivo, nomeDispositivo: 'Meu navegador'});
      if (entrada.iniciando) tela('<p class="espera" role="status">Preparando seu espaço de estudo…</p>');
      if (entrada.painel) receberPainel(entrada.painel); else await atualizar();
      if (entrada.iniciando && !publico && location.pathname !== '/site/') { location.assign('/site/' + location.hash); return; }
      navegar();
    } catch (e) {
      if (!$('#erro-acesso')) verEntrada();
      $('#erro-acesso').textContent = mensagemErro(e);
      const atual = $('#acesso button'); if (atual) { atual.disabled = false; atual.removeAttribute('aria-busy'); atual.textContent = cadastro ? 'Criar conta' : 'Entrar'; }
    }
  };
}

// ---------- Estudar ----------
const DIAS = ['S', 'T', 'Q', 'Q', 'S', 'S', 'D'];
const NOMES_DIAS = ['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo'];
function ritmoHtml() {
  const e = painel.estudo; const feitas = e.hoje.respostas; const cumprida = feitas >= prefs.meta;
  // Depois da meta, só mostra um alvo novo se a pessoa pediu "Mais 5"; quem encerrou não é cobrado.
  const alvo = cumprida && prefs.alvo?.bloco ? Math.max(prefs.alvo.valor, feitas) : prefs.meta;
  const contagem = cumprida && !prefs.alvo?.bloco ? `${feitas} ${feitas === 1 ? 'questão' : 'questões'}` : `${feitas} de ${alvo}`;
  const dias = e.semana.filter(n => n > 0).length;
  return `<section class="ritmo" aria-label="Seu ritmo">
<div class="ritmo-hoje"><span class="rotulo">Hoje</span><strong>${contagem}</strong><progress max="${alvo}" value="${Math.min(feitas, alvo)}" aria-label="Questões respondidas hoje"></progress>${cumprida ? '<span class="selo certo">meta cumprida</span>' : ''}</div>
<ol class="semana" aria-label="${plural(dias, 'dia de estudo', 'dias de estudo')} nesta semana">${e.semana.map((n, i) => `<li${n > 0 ? ' data-feito' : ''}${i === e.diaDaSemana ? ' data-hoje' : ''}><span aria-hidden="true">${DIAS[i]}</span><span class="oculto">${NOMES_DIAS[i]}: ${n > 0 ? plural(n, 'questão', 'questões') : 'sem estudo'}</span></li>`).join('')}</ol>
</section>`;
}
function modosHtml() {
  const vencidas = painel.estudo.revisao.vencidas.length; const foco = prefs.foco;
  const rotuloFoco = foco ? escapar(foco.topico ? `${foco.materia}: ${foco.topico}` : foco.materia) : 'Matéria';
  const pendentes = new Set(painel.densidade.pendentes);
  return `<div class="modos" role="group" aria-label="O que treinar agora">
<button type="button" class="ficha" data-modo="misturado" aria-pressed="${estado.modo === 'misturado' && !foco}">Misturado</button>
<button type="button" class="ficha" data-modo="revisao" aria-pressed="${estado.modo === 'revisao'}">Revisão${vencidas ? ` <span class="conta">${vencidas}</span>` : ''}</button>
<button type="button" class="ficha" id="abrir-foco" aria-expanded="false" aria-controls="painel-foco"${foco ? ' data-ativo' : ''}><span class="corte">${rotuloFoco}</span></button>
</div>
<div id="painel-foco" class="painel-foco" hidden><p class="rotulo">Treinar só uma matéria. O que você fizer continua contando na sua volta pelo banco.</p><div class="lista-foco">${painel.indice.materias.map(m => { const ids = m.topicos.flatMap(t => t.ids); const faltam = ids.filter(i => pendentes.has(i)).length; return `<button type="button" class="ficha" data-materia="${escapar(m.nome)}" aria-pressed="${foco?.materia === m.nome}">${escapar(m.nome)} <span class="conta">${faltam}</span></button>`; }).join('')}</div></div>`;
}
function verEstudo() {
  tela(`<h1 class="oculto">Estudar</h1>${ritmoHtml()}${modosHtml()}<div id="area-questao"></div>`);
  ligarModos();
  abrirProxima();
}
function atualizarCabecalhoEstudo() {
  const ritmo = $('.ritmo:not(.simulado-topo)'); if (ritmo) ritmo.outerHTML = ritmoHtml();
  const modos = $('.modos'); const foco = $('#painel-foco');
  if (modos && foco) { foco.remove(); modos.outerHTML = modosHtml(); ligarModos(); }
}
function ligarModos() {
  const abrir = $('#abrir-foco'); const painelFoco = $('#painel-foco');
  $$('.modos [data-modo]').forEach(b => b.onclick = () => { estado.modo = b.dataset.modo; prefs.foco = null; salvarPrefs(); verEstudo(); });
  abrir.onclick = () => { painelFoco.hidden = !painelFoco.hidden; abrir.setAttribute('aria-expanded', String(!painelFoco.hidden)); };
  $$('[data-materia]', painelFoco).forEach(b => b.onclick = () => { const mesma = prefs.foco?.materia === b.dataset.materia && !prefs.foco.topico; prefs.foco = mesma ? null : {materia: b.dataset.materia}; estado.modo = 'misturado'; salvarPrefs(); verEstudo(); });
}
function marcoPendente() { return prefs.alvo && painel.estudo.hoje.respostas >= prefs.alvo.valor; }
function verMarco() {
  const area = $('#area-questao'); const e = painel.estudo; const vencidas = e.revisao.vencidas.length;
  const primeira = prefs.alvo.valor <= prefs.meta; const dias = e.semana.filter(n => n > 0).length;
  estado.atual = null;
  area.innerHTML = `<section class="marco"><h2>${primeira ? 'Meta de hoje cumprida.' : 'Bloco concluído.'}</h2><p>Você respondeu ${plural(e.hoje.respostas, 'questão', 'questões')} hoje e acertou ${e.hoje.acertos}. ${dias > 1 ? `É o seu ${dias}º dia de estudo nesta semana.` : ''}</p><p class="secundario">Parar aqui é uma boa escolha: o que você errou ou chutou volta na revisão nos próximos dias.${primeira && publico && !matchMedia('(display-mode: standalone)').matches ? ' Para voltar amanhã com um toque, use “Adicionar à tela inicial” no menu do navegador.' : ''}</p><div class="acoes"><button type="button" id="mais-cinco">Mais 5 questões</button>${vencidas && estado.modo !== 'revisao' ? `<button type="button" class="discreto" id="ir-revisao">Revisar ${plural(vencidas, 'questão', 'questões')}</button>` : '<a class="botao discreto" id="ir-simulado" href="#simulado">Fazer um simulado curto</a>'}<a class="botao discreto" id="encerrar" href="#progresso">Encerrar por hoje</a></div>${primeira ? '<p class="secundario lembrar">Quer um aviso para amanhã? <a href="#conta">Crie um lembrete diário</a> no calendário do celular.</p>' : ''}</section>`;
  const seguir = bloco => { prefs.alvo.valor = painel.estudo.hoje.respostas + 5; prefs.alvo.bloco = bloco; salvarPrefs(); };
  $('#mais-cinco').onclick = () => { seguir(true); verEstudo(); };
  if ($('#ir-revisao')) $('#ir-revisao').onclick = () => { seguir(true); estado.modo = 'revisao'; prefs.foco = null; salvarPrefs(); verEstudo(); };
  $('#encerrar').onclick = () => seguir(false);
  if ($('#ir-simulado')) $('#ir-simulado').onclick = () => seguir(false);
  estado.aoTeclar = evento => { if (evento.key === 'Enter' && !evento.target.closest('button,a')) { evento.preventDefault(); $('#mais-cinco').click(); } };
  $('.marco h2').tabIndex = -1; $('.marco h2').focus({preventScroll: true});
}
function semQuestoes() {
  const area = $('#area-questao'); const revisao = painel.estudo.revisao; estado.atual = null;
  if (estado.modo === 'revisao') {
    area.innerHTML = `<section class="marco"><h2>Nenhuma revisão vence agora.</h2><p>${revisao.caderno ? `Há ${plural(revisao.caderno, 'questão', 'questões')} no seu caderno de revisão. Elas voltam 1, 3 e 7 dias depois de cada tentativa.` : 'Seu caderno de revisão está vazio. Ele recebe as questões que você errar ou marcar como chute.'}</p><div class="acoes"><button type="button" id="voltar-misturado">Continuar com questões novas</button></div></section>`;
    $('#voltar-misturado').onclick = () => { estado.modo = 'misturado'; verEstudo(); };
    return;
  }
  const d = painel.densidade;
  area.innerHTML = `<section class="marco"><h2>Não há questão disponível agora.</h2><p>${d.bloqueada ? 'Uma questão desta volta saiu do banco. Seu progresso está guardado; avise quem mantém o PU.' : d.total ? 'Tente escolher outra matéria ou voltar ao modo misturado.' : 'O banco de questões ainda não foi carregado. Tente de novo mais tarde.'}</p>${prefs.foco ? '<div class="acoes"><button type="button" id="voltar-misturado">Voltar ao misturado</button></div>' : ''}</section>`;
  if ($('#voltar-misturado')) $('#voltar-misturado').onclick = () => { prefs.foco = null; salvarPrefs(); verEstudo(); };
}
async function abrirProxima() {
  const area = $('#area-questao'); if (!area) return;
  if (marcoPendente()) return verMarco();
  const fila = filaDeEstudo();
  if (!fila.length) return semQuestoes();
  const vez = ++estado.vez; const id = fila[0];
  if (!questoes.has(id)) area.innerHTML = '<div class="questao esqueleto" role="status"><span class="oculto">Carregando questão…</span><i></i><i></i><i></i><i class="curto"></i></div>';
  try {
    const q = await obterQuestao(id);
    if (vez !== estado.vez || !area.isConnected) return;
    montarQuestao(area, q, {modo: 'estudo'});
    const seguinte = filaDeEstudo().find(i => !itensDe(q).some(item => item.id === i));
    if (seguinte !== undefined) adiantar(seguinte);
  } catch (e) {
    if (vez !== estado.vez || !area.isConnected) return;
    area.innerHTML = `<section class="marco"><h2>Não foi possível abrir a questão.</h2><p>${escapar(mensagemErro(e))}</p><div class="acoes"><button type="button" id="tentar">Tentar novamente</button></div></section>`;
    $('#tentar').onclick = abrirProxima;
  }
}
const novoEnvio = () => crypto.randomUUID ? crypto.randomUUID() : Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('') + '-envio';

/* Monta a folha da questão. Modos: 'estudo' (confere na hora), 'simulado' (segue sem correção) e 'rever' (somente leitura). */
function montarQuestao(area, q, opcoes) {
  const itens = itensDe(q); const conjunto = Boolean(q.grupo); const modo = opcoes.modo;
  const emRevisao = modo === 'estudo' && itens.some(item => painel.estudo.revisao.vencidas.includes(item.id));
  const temImagens = itens.some(item => item.imagens?.length);
  const pergunta = item => `<section class="pergunta" data-questao="${item.id}">${conjunto ? `<h3>${escapar(item.titulo)}</h3>` : ''}<div class="enunciado">${enunciadoHtml(item.enunciado, item)}</div><fieldset data-resposta="${item.id}"><legend class="oculto">Alternativas${conjunto ? ` da ${escapar(item.titulo)}` : ''}</legend>${item.alternativas.map((a, i) => `<label class="alternativa"><input type="radio" name="alternativa-${item.id}" value="${i}"><span class="letra">${letra(i)}</span><span class="texto">${alternativaHtml(a, item)}</span></label>`).join('')}</fieldset><div class="correcao" data-correcao-de="${item.id}"></div></section>`;
  const barra = modo === 'estudo' ? '<button type="button" class="discreto" id="chutei" disabled>Chutei</button><button type="submit" class="primaria" id="conferir" disabled>Conferir</button>'
    : modo === 'simulado' ? `<button type="submit" class="primaria" id="conferir" disabled>${opcoes.ultima ? 'Responder e terminar' : 'Responder e seguir'}</button>`
    : '<button type="button" class="primaria" id="voltar-resultado">Voltar ao resultado</button>';
  area.innerHTML = `<article class="questao" data-id="${q.id}">
<header class="questao-topo"><p class="rotulo">${escapar(q.materia || q.area)} · ${escapar(conjunto ? `${itens.length} perguntas com o mesmo texto` : q.titulo)}${emRevisao ? ' <span class="selo revisao">revisão</span>' : ''}${opcoes.rotulo ? ` <span class="selo">${escapar(opcoes.rotulo)}</span>` : ''}</p>${modo === 'estudo' ? '<button type="button" class="texto-botao" id="pular">Pular</button>' : ''}</header>
${conjunto ? '<p class="secundario">Leia o texto e marque uma resposta em cada pergunta. O envio é conjunto; cada pergunta conta separadamente.</p>' : ''}
${q.textoComum ? `<div class="texto-comum enunciado">${enunciadoHtml(q.textoComum, q)}</div>` : ''}
<form id="responder" novalidate>${itens.map(pergunta).join('')}
${temImagens ? '<div class="originais"><p id="estado-original" class="secundario" role="status"></p><div id="imagens-originais"></div></div>' : ''}
<div id="retorno" class="retorno" aria-live="polite"></div>
<div class="barra-acao">${barra}</div></form></article>`;
  const form = $('#responder', area); const retorno = $('#retorno', area);
  const conferir = $('#conferir', area); const chutei = $('#chutei', area);
  const envio = opcoes.envio || novoEnvio();
  let figurasProntas = !temImagens; let enviando = false; let enviadas = null;
  estado.atual = {id: q.id, ids: itens.map(item => item.id)};
  const marcada = item => { const m = $(`input[name="alternativa-${item.id}"]:checked`, form); return m ? Number(m.value) : null; };
  const completo = () => itens.every(item => marcada(item) !== null);
  const liberar = () => { const pronto = completo() && figurasProntas && !enviando; if (conferir) conferir.disabled = !pronto; if (chutei) chutei.disabled = !pronto; };
  // Devolve a marcação feita antes de trocar de página ou de a rede falhar.
  if (modo !== 'rever') for (const item of itens) { const antes = estado.marcadas[item.id]; if (Number.isInteger(antes)) { const campo = $(`input[name="alternativa-${item.id}"][value="${antes}"]`, form); if (campo) campo.checked = true; } }
  const carregarFiguras = async () => {
    const destino = $('#imagens-originais', area); const situacao = $('#estado-original', area);
    try {
      situacao.textContent = 'Carregando as figuras…'; destino.replaceChildren();
      for (const item of itens) for (let indice = 0; indice < (item.imagens?.length || 0); indice++) {
        const endereco = await carregarImagem(item, indice);
        if (!destino.isConnected) return;
        const nova = () => { const imagem = document.createElement('img'); imagem.alt = `Figura, tabela ou fórmula da ${item.titulo}`; imagem.src = endereco; return imagem; };
        const lugares = $$(`[data-midia="${item.id}-${indice}"]`, area);
        lugares.forEach(lugar => lugar.replaceChildren(nova()));
        if (!lugares.length && item.extrator !== 2) destino.append(nova());
      }
      situacao.textContent = ''; figurasProntas = true; liberar();
    } catch {
      if (!situacao.isConnected) return;
      situacao.textContent = 'Não foi possível carregar as figuras. ';
      const tentar = document.createElement('button'); tentar.type = 'button'; tentar.className = 'texto-botao'; tentar.textContent = 'Tentar novamente'; tentar.onclick = () => void carregarFiguras(); situacao.append(tentar);
    }
  };
  if (temImagens) void carregarFiguras();

  if (modo === 'rever') {
    for (const item of itens) marcarCorrecao(area, item.id, opcoes.corrigida[item.id]);
    $$('fieldset', form).forEach(campo => campo.disabled = true);
    $('#voltar-resultado', area).onclick = opcoes.aoVoltar;
    return;
  }
  form.onchange = evento => { const campo = evento.target.closest('input[type=radio]'); if (campo && !enviadas) { estado.marcadas[Number(campo.name.split('-')[1])] = Number(campo.value); liberar(); } };
  liberar();
  estado.aoTeclar = evento => {
    if (evento.target.closest('input:not([type=radio]),textarea,select,[contenteditable]')) return;
    const indice = prefs.atalhos !== false && evento.key.length === 1 ? 'abcde'.indexOf(evento.key.toLowerCase()) : -1;
    if (indice >= 0 && !evento.ctrlKey && !evento.metaKey && !evento.altKey) {
      const campo = $$('fieldset:not(:disabled)', form).find(c => !$('input:checked', c)) || $('fieldset:not(:disabled)', form);
      const alvo = campo && $$('input', campo)[indice];
      if (alvo && !alvo.disabled) { alvo.checked = true; alvo.dispatchEvent(new Event('change', {bubbles: true})); alvo.focus({preventScroll: true}); }
    } else if (evento.key === 'Enter' && !evento.target.closest('button,a')) {
      const principal = $('.barra-acao .primaria:not(:disabled)', area);
      if (principal) { evento.preventDefault(); principal.click(); }
    }
  };
  if (modo === 'simulado') {
    form.onsubmit = evento => { evento.preventDefault(); if (!completo() || !figurasProntas) return; delete estado.marcadas[q.id]; opcoes.aoResponder(marcada(q), envio); };
    return;
  }
  $('#pular', area).onclick = () => { itens.forEach(item => estado.puladas.add(item.id)); if (estado.primeira === q.id) estado.primeira = null; subir(); abrirProxima(); };
  const enviar = async chute => {
    if (enviando || !completo() || !figurasProntas) return;
    som.preparar();   // ainda dentro do gesto: a correção chega depois, pela rede
    enviando = true; liberar(); conferir.textContent = 'Conferindo…'; conferir.classList.add('esperando'); retorno.textContent = '';
    enviadas ??= itens.map(item => ({id: item.id, alternativa: marcada(item)}));
    // Depois do primeiro envio a alternativa fica travada: se a resposta chegou ao servidor, o reenvio é o mesmo.
    $$('fieldset', form).forEach(campo => campo.disabled = true);
    // Pede junto a primeira questão da fila que ainda não chegou: a seguinte costuma já estar adiantada.
    const resto = filaDeEstudo().filter(i => !estado.atual.ids.includes(i));
    const proxima = resto.slice(0, 3).find(i => !questoes.has(i));
    try {
      const corpo = conjunto ? {respostas: enviadas, envio, chute} : {alternativa: enviadas[0].alternativa, envio, chute};
      if (proxima !== undefined) corpo.proxima = proxima;
      const r = await api('/api/questoes/' + q.id, corpo);
      if (r.proximaQuestao) lembrarQuestao(r.proximaQuestao);
      itens.forEach(item => { estado.feitasSessao.add(item.id); estado.puladas.delete(item.id); delete estado.marcadas[item.id]; });
      if (estado.primeira === q.id) estado.primeira = null;
      aplicarResultado(r);
      if (!form.isConnected) return;
      atualizarCabecalhoEstudo();
      const quente = aquecimento(); if (quente !== null && !questoes.has(quente)) adiantar(quente);
      corrigir(r.resultados || [{...r, id: q.id}], chute);
    } catch (e) {
      // A mesma chave de envio segue valendo: se a resposta chegou ao servidor, ela não é contada de novo.
      enviando = false;
      if (!form.isConnected) return;
      conferir.textContent = 'Conferir'; conferir.classList.remove('esperando'); liberar();
      retorno.innerHTML = `<p class="engano"><strong>Sua resposta não foi enviada.</strong> ${escapar(mensagemErro(e))} A alternativa marcada está guardada: toque em Conferir de novo.</p>`;
      anunciar('Sua resposta não foi enviada. Toque em Conferir de novo.'); mostrar(retorno);
    }
  };
  form.onsubmit = evento => { evento.preventDefault(); void enviar(false); };
  chutei.onclick = () => {
    if (!prefs.dicaChute) { prefs.dicaChute = true; salvarPrefs(); }
    void enviar(true);
  };
  if (!prefs.dicaChute) retorno.innerHTML = '<p class="dica">Sem certeza? Use <strong>Chutei</strong>: se acertar no chute, a questão volta na revisão mesmo assim.</p>';

  function corrigir(resultados, chute) {
    const barraAcao = $('.barra-acao', area);
    const seguir = () => {
      barraAcao.innerHTML = '<button type="button" class="primaria" id="proxima">Próxima questão</button>';
      $('#proxima', area).onclick = () => { subir(); abrirProxima(); };
      $('#proxima', area).focus({preventScroll: true});
    };
    const assuntoDe = item => item.topico ? `<p class="secundario">Assunto: ${escapar(item.topico)}.${item.conteudo ? ` Conteúdo cobrado: ${escapar(item.conteudo)}.` : ''}</p>` : '';
    const mais = item => item.materia && item.topico && idsDoFoco({materia: item.materia, topico: item.topico}).size > 1 ? `<button type="button" class="texto-botao" data-treinar="${item.id}">Treinar mais deste assunto</button>` : '';
    const ligarTreino = () => $$('[data-treinar]', area).forEach(b => b.onclick = () => { const item = itens.find(x => x.id === Number(b.dataset.treinar)); prefs.foco = {materia: item.materia, topico: item.topico}; estado.modo = 'misturado'; salvarPrefs(); subir(); verEstudo(); });
    const revelar = (resultado, item, cabecalho) => {
      const secao = $(`[data-questao="${item.id}"]`, form);
      $('fieldset', secao).disabled = true;
      marcarCorrecao(area, item.id, {escolhida: enviadas.find(x => x.id === item.id).alternativa, correta: resultado.correta});
      const seguro = resultado.acerto && !chute;
      const comentada = resultado.explicacao && !SEM_SOLUCAO.test(resultado.explicacao);
      $('.correcao', secao).innerHTML = `${cabecalho}${comentada ? `<p class="explicacao">${escapar(resultado.explicacao)}</p>` : seguro ? '' : `<p>Ainda não há solução comentada para esta questão. Tente dizer, em uma frase, por que a ${letra(resultado.correta)} responde ao que foi pedido. Se não fizer sentido, veja uma resolução:</p>${buscaResolucao(item)}`}${seguro ? '' : '<p class="secundario">Ela volta na sua revisão amanhã.</p>'}${assuntoDe(item)}${seguro ? '' : mais(item)}`;
      ligarTreino();
    };
    retorno.textContent = '';
    if (conjunto) {
      for (const resultado of resultados) { const item = itens.find(x => x.id === resultado.id); revelar(resultado, item, `<p class="${resultado.acerto ? 'acerto' : 'engano'}"><strong>${resultado.acerto ? 'Certa!' : `Não foi essa. A certa é a ${letra(resultado.correta)}.`}</strong></p>`); }
      som.tocar(resultados.every(r => r.acerto) ? 'acerto' : 'erro');
      anunciar(`Você acertou ${resultados.filter(r => r.acerto).length} de ${resultados.length} perguntas. A correção está abaixo de cada uma.`);
      seguir(); return mostrar($('.correcao', form));
    }
    const resultado = resultados[0]; const item = itens[0]; const secao = $(`[data-questao="${item.id}"]`, form); const campo = $('fieldset', secao);
    if (resultado.acerto) {
      revelar(resultado, item, `<p class="acerto"><strong>Certa!</strong>${chute ? ' Como foi chute, ela ainda passa pela revisão.' : ''}</p>`);
      som.tocar('acerto');
      anunciar(chute ? 'Certa! Como foi chute, ela ainda passa pela revisão.' : 'Certa!');
      seguir(); return mostrar($('.correcao', secao));
    }
    // Segunda tentativa antes de ver o gabarito: pensar de novo fixa mais do que só ler a resposta. Não é registrada.
    const escolhida = enviadas[0].alternativa;
    $$('.alternativa', secao)[escolhida].dataset.correcao = 'errada';
    campo.disabled = false;
    $$('input', campo).forEach((entrada, i) => { entrada.checked = false; entrada.disabled = i === escolhida; });
    $('.correcao', secao).innerHTML = '<p class="engano"><strong>Não foi essa.</strong> Quer tentar outra antes de ver a resposta? Toque numa alternativa (não muda o seu resultado) ou em Ver resposta.</p>';
    barraAcao.innerHTML = '<button type="button" class="primaria" id="ver-resposta">Ver resposta</button>';
    som.tocar('erro');
    anunciar('Não foi essa. Escolha outra alternativa para tentar mais uma vez, ou veja a resposta.');
    mostrar($('.correcao', secao)); $('input:not(:disabled)', campo)?.focus({preventScroll: true});
    const fechar = segunda => {
      form.onchange = null;
      const agora = segunda === resultado.correta;
      // Segunda tentativa: a correção também aparece na hora. "Ver resposta" não toca de novo.
      if (segunda !== null) som.tocar(agora ? 'acerto' : 'erro');
      revelar(resultado, item, agora ? `<p class="acerto"><strong>Agora sim: é a ${letra(resultado.correta)}.</strong></p>` : `<p class="engano"><strong>${segunda === null ? '' : 'Também não. '}A certa é a ${letra(resultado.correta)}.</strong></p>`);
      $$('input', campo).forEach(entrada => { entrada.checked = false; });
      anunciar(agora ? `Agora sim: é a ${letra(resultado.correta)}.` : `A certa é a ${letra(resultado.correta)}. Ela volta na sua revisão amanhã.`);
      seguir(); mostrar($('.correcao', secao));
    };
    form.onchange = evento => { const entrada = evento.target.closest('input[type=radio]'); if (entrada) fechar(Number(entrada.value)); };
    $('#ver-resposta', area).onclick = () => fechar(null);
  }
}
function marcarCorrecao(area, id, {escolhida, correta}) {
  const secao = $(`[data-questao="${id}"]`, area);
  $$('.alternativa', secao).forEach((alternativa, indice) => {
    if (indice !== correta && indice !== escolhida) return;
    alternativa.dataset.correcao = indice === correta ? 'correta' : 'errada';
    if ($('.legenda', alternativa)) return;
    const legenda = document.createElement('small'); legenda.className = 'legenda';
    legenda.textContent = indice === correta ? (indice === escolhida ? 'Sua resposta, certa' : 'Resposta certa') : 'Sua resposta';
    $('.texto', alternativa).append(legenda);
  });
}

// ---------- Simulado ----------
const TAMANHO_SIMULADO = 10;
const salvarSimulado = () => { if (simulado) guarda.gravar(CHAVES.simulado, simulado); else guarda.apagar(CHAVES.simulado); };
const tempo = segundos => `${String(Math.floor(segundos / 60)).padStart(2, '0')}:${String(segundos % 60).padStart(2, '0')}`;
function pararRelogio() { if (relogio) { clearInterval(relogio); relogio = null; salvarSimulado(); } }
function sortearSimulado() {
  const conjuntos = new Set(painel.indice.conjuntos); const areaDe = new Map();
  for (const m of painel.indice.materias) for (const t of m.topicos) for (const id of t.ids) areaDe.set(id, m.area);
  const pendentes = (painel.densidade.pendentes || []).filter(i => !conjuntos.has(i));
  const outras = [...areaDe.keys()].filter(i => !conjuntos.has(i) && !pendentes.includes(i));
  const porArea = new Map();
  for (const id of [...pendentes, ...outras]) { const area = areaDe.get(id) || 'Outras'; if (!porArea.has(area)) porArea.set(area, []); porArea.get(area).push(id); }
  const ids = []; const filas = [...porArea.values()];
  // Uma questão de cada área por rodada, para a mistura lembrar a prova.
  while (ids.length < TAMANHO_SIMULADO && filas.some(f => f.length)) for (const fila of filas) { if (fila.length && ids.length < TAMANHO_SIMULADO) ids.push(fila.shift()); }
  return ids;
}
function verSimulado() {
  if (simulado && !simulado.fim) return Object.keys(simulado.respostas).length || simulado.gasto ? retomarSimulado() : introSimulado();
  if (simulado && simulado.fim) return resultadoSimulado();
  introSimulado();
}
function introSimulado() {
  const total = Math.min(TAMANHO_SIMULADO, sortearSimulado().length);
  tela(`<h1>Simulado curto</h1><p class="lide">${total} questões das quatro áreas, com cronômetro e correção só no fim, como na prova.</p><ul class="lista-simples"><li>Cada resposta entra no seu histórico e na densidade.</li><li>Você pode sair e continuar depois: a rodada fica guardada neste aparelho.</li><li>O tempo aparece no alto; toque nele para esconder, se preferir.</li><li>As erradas entram na revisão a partir de amanhã.</li></ul><div class="acoes"><button type="button" id="comecar" ${total ? '' : 'disabled'}>Começar simulado</button></div><p class="nota">Prática sem cálculo de nota TRI. No Enem, a média é de cerca de 3 minutos por questão.</p>`);
  $('#comecar').onclick = () => { simulado = {conta: painel.conta.id, ids: sortearSimulado(), respostas: {}, atual: 0, gasto: 0, criado: Date.now(), fim: null}; salvarSimulado(); questaoSimulado(); };
}
function retomarSimulado() {
  tela(`<h1>Simulado em andamento</h1><p class="lide">Você parou na questão ${simulado.atual + 1} de ${simulado.ids.length}, com ${tempo(simulado.gasto)} no cronômetro.</p><div class="acoes"><button type="button" id="continuar">Continuar de onde parei</button><button type="button" class="discreto" id="descartar">Encerrar esta rodada</button></div><p class="nota">Encerrar mostra o resultado só das questões já respondidas.</p>`);
  $('#continuar').onclick = questaoSimulado;
  $('#descartar').onclick = () => { simulado.ids = simulado.ids.filter(id => simulado.respostas[id]); if (!simulado.ids.length) { simulado = null; salvarSimulado(); return introSimulado(); } simulado.fim = Date.now(); salvarSimulado(); resultadoSimulado(); };
}
function enviarSimulado(id) {
  const rodada = simulado; const resposta = rodada?.respostas[id];
  if (!resposta || resposta.resultado) return Promise.resolve();
  if (!enviosSimulado.has(id)) {
    enviosSimulado.set(id, (async () => {
      try {
        const r = await api('/api/questoes/' + id, {alternativa: resposta.alternativa, envio: resposta.envio, chute: false});
        if (painel) aplicarResultado(r);
        resposta.resultado = {acerto: r.acerto, correta: r.correta};
        if (simulado === rodada) salvarSimulado();
      } catch { /* Fica pendente; o resultado tenta de novo. */ }
      finally { enviosSimulado.delete(id); }
    })());
  }
  return enviosSimulado.get(id);
}
async function questaoSimulado() {
  if (!simulado || simulado.fim) return verSimulado();
  if (simulado.atual >= simulado.ids.length) { simulado.fim = Date.now(); salvarSimulado(); return resultadoSimulado(); }
  const indice = simulado.atual; const id = simulado.ids[indice];
  tela(`<h1 class="oculto">Simulado curto</h1><section class="ritmo simulado-topo" aria-label="Andamento do simulado"><div class="ritmo-hoje"><span class="rotulo">Simulado</span><strong>${indice + 1} de ${simulado.ids.length}</strong><progress max="${simulado.ids.length}" value="${indice}" aria-label="Questões respondidas no simulado"></progress></div><button type="button" class="cronometro texto-botao" id="alternar-cronometro" aria-pressed="${!prefs.semCronometro}" title="Mostrar ou esconder o tempo"><span id="cronometro"${prefs.semCronometro ? ' hidden' : ''}>${tempo(simulado.gasto)}</span><span id="cronometro-oculto"${prefs.semCronometro ? '' : ' hidden'}>Mostrar tempo</span></button></section><div id="area-questao"><div class="questao esqueleto" role="status"><span class="oculto">Carregando questão…</span><i></i><i></i><i></i><i class="curto"></i></div></div><p class="sair-simulado"><a href="#estudar">Sair e continuar depois</a></p>`);
  const vez = estado.vez; const area = $('#area-questao');
  $('#alternar-cronometro').onclick = () => { prefs.semCronometro = !prefs.semCronometro; salvarPrefs(); $('#cronometro').hidden = prefs.semCronometro; $('#cronometro-oculto').hidden = !prefs.semCronometro; $('#alternar-cronometro').setAttribute('aria-pressed', String(!prefs.semCronometro)); };
  try {
    const q = await obterQuestao(id);
    if (vez !== estado.vez) return;
    montarQuestao(area, q, {modo: 'simulado', ultima: indice === simulado.ids.length - 1, aoResponder: (alternativa, envio) => {
      simulado.respostas[id] = {alternativa, envio, resultado: null}; simulado.atual = indice + 1; salvarSimulado();
      void enviarSimulado(id); subir(); questaoSimulado();
    }});
    relogio = setInterval(() => { if (document.hidden || !simulado) return; simulado.gasto++; const mostrador = $('#cronometro'); if (mostrador) mostrador.textContent = tempo(simulado.gasto); if (simulado.gasto % 5 === 0) salvarSimulado(); }, 1000);
    if (simulado.ids[indice + 1] !== undefined) adiantar(simulado.ids[indice + 1]);
  } catch (e) {
    if (vez !== estado.vez) return;
    area.innerHTML = `<section class="marco"><h2>Não foi possível abrir a questão.</h2><p>${escapar(mensagemErro(e))}</p><div class="acoes"><button type="button" id="tentar">Tentar novamente</button></div></section>`;
    $('#tentar').onclick = questaoSimulado;
  }
}
async function resultadoSimulado() {
  const s = simulado; const respondidas = s.ids.filter(id => s.respostas[id]);
  const pendentes = () => respondidas.filter(id => !s.respostas[id].resultado);
  if (pendentes().length) {
    tela('<h1>Corrigindo seu simulado…</h1><p class="espera" role="status">Conferindo as respostas no servidor.</p>');
    const vez = estado.vez;
    // Espera os envios que já estavam a caminho (a fila pública pode demorar) e repete só o que falhou.
    for (let tentativa = 0; tentativa < 3 && pendentes().length && painel; tentativa++) { await Promise.all(pendentes().map(enviarSimulado)); if (pendentes().length && painel) await new Promise(r => setTimeout(r, 1500)); }
    if (!painel || vez !== estado.vez || simulado !== s) return;
    if (pendentes().length) {
      tela(`<h1>Faltou conferir ${plural(pendentes().length, 'resposta', 'respostas')}.</h1><p>Suas respostas estão guardadas neste aparelho. Verifique a conexão e tente de novo.</p><div class="acoes"><button type="button" id="tentar">Tentar novamente</button></div>`);
      $('#tentar').onclick = resultadoSimulado; return;
    }
  }
  const acertos = respondidas.filter(id => s.respostas[id].resultado.acerto).length;
  const media = respondidas.length ? Math.round(s.gasto / respondidas.length) : 0;
  const linhas = respondidas.map((id, n) => { const q = questoes.get(id); const r = s.respostas[id]; return `<li class="linha-resultado" data-acerto="${r.resultado.acerto}"><span class="marca-resultado" aria-hidden="true">${r.resultado.acerto ? '✓' : '✗'}</span><div><strong>${n + 1}. ${escapar(q ? `${q.materia || q.area} · ${q.titulo}` : 'Questão ' + id)}</strong><span class="secundario">${r.resultado.acerto ? `Certa: ${letra(r.resultado.correta)}` : `Você marcou ${letra(r.alternativa)}; a certa é a ${letra(r.resultado.correta)}`}</span></div><button type="button" class="texto-botao" data-rever="${id}">Rever</button></li>`; }).join('');
  tela(`<h1>Você acertou ${acertos} de ${respondidas.length}.</h1><div class="indicadores"><div class="indicador"><strong>${respondidas.length ? Math.round(acertos / respondidas.length * 100) : 0}%</strong><span>de acerto nesta rodada</span></div><div class="indicador"><strong>${tempo(s.gasto)}</strong><span>tempo total</span></div><div class="indicador"><strong>${tempo(media)}</strong><span>por questão (no Enem, cerca de 03:00)</span></div></div><h2>Questão por questão</h2><ol class="resultado-simulado">${linhas}</ol><p class="secundario">${acertos < respondidas.length ? 'As erradas entram na sua revisão a partir de amanhã.' : 'Nenhuma errada nesta rodada.'} Esta contagem é de prática e não equivale à nota TRI.</p><div class="acoes"><button type="button" id="novo-simulado">Fazer outro simulado</button><a class="botao discreto" href="#progresso">Ver meu progresso</a></div>`);
  $('#novo-simulado').onclick = () => { simulado = null; salvarSimulado(); introSimulado(); };
  $$('[data-rever]').forEach(b => b.onclick = async () => {
    const id = Number(b.dataset.rever); b.disabled = true;
    try {
      const q = await obterQuestao(id); const r = s.respostas[id];
      tela('<h1 class="oculto">Rever questão do simulado</h1><div id="area-questao"></div>');
      montarQuestao($('#area-questao'), q, {modo: 'rever', rotulo: 'simulado', corrigida: {[id]: {escolhida: r.alternativa, correta: r.resultado.correta}}, aoVoltar: () => { resultadoSimulado(); subir(); }});
      subir();
    } catch (e) { erro(e); b.disabled = false; }
  });
}

// ---------- Progresso ----------
function porMateria() {
  const mapa = new Map();
  for (const a of painel.perfil.assuntos) {
    if (!mapa.has(a.materia)) mapa.set(a.materia, {materia: a.materia, tentativas: 0, acertos: 0, assuntos: []});
    const m = mapa.get(a.materia); m.tentativas += a.tentativas; m.acertos += a.acertos; m.assuntos.push(a);
  }
  return [...mapa.values()].map(m => ({...m, percentual: Math.round(m.acertos / m.tentativas * 100)})).sort((a, b) => a.percentual - b.percentual || b.tentativas - a.tentativas);
}
function proximoPasso() {
  const vencidas = painel.estudo.revisao.vencidas.length;
  if (vencidas) return {titulo: `Revise ${plural(vencidas, 'questão', 'questões')} que você errou ou chutou.`, texto: 'São as que venceram hoje. Leva poucos minutos.', botao: 'Revisar agora', acao: () => { estado.modo = 'revisao'; prefs.foco = null; }};
  const fraco = painel.perfil.assuntos.find(a => a.tentativas >= 3 && a.percentual < 60);
  if (fraco) return {titulo: `Treine ${fraco.assunto} (${fraco.materia}).`, texto: `Você acertou ${fraco.acertos} de ${fraco.tentativas} neste assunto. É onde mais dá para crescer agora.`, botao: 'Treinar este assunto', acao: () => { estado.modo = 'misturado'; prefs.foco = {materia: fraco.materia, topico: fraco.assunto}; }};
  if (!painel.progresso.total) return {titulo: 'Responda a sua primeira questão.', texto: 'Com as primeiras respostas, esta página mostra onde você vai bem e onde treinar.', botao: 'Começar', acao: () => {}};
  return {titulo: 'Continue de onde parou.', texto: 'Nenhuma revisão vence hoje e nenhum assunto pede atenção especial.', botao: 'Continuar estudando', acao: () => {}};
}
function verProgresso() {
  const {total, acertos} = painel.progresso; const e = painel.estudo; const d = painel.densidade; const p = painel.perfil;
  const passo = proximoPasso(); const dias = e.semana.filter(n => n > 0).length; const semana = e.semana.reduce((a, b) => a + b, 0);
  const materias = porMateria();
  tela(`<h1>Seu progresso</h1>
<section class="passo"><p class="rotulo">Próximo passo</p><h2>${escapar(passo.titulo)}</h2><p>${escapar(passo.texto)}</p><button type="button" id="passo">${escapar(passo.botao)}</button></section>
<div class="indicadores"><div class="indicador"><strong>${e.hoje.respostas}</strong><span>${e.hoje.respostas === 1 ? 'questão hoje' : 'questões hoje'} (meta: ${prefs.meta})</span></div><div class="indicador"><strong>${dias}</strong><span>${dias === 1 ? 'dia de estudo' : 'dias de estudo'} nesta semana, ${plural(semana, 'questão', 'questões')}</span></div><div class="indicador"><strong>${total ? Math.round(acertos / total * 100) + '%' : '—'}</strong><span>de acerto em ${plural(total, 'resposta', 'respostas')}</span></div></div>
<h2>Revisão</h2><p>${e.revisao.caderno ? `${plural(e.revisao.caderno, 'questão está', 'questões estão')} no seu caderno de revisão; ${e.revisao.vencidas.length ? plural(e.revisao.vencidas.length, 'vence hoje', 'vencem hoje') : 'nenhuma vence hoje'}.` : 'Seu caderno de revisão está vazio.'} Uma questão errada ou chutada volta depois de 1, 3 e 7 dias e sai do caderno quando você acerta com segurança nas três voltas.</p>
<h2>Por matéria</h2>${materias.length ? `<p class="secundario">Da que mais precisa de treino para a que você mais acerta. Toque para ver os assuntos.</p>${materias.map(m => `<details class="materia"><summary><span class="nome">${escapar(m.materia)}</span><span class="numero">${m.percentual}% <small>${m.acertos} de ${m.tentativas}</small></span><progress max="${m.tentativas}" value="${m.acertos}" aria-label="Acertos em ${escapar(m.materia)}"></progress></summary>${m.assuntos.map(a => `<div class="assunto"><div><strong>${escapar(a.assunto)}</strong><span class="secundario">${plural(a.acertos, 'acerto', 'acertos')} e ${plural(a.erros, 'erro', 'erros')} em ${plural(a.tentativas, 'tentativa', 'tentativas')} (${num(a.percentual)}%). ${a.media === null ? 'Comparação disponível quando houver respostas de pelo menos cinco usuários nesse assunto.' : `Média dos usuários: ${num(a.media)}%. Sua diferença: ${num(a.percentual - a.media)} pontos percentuais.`}</span></div><button type="button" class="texto-botao" data-treinar-materia="${escapar(a.materia)}" data-treinar-topico="${escapar(a.assunto)}">Treinar</button></div>`).join('')}</details>`).join('')}` : '<p>Responda uma questão para começar seu perfil.</p>'}
<details class="materia densidade"><summary><span class="nome">Volta completa pelo banco (densidade)</span><span class="numero">${d.feitas} <small>de ${d.total}</small></span>${d.total ? `<progress aria-label="Questões feitas na densidade" value="${d.feitas}" max="${d.total}"></progress>` : ''}</summary><p><strong>${plural(d.concluidas, 'densidade completa', 'densidades completas')}</strong> · ${d.feitas} de ${d.total} questões na densidade atual.</p><p class="secundario">Uma densidade é uma volta completa pelo banco: todas as questões, de todas as matérias, na proporção em que aparecem nas provas guardadas. Acertos e erros contam como prática. Não é meta de prazo: ela anda sozinha enquanto você cumpre a meta do dia. ${escapar(d.base || '')}</p>${d.materias.length ? `<ul class="lista-densidade">${d.materias.map(m => `<li><span>${escapar(m.materia)}</span><span>${m.feitas} de ${m.total}</span></li>`).join('')}</ul>` : ''}</details>${d.bloqueada ? '<p role="status">Uma questão desta volta saiu do banco. Seu progresso está guardado; avise quem mantém o PU.</p>' : ''}
<p class="nota">Média geral dos usuários: ${p.mediaGeral === null || p.mediaGeral === undefined ? 'amostra insuficiente' : num(p.mediaGeral) + '%'}. ${p.atualizada ? `Atualização semanal: ${escapar(p.atualizada.slice(0, 10))}. ` : ''}${escapar(p.periodo || '')} Questões retiradas do catálogo não entram na classificação por assunto. Esses números representam tentativas e acertos nesta plataforma; não são nota TRI nem previsão de desempenho no Enem.</p>`);
  const ir = () => { salvarPrefs(); if (location.hash === '#estudar') navegar(); else location.hash = '#estudar'; };
  $('#passo').onclick = () => { passo.acao(); ir(); };
  $$('[data-treinar-materia]').forEach(b => b.onclick = () => { estado.modo = 'misturado'; prefs.foco = {materia: b.dataset.treinarMateria, topico: b.dataset.treinarTopico}; ir(); });
}

// ---------- Lembrete diário ----------
// O PU não envia notificações. O lembrete é um evento que se repete todo dia no calendário do próprio aparelho.
function baixarLembrete(hora) {
  const [h, m] = hora.split(':').map(Number); const dois = n => String(n).padStart(2, '0'); const d = new Date();
  const dia = `${d.getFullYear()}${dois(d.getMonth() + 1)}${dois(d.getDate())}`; const fim = h * 60 + m + 10;
  const carimbo = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d+/, '');
  const endereco = location.origin + location.pathname;
  const linhas = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Pe na Universidade//PU//PT-BR', 'BEGIN:VEVENT', `UID:pu-lembrete-${Date.now()}@pu`, `DTSTAMP:${carimbo}`,
    `DTSTART:${dia}T${dois(h)}${dois(m)}00`, `DTEND:${dia}T${dois(Math.floor(fim / 60) % 24)}${dois(fim % 60)}00`, 'RRULE:FREQ=DAILY', `SUMMARY:PU: ${prefs.meta} questões de hoje`,
    `DESCRIPTION:Abra o PU e responda a questão do dia: ${endereco}`, `URL:${endereco}`, 'BEGIN:VALARM', 'ACTION:DISPLAY', 'DESCRIPTION:Hora das questões do PU', 'TRIGGER:PT0M', 'END:VALARM', 'END:VEVENT', 'END:VCALENDAR'];
  const arquivo = URL.createObjectURL(new Blob([linhas.join('\r\n')], {type: 'text/calendar'}));
  const link = document.createElement('a'); link.href = arquivo; link.download = 'lembrete-pu.ics'; document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(arquivo), 10000);
}

// ---------- Conta, dispositivos e dados ----------
async function verConta() {
  tela(`<h1>Sua conta</h1><p class="lide">${escapar(painel.conta.nome)}</p>
<h2>Meta do dia</h2><p class="secundario">Quantas questões contam como o dia feito. Comece pequeno: dá para fazer mais quando quiser.</p><div class="modos" role="group" aria-label="Meta diária de questões">${[3, 5, 10, 20].map(n => `<button type="button" class="ficha" data-meta="${n}" aria-pressed="${prefs.meta === n}">${n} questões</button>`).join('')}</div>
<h2>Tema</h2><p class="secundario">Vale para as telas de estudo neste navegador. No automático, o PU fica diurno, com fundo branco, das 6h às 18h e noturno, com fundo preto, das 18h às 6h.</p><fieldset class="escolha-tema"><legend class="oculto">Tema</legend>${Object.entries(TEMAS).map(([valor, nome]) => `<label class="opcao-tema"><input type="radio" name="tema" value="${valor}"${prefs.tema === valor ? ' checked' : ''}><span>${nome}</span></label>`).join('')}</fieldset>
<div class="bloco-fuso" id="bloco-fuso"${prefs.tema === 'automatico' ? '' : ' hidden'}><label for="fuso">Fuso horário</label><select id="fuso" aria-describedby="hora-fuso">${opcoesDeFuso()}</select><p class="secundario" id="hora-fuso"></p></div>
<h2>Sons</h2><p class="secundario">Um som curto quando a correção aparece logo depois de responder, um para acerto e outro para erro. O simulado não tem som.</p><div class="modos"><button type="button" class="ficha" role="switch" id="sons" aria-checked="${prefs.sons !== false}">Sons de acerto e erro</button></div>
${publico && !matchMedia('(display-mode: standalone)').matches ? '<h2>PU a um toque</h2><p class="secundario">No celular, abra o menu do navegador e escolha “Adicionar à tela inicial”. O PU vira um ícone e abre direto na questão do dia.</p>' : ''}
<h2>Lembrete diário</h2><p class="secundario">O PU não envia notificações. Escolha um horário e baixe um evento que se repete todo dia; ao abrir o arquivo, ele entra no calendário do seu celular ou computador, com o aviso na hora marcada.</p><div class="lembrete"><label for="hora-lembrete">Horário</label><input id="hora-lembrete" type="time" value="${escapar(prefs.lembrete || '19:00')}"><button type="button" class="discreto" id="criar-lembrete">Baixar lembrete</button></div>
<h2>Atalhos do teclado</h2><p class="secundario">No computador, as teclas A a E marcam a alternativa e Enter confere.</p><div class="modos" role="group" aria-label="Atalhos do teclado"><button type="button" class="ficha" id="atalhos" aria-pressed="${prefs.atalhos !== false}">Letras A a E ${prefs.atalhos !== false ? 'ligadas' : 'desligadas'}</button></div>
<h2>Dispositivos autorizados</h2><p class="secundario">Um novo navegador é registrado quando você entra com a senha. Você pode manter até cinco. Revogar encerra as sessões daquele dispositivo.</p><div id="dispositivos"><p class="espera" role="status">Carregando dispositivos…</p></div>
<h2>Dados e saída</h2><div class="acoes"><a class="botao discreto" href="#privacidade">Dados e segurança</a><button type="button" class="discreto" id="sair">Sair da conta</button></div>`);
  $$('[data-meta]').forEach(b => b.onclick = () => { prefs.meta = Number(b.dataset.meta); prefs.alvo = null; acertarAlvo(); $$('[data-meta]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); informar(`Meta do dia: ${prefs.meta} questões.`); });
  $('#criar-lembrete').onclick = () => { const hora = $('#hora-lembrete').value; if (!/^\d{2}:\d{2}$/.test(hora)) { informar('Escolha um horário para o lembrete.', true); return; } prefs.lembrete = hora; salvarPrefs(); baixarLembrete(hora); informar(`Lembrete das ${hora} baixado. Abra o arquivo para colocá-lo no calendário.`); };
  $$('input[name="tema"]').forEach(entrada => entrada.onchange = () => {
    if (!entrada.checked) return;
    prefs.tema = entrada.value; salvarPrefs(); aplicarTema();
    $('#bloco-fuso').hidden = prefs.tema !== 'automatico'; mostrarHoraDoFuso();
    informar(`Tema: ${TEMAS[prefs.tema]}${prefs.tema === 'automatico' ? `, agora ${temaEmVigor()}` : ''}.`);
  });
  $('#fuso').onchange = evento => {
    prefs.fuso = fusoValido(evento.target.value) ? evento.target.value : ''; salvarPrefs(); aplicarTema(); mostrarHoraDoFuso();
    informar(`Fuso: ${prefs.fuso ? nomeDoFuso(prefs.fuso) : 'o do navegador'}.`);
  };
  $('#fuso').value = prefs.fuso; setTimeout(() => completarFusos($('#fuso')), 0);
  mostrarHoraDoFuso(); aplicarTema();
  $('#sons').onclick = evento => {
    prefs.sons = prefs.sons === false; salvarPrefs(); evento.currentTarget.setAttribute('aria-checked', String(prefs.sons));
    // Ao ligar, toca o de acerto: serve de amostra e já libera o áudio neste gesto.
    if (prefs.sons) { som.preparar(); som.tocar('acerto'); }
    informar(`Sons de acerto e erro ${prefs.sons ? 'ligados' : 'desligados'}.`);
  };
  $('#atalhos').onclick = evento => { prefs.atalhos = prefs.atalhos === false; salvarPrefs(); evento.currentTarget.setAttribute('aria-pressed', String(prefs.atalhos)); evento.currentTarget.textContent = `Letras A a E ${prefs.atalhos ? 'ligadas' : 'desligadas'}`; };
  $('#sair').onclick = async () => {
    // Mesmo sem rede, o aparelho é limpo: num celular dividido, nada fica para a próxima pessoa.
    let falha = null;
    try { await api('/api/sair', {}); } catch (e) { falha = e; }
    encerrarLocal(true); cadastro = false; verEntrada();
    if (falha && falha.status !== 401) informar('Você saiu neste aparelho. Não foi possível avisar o servidor agora; a sessão antiga vence sozinha.');
  };
  const vez = estado.vez;
  const listar = async () => {
    try {
      const dados = await api('/api/dispositivos');
      const destino = $('#dispositivos'); if (vez !== estado.vez || !destino) return;
      destino.innerHTML = dados.dispositivos.map(d => `<section class="dispositivo"><strong>${escapar(d.nome)}${d.atual ? ' (este dispositivo)' : ''}</strong><button type="button" class="texto-botao" data-revogar="${escapar(d.id)}">Revogar acesso</button></section>`).join('') || '<p>Nenhum dispositivo registrado.</p>';
      $$('[data-revogar]', destino).forEach(b => b.onclick = async () => { b.disabled = true; try { await api('/api/dispositivos', {acao: 'revogar', id: b.dataset.revogar}); await atualizar(); await listar(); } catch (e) { if (painel) { erro(e); b.disabled = false; } } });
    } catch (e) { const destino = $('#dispositivos'); if (vez === estado.vez && destino) destino.innerHTML = `<p>${escapar(mensagemErro(e))}</p>`; }
  };
  void listar();
}
function verPrivacidade() {
  tela(`<h1>Seus dados e sua segurança</h1>
<h2>O que o PU guarda e para quê</h2><p>Na sua conta ficam o nome, o e-mail, a senha guardada só como resumo protegido (scrypt, com sal próprio de cada conta), as sessões abertas, os navegadores autorizados com a data do primeiro e do último uso, e cada resposta com data e hora, inclusive quando você marca “Chutei”. Com isso o PU abre a sua conta, mostra o histórico, monta a revisão, calcula o seu desempenho por matéria e assunto e faz a comparação semanal. O desempenho por assunto não mede capacidade e não é diagnóstico.</p>
<p>No banco do PU, a senha não fica escrita: quem administra o PU vê só o resumo, que não se desfaz de volta em senha. Uma senha curta ou comum ainda pode ser adivinhada a partir do resumo, por isso o PU pede pelo menos 12 caracteres.</p>
<h2>Por onde os seus dados passam</h2><p>No endereço público, o navegador não fala direto com o PU. Cada pedido vai por HTTPS a um intermediário hospedado num serviço de terceiros, numa conta que não é da Ginga Mídia, e fica numa fila até o conector do PU buscá-lo, o que costuma levar poucos segundos. Pedido que ninguém buscou vence em 35 segundos. Nesse caminho passam o e-mail e a senha quando você entra ou cria a conta, a sessão em todo pedido e, na volta, o seu nome e o resumo de estudo. Enquanto estão na fila, quem administra o intermediário consegue ler esses dados, a senha também. O PU não controla os registros nem as cópias que esse serviço faz. Por isso, crie para o PU uma senha que você não usa em nenhum outro lugar.</p>
<p>A conta e o histórico ficam no banco do PU, no computador onde ele roda, que precisa estar ligado para atender. Cada conta tem ali também um espaço separado com a última cópia do resumo de estudo, sem senha e sem sessão.</p>
<h2>O que fica protegido</h2><p>O navegador não recebe o banco, o resumo das senhas, as respostas de outros estudantes nem o gabarito de uma questão antes de você responder. A exceção é a questão de demonstração da página de entrada, que é pública e não fica registrada. O servidor confere a sessão em todo pedido de dados da conta. A comparação semanal mostra só médias de assuntos com pelo menos cinco estudantes e deixa a conta de teste de fora. As respostas não vão para nenhum modelo de IA. Os registros de funcionamento do PU guardam a hora, o tipo do evento e o resultado, sem nome, e-mail, senha, sessão ou endereço de internet.</p>
<h2>Sessão e o que fica no aparelho</h2><p>Ao entrar, você ganha uma sessão que vale 30 dias. Enquanto você está conectado, este navegador guarda o seu nome e o resumo de estudo, as próximas questões, o simulado em andamento com as correções que já chegaram e, no endereço público, a sessão. A sessão fica no armazenamento comum do navegador, que o código desta página consegue ler; o PU não carrega código de outros sites.</p>
<p>Sair da conta encerra a sessão no servidor e apaga do aparelho a sessão, o resumo, as questões e o simulado. Continuam no aparelho as suas preferências (como a meta do dia), separadas por conta, e o código que identifica este navegador, que sozinho não abre a conta. O histórico continua na conta e volta quando você entrar de novo. Em Conta, você vê os navegadores autorizados, até cinco, e pode revogar cada um, o que encerra as sessões dele. Se você divide o celular ou o computador, use Sair da conta ao terminar. A conta de teste é compartilhada: nela, use só dados inventados.</p>
<h2>Por quanto tempo e como apagar</h2><p>Ainda não há prazo definido para guardar os dados. O histórico continua guardado quando o PU reinicia, e uma cópia cifrada do banco é feita a cada hora no mesmo computador; nenhuma cópia é apagada sozinha. Ainda não há botão para apagar a conta, trocar a senha ou recuperar a senha esquecida. A administração do PU vai definir o prazo de guarda, a exclusão das cópias e o canal para esses pedidos.</p>
<h2>Crianças e adolescentes</h2><p>Muitos estudantes de vestibular têm menos de 18 anos. O PU ainda não pergunta a idade nem pede a ciência de um responsável. As regras para esse público, que precisam seguir a LGPD e o melhor interesse de crianças e adolescentes, ainda estão em definição. Até lá, use só dados de teste nesta versão.</p>
<h2>Seus direitos</h2><p>A LGPD garante a você saber quais dados o PU tem e pedir acesso, correção e exclusão. Ainda não há canal definido nem responsável nomeado para receber esses pedidos, e a exclusão de conta ainda não existe no PU. Esta página descreve como o PU funciona hoje e não atesta conformidade com a LGPD.</p>
<p><a href="https://www.gov.br/anpd/pt-br/assuntos/noticias/anpd-divulga-enunciado-sobre-o-tratamento-de-dados-pessoais-de-criancas-e-adolescentes" target="_blank" rel="noopener noreferrer">Orientação da ANPD sobre crianças e adolescentes</a></p>
<div class="acoes"><a class="botao" href="#estudar">${painel ? 'Voltar ao estudo' : 'Voltar à entrada'}</a></div>`);
}
function verNota() { tela(''); PUSimulador.mostrar(conteudo); }

// ---------- Navegação ----------
const ROTAS = {'#estudar': verEstudo, '#progresso': verProgresso, '#simulado': verSimulado, '#nota': verNota, '#conta': verConta, '#privacidade': verPrivacidade};
const APELIDOS = {'': '#estudar', '#inicio': '#estudar', '#questoes': '#estudar', '#dispositivos': '#conta', '#entrar': '#estudar', '#criar-conta': '#estudar'};
// Endereço para links de outras páginas: /?criar-conta abre a entrada já no cadastro (sem rota nova). Vale uma vez, ao abrir.
let pedidoDeCadastro = new URLSearchParams(location.search).has('criar-conta');
function navegar() {
  if (location.hash === '#principal') return;
  let destino = APELIDOS[location.hash] ?? location.hash;
  if (!ROTAS[destino]) destino = '#estudar';
  marcarMenu(destino);
  const pedido = pedidoDeCadastro; pedidoDeCadastro = false;
  if (destino === '#privacidade') { verPrivacidade(); return subir(); }
  if (!painel) {
    // #entrar e #criar-conta levam ao formulário; ?criar-conta abre no cadastro.
    if (location.hash === '#criar-conta' || (pedido && location.hash !== '#entrar')) cadastro = true; else if (location.hash === '#entrar') cadastro = false;
    return verEntrada({rolar: pedido || ['#entrar', '#criar-conta'].includes(location.hash)});
  }
  ROTAS[destino](); subir();
}
window.addEventListener('hashchange', navegar);
document.addEventListener('click', evento => {
  // "Pular para o conteúdo" só leva o foco, sem trocar de página.
  if (evento.target.closest('a.pular')) { evento.preventDefault(); $('#principal').focus(); return; }
  // Navega também quando o destino já é a página aberta.
  const link = evento.target.closest('a[href^="#"]');
  if (link && link.hash === location.hash && (ROTAS[link.hash] || APELIDOS[link.hash])) { evento.preventDefault(); navegar(); }
});
document.addEventListener('keydown', evento => { document.documentElement.dataset.entrada = 'teclado'; if (estado.aoTeclar) estado.aoTeclar(evento); });
document.addEventListener('pointerdown', () => { document.documentElement.dataset.entrada = 'ponteiro'; });
document.addEventListener('visibilitychange', () => {
  // Ao voltar para a aba em outro dia, busca o painel novo sem tirar a questão da frente.
  if (!document.hidden && painel && painel.estudo.data !== hojeLocal()) atualizar().then(() => { if (!estado.atual && !relogio) navegar(); else atualizarCabecalhoEstudo(); }).catch(() => {});
});

// ---------- Início ----------
(function iniciar() {
  const guardado = guarda.ler(CHAVES.painel);
  const salvas = guarda.ler(CHAVES.questoes);
  (Array.isArray(salvas) ? salvas : []).forEach(q => questoes.set(q.id, q));
  const podeRetomar = guardado && guardado.conta && (!publico || (conexao.habilitado && sessao));
  if (podeRetomar) {
    // Abre na hora com o que ficou guardado; o servidor confirma a sessão e atualiza em seguida.
    painel = normalizar(guardado, true); carregarPrefs();
    if (simulado && simulado.conta !== painel.conta.id) { simulado = null; guarda.apagar(CHAVES.simulado); }
    const quente = painel.estudo.hoje.respostas === 0 ? aquecimento() : null;
    if (quente !== null && questoes.has(quente)) estado.primeira = quente;
    menu.hidden = false; document.body.classList.remove('sem-sessao'); acertarAlvo();
    navegar();
    atualizar().then(() => { if (!estado.atual && !relogio && ['', '#estudar', '#inicio', '#questoes'].includes(location.hash)) navegar(); else atualizarCabecalhoEstudo(); }).catch(e => { if (painel) erro(e); });
    return;
  }
  // Sem conta para retomar: tira o tema que o tema-inicial.js tenha posto (a entrada fica sem tema).
  aplicarTema();
  if (publico) {
    if (conexao.habilitado && sessao) {
      menu.hidden = true; document.body.classList.add('sem-sessao');
      tela('<p class="espera" role="status">Retomando seus estudos…</p>');
      const retomar = () => atualizar().then(navegar).catch(e => { if (sessao) { tela('<p>Não foi possível retomar agora.</p><div class="acoes"><button type="button" id="retomar">Tentar novamente</button></div>'); $('#retomar').onclick = retomar; erro(e); } });
      retomar();
    } else navegar();
    return;
  }
  tela('<p class="espera" role="status">Abrindo o PU…</p>');
  atualizar().then(navegar).catch(e => { if (!painel) navegar(); if (e.status !== 401) erro(e); });
})();
