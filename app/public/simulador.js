/* Dominique-Oliveira-ChatGPT: simulação de médias, independente do cálculo TRI. */
(function (raiz) {
  'use strict';
  const areas = [
    ['linguagens', 'Linguagens'], ['humanas', 'Ciências Humanas'],
    ['natureza', 'Ciências da Natureza'], ['matematica', 'Matemática'], ['redacao', 'Redação']
  ];
  const formato = new Intl.NumberFormat('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const escapar = valor => String(valor).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function numero(valor, nome) {
    if (typeof valor !== 'number' && typeof valor !== 'string') throw new Error(`Preencha ${nome}.`);
    const texto = String(valor).trim().replace(',', '.');
    if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(texto)) throw new Error(`Informe um número válido em ${nome}.`);
    const n = Number(texto);
    if (!Number.isFinite(n) || n < 0 || n > Number.MAX_SAFE_INTEGER) throw new Error(`Confira o valor de ${nome}.`);
    return n;
  }
  function calcular(notas, pesos, corte = '') {
    const ns = areas.map(([id, nome]) => numero(notas[id], `nota de ${nome}`));
    if (ns[4] > 1000) throw new Error('A nota de Redação deve ficar entre 0 e 1.000.');
    const ps = areas.map(([id, nome]) => numero(pesos[id], `peso de ${nome}`));
    const soma = ps.reduce((a,b) => a+b,0);
    if (soma <= 0 || !Number.isFinite(soma)) throw new Error('Informe pelo menos um peso maior que zero.');
    // Pesos normalizados evitam transbordamento na multiplicação nota × peso.
    const parcelas = ns.map((n,i) => n * (ps[i]/soma));
    const media = parcelas.reduce((a,b) => a+b,0);
    const meta = corte === '' || corte == null ? null : numero(corte, 'nota de referência');
    const necessarias = areas.map(([id, nome],i) => {
      if (meta === null || ps[i] === 0) return {id, nome, nota:null, estado:ps[i] === 0 ? 'sem-peso' : 'sem-meta'};
      const nota = (meta - parcelas.reduce((s,n,j) => s+(j===i?0:n),0)) / (ps[i]/soma);
      return {id, nome, nota, estado:nota < 0 ? 'atingida' : i===4 && nota > 1000 ? 'acima-limite' : 'necessaria'};
    });
    return {media, mediaSimples:ns.reduce((s,n) => s+n/5,0), parcelas, participacoes:ps.map(p => p/soma), meta, diferenca:meta === null ? null : media-meta, necessarias};
  }
  function opcaoVazia() { return {instituicao:'', curso:'', modalidade:'', edicao:'', corte:'', pesos:Object.fromEntries(areas.map(([id]) => [id,'1'])), busca:'', sisu:null}; }
  // Lista de cursos do Sisu (pesos-sisu.js, ao lado deste arquivo), carregada só quando o estudante procura um curso.
  // Gerada por scripts/importar-pesos-sisu.py das planilhas oficiais do MEC; o ?v= é o começo do sha256 do arquivo.
  const VERSAO_SISU = 'd3256dbf88';
  const BASE_SCRIPT = typeof document !== 'undefined' && document.currentScript ? document.currentScript.src.replace(/[?#].*$/, '').replace(/[^/]*$/, '') : '';
  const FONTE_OFICIAL = /^https:\/\/sisu\.mec\.gov\.br\//;
  let carregandoSisu = null, indiceSisu = null;
  function carregarSisu() {
    if (raiz.PUPesosSisu) return Promise.resolve(raiz.PUPesosSisu);
    if (!carregandoSisu) carregandoSisu = new Promise((ok, falha) => {
      const s = document.createElement('script');
      s.src = BASE_SCRIPT + 'pesos-sisu.js?v=' + VERSAO_SISU;
      s.onload = () => raiz.PUPesosSisu ? ok(raiz.PUPesosSisu) : falha(new Error('lista vazia'));
      s.onerror = () => { carregandoSisu = null; s.remove(); falha(new Error('lista indisponível')); };
      document.head.appendChild(s);
    });
    return carregandoSisu;
  }
  const simples = texto => String(texto).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
  // Curso k da lista: [sigla, local, curso, grau, turno, pesos, notas mínimas, média mínima, modalidades].
  function cursoSisu(d, k) {
    const c = d.cursos[k]; if (!c) return null;
    const [campus, municipio, uf] = d.locais[c[1]] || ['', '', ''];
    return {sigla:c[0], instituicao:d.instituicoes[c[0]] || c[0], campus, municipio, uf, curso:c[2], grau:c[3], turno:c[4],
      pesos:c[5], minimas:c[6], media:c[7], modalidades:c[8].map(m => ({descricao:d.modalidades[m[0]] || '', cota:m[1], corte:m[2], vagas:m[3], pesos:m[4] || c[5]}))};
  }
  function procurarSisu(d, texto) {
    if (!indiceSisu) indiceSisu = d.cursos.map((c, k) => { const x = cursoSisu(d, k); return simples([x.sigla, x.instituicao, x.curso, x.grau, x.turno, x.campus, x.municipio, x.uf].join(' ')); });
    const partes = simples(texto).split(' ').filter(Boolean);
    if (!partes.length) return [];
    const achados = [];
    indiceSisu.forEach((linha, k) => { if (partes.every(p => linha.includes(p))) achados.push(k); });
    return achados;
  }
  const rotuloModalidade = m => m.cota === 'AC' ? 'Ampla concorrência' : `${m.cota}: ${m.descricao.length > 70 ? m.descricao.slice(0, 70).trim() + '…' : m.descricao}`;
  const textoModalidade = m => m.cota === 'AC' ? 'Ampla concorrência' : (m.descricao.length > 100 ? m.descricao.slice(0, 99).trim() + '…' : m.descricao);
  const nomesAreas = ['Linguagens', 'Humanas', 'Natureza', 'Matemática', 'Redação'];
  let rascunho;
  function limpar() { rascunho = {notas:Object.fromEntries(areas.map(([id]) => [id,''])), opcoes:[opcaoVazia()]}; }
  limpar();
  // publica: a calculadora aberta do site (/calculadora-nota-enem/), que traz o próprio h1 e não tem conta.
  function mostrar(conteudo, opcoesTela = {}) {
    const publica = opcoesTela.publica === true;
    const campo = (id, rotulo, valor, extra='') => `<label for="${id}">${rotulo}</label><input id="${id}" name="${id}" value="${escapar(valor)}" autocomplete="off" ${extra}>`;
    const decimal = 'type="text" inputmode="decimal" maxlength="16" pattern="[0-9]+([.,][0-9]+)?" required';
    conteudo.innerHTML = `<section class="simulador${publica?' simulador-publico':''}"${publica?'':' aria-labelledby="titulo-nota"'}>${publica?'':'<h1 id="titulo-nota">Simule sua nota Enem.</h1><p>Teste suas notas, aplique os pesos do curso e veja quanto falta para a sua meta.</p>'}<p class="nota">Você informa as notas por área. A simulação calcula médias; a nota TRI não pode ser obtida apenas pelo número de acertos.</p><form id="simular-nota"><section aria-labelledby="suas-notas"><h2 id="suas-notas">Suas notas por área</h2><p>Use seu boletim de uma mesma edição ou as notas que deseja alcançar. Nenhum campo vem preenchido com uma previsão.</p><div class="campos-notas">${areas.map(([id,nome]) => `<div>${campo('nota-'+id,nome,rascunho.notas[id],decimal)}</div>`).join('')}</div><small>Redação: de 0 a 1.000. Nas provas objetivas, a escala TRI varia conforme a edição.</small></section><section aria-labelledby="opcoes-cursos"><h2 id="opcoes-cursos">Compare suas opções</h2><p>Adicione até três opções. Procure o curso na lista do Sisu 2026 ou informe os pesos do edital e, se quiser comparar, uma nota de corte de referência da mesma modalidade. Os pesos começam em 1 para calcular a média simples.</p><div id="opcoes-nota">${rascunho.opcoes.map((opcao,i) => `<fieldset class="opcao-nota"><legend>Opção ${i+1}</legend><div class="busca-sisu"><label for="sisu-${i}">Procure o curso no Sisu 2026 (opcional)</label><input id="sisu-${i}" type="search" value="${escapar(opcao.busca)}" maxlength="80" autocomplete="off" spellcheck="false" enterkeyhint="search" data-indice="${i}" aria-describedby="sisu-ajuda-${i}" aria-controls="sisu-lista-${i}"><p class="nota" id="sisu-ajuda-${i}">Digite o curso e a universidade, por exemplo "medicina ufscar". A lista traz cursos de 13 universidades federais com os pesos e a nota de corte do Sisu 2026; eles entram nos campos abaixo, e você pode mudar.</p><p class="estado-sisu" id="sisu-estado-${i}" aria-live="polite"></p><ul class="lista-sisu" id="sisu-lista-${i}"></ul><div class="sisu-escolhido" id="sisu-escolhido-${i}"></div></div><div class="campos-opcao"><div>${campo('instituicao-'+i,'Instituição',opcao.instituicao,'maxlength="100" type="text"')}</div><div>${campo('curso-'+i,'Curso',opcao.curso,'maxlength="100" type="text"')}</div><div>${campo('modalidade-'+i,'Modalidade de concorrência ou cota',opcao.modalidade,'maxlength="100" type="text"')}</div><div>${campo('edicao-'+i,'Edição da seleção de referência',opcao.edicao,'maxlength="40" type="text"')}</div><div>${campo('corte-'+i,'Nota de corte de referência (opcional)',opcao.corte,decimal.replace(' required',''))}</div></div><details${publica?' open':''}><summary>Pesos por área da opção ${i+1}</summary><div class="campos-pesos">${areas.map(([id,nome]) => `<div>${campo('peso-'+i+'-'+id,nome,opcao.pesos[id],decimal)}</div>`).join('')}</div><small>Um peso zero exclui a área apenas desta média. Pelo menos um peso deve ser maior que zero. Confira também as notas mínimas exigidas pelo edital.</small></details>${i>0?`<button type="button" class="discreto remover-opcao" data-indice="${i}">Remover opção ${i+1}</button>`:''}</fieldset>`).join('')}</div><button type="button" class="discreto" id="adicionar-opcao" ${rascunho.opcoes.length>=3?'disabled':''}>Adicionar opção</button></section><p class="erro-campo" id="erro-nota" role="alert" tabindex="-1"></p><button type="submit">Calcular minha simulação</button></form><div id="resultado-nota" tabindex="-1" aria-live="polite"></div>${publica?'':`<details class="metodo-nota"><summary>Como a simulação é calculada</summary><p>Média ponderada = soma de cada nota multiplicada pelo peso ÷ soma dos pesos. Com todos os pesos iguais, o resultado é a média simples.</p><p>Para encontrar a nota necessária em uma área, mantemos as outras quatro notas fixas e resolvemos a mesma fórmula para a meta informada. As metas de cada área são cenários separados.</p><p>Pesos e cortes são os que você digita ou os da lista do Sisu 2026, tirados das planilhas oficiais do MEC; nada é consultado na hora nas faculdades. A comparação não considera notas mínimas, bonificações, desempate ou as demais regras de seleção e não garante aprovação. O rascunho fica nesta aba e é apagado ao sair da conta ou recarregar.</p><p>Referência: <a href="https://www.gov.br/inep/pt-br/centrais-de-conteudo/acervo-linha-editorial/publicacoes-institucionais/avaliacoes-e-exames-da-educacao-basica/entenda-a-sua-nota-no-enem-guia-do-participante" target="_blank" rel="noopener noreferrer">Inep: entenda a sua nota no Enem</a>.</p></details>`}</section>`;
    const form = conteudo.querySelector('#simular-nota');
    function recolher() {
      areas.forEach(([id]) => {rascunho.notas[id]=form.elements['nota-'+id].value;});
      rascunho.opcoes.forEach((opcao,i) => {
        ['instituicao','curso','modalidade','edicao','corte'].forEach(chave => {opcao[chave]=form.elements[chave+'-'+i].value;});
        areas.forEach(([id]) => {opcao.pesos[id]=form.elements['peso-'+i+'-'+id].value;});
      });
    }
    // Curso escolhido na lista do Sisu: caixa com modalidade, nota de corte, pesos, fonte e aviso. Todo texto da lista passa por escapar().
    const link = (url, texto) => FONTE_OFICIAL.test(url) ? `<a href="${escapar(url)}" target="_blank" rel="noopener noreferrer">${texto}</a>` : texto;
    function desenharEscolhido(i) {
      const caixa = conteudo.querySelector('#sisu-escolhido-' + i), opcao = rascunho.opcoes[i], d = raiz.PUPesosSisu;
      const c = opcao.sisu && d ? cursoSisu(d, opcao.sisu.curso) : null;
      if (!caixa || !c) { if (caixa) caixa.replaceChildren(); return; }
      const m = c.modalidades[opcao.sisu.modalidade] || c.modalidades[0];
      const minimas = c.minimas.map((v, j) => [nomesAreas[j], v]).filter(([, v]) => Number(String(v).replace(',', '.')) > 0);
      const media = Number(String(c.media).replace(',', '.')) > 0 ? `<div><dt>Média mínima na planilha do MEC</dt><dd>${escapar(c.media)}</dd></div>` : '';
      caixa.innerHTML = `<p class="sisu-titulo"><strong>${escapar(c.curso)}</strong> (${escapar(c.grau)}, ${escapar(c.turno)}) · ${escapar(c.sigla)} · ${escapar(c.campus)}, ${escapar(c.municipio)} (${escapar(c.uf)})</p>`
        + `<label for="sisu-modalidade-${i}">Modalidade de concorrência</label><select id="sisu-modalidade-${i}" data-indice="${i}">${c.modalidades.map((x, j) => `<option value="${j}"${x === m ? ' selected' : ''}>${escapar(rotuloModalidade(x))}</option>`).join('')}</select>`
        + `<p class="nota">${escapar(m.descricao)}</p>`
        + `<dl class="sisu-dados"><div><dt>Nota de corte na chamada regular</dt><dd>${m.corte ? escapar(m.corte) : 'Sem nota de corte nesta modalidade'}</dd></div><div><dt>Vagas nesta modalidade</dt><dd>${escapar(m.vagas)}</dd></div><div><dt>Pesos</dt><dd>${m.pesos.map((v, j) => `${nomesAreas[j]} ${escapar(v)}`).join(' · ')}</dd></div>${minimas.length ? `<div><dt>Notas mínimas na planilha do MEC</dt><dd>${minimas.map(([n, v]) => `${n} ${escapar(v)}`).join(' · ')}</dd></div>` : ''}${media}</dl>`
        + `<p class="aviso-sisu" data-sisu-mudou hidden>Você mudou um peso ou a nota de corte: a conta usa os seus números, e não os do Sisu.</p>`
        + `<p class="aviso-sisu">A nota de corte muda a cada edição e durante as inscrições: a do próximo Sisu pode ser outra. Ela não garante vaga, e a conta não confere as notas mínimas.</p>`
        + `<p class="nota">Fonte: planilhas oficiais do MEC do ${escapar(d.edicao)}, ${link(d.fonte_pesos, 'pesos e notas mínimas')} e ${link(d.fonte_cortes, 'notas de corte da chamada regular')}, na ${link(d.pagina, 'página do Sisu')}. Conferidas em ${escapar(String(d.conferido_em).split('-').reverse().join('/'))}.</p>`
        + `<button type="button" class="discreto limpar-sisu" data-indice="${i}">Limpar esta opção</button>`;
      marcarMudanca(i);
    }
    function marcarMudanca(i) {
      const opcao = rascunho.opcoes[i], aviso = conteudo.querySelector(`#sisu-escolhido-${i} [data-sisu-mudou]`), d = raiz.PUPesosSisu;
      const c = opcao.sisu && d ? cursoSisu(d, opcao.sisu.curso) : null;
      if (!aviso || !c) return;
      const m = c.modalidades[opcao.sisu.modalidade] || c.modalidades[0];
      const igual = (a, b) => String(a).trim().replace(',', '.') === String(b).trim().replace(',', '.');
      aviso.hidden = igual(opcao.corte, m.corte) && areas.every(([id], a) => igual(opcao.pesos[id], m.pesos[a]));
    }
    function aplicarSisu(i, k, j) {
      const d = raiz.PUPesosSisu, c = d && cursoSisu(d, k);
      if (!c) return;
      const m = c.modalidades[j] || c.modalidades[0], opcao = rascunho.opcoes[i];
      Object.assign(opcao, {instituicao:`${c.sigla} (${c.instituicao})`, curso:`${c.curso} (${c.grau}, ${c.turno}, ${c.campus})`, modalidade:textoModalidade(m),
        edicao:`${d.edicao}, ${d.etapa}`, corte:m.corte || '', busca:'', sisu:{curso:k, modalidade:c.modalidades.indexOf(m)}});
      areas.forEach(([id], a) => { opcao.pesos[id] = m.pesos[a]; });
    }
    function listar(i) {
      const opcao = rascunho.opcoes[i], lista = conteudo.querySelector('#sisu-lista-' + i), estado = conteudo.querySelector('#sisu-estado-' + i);
      if (!lista || !estado) return;
      if (simples(opcao.busca).length < 3) { lista.replaceChildren(); estado.textContent = ''; return; }
      if (!raiz.PUPesosSisu) estado.textContent = 'Carregando a lista de cursos…';
      carregarSisu().then(d => {
        if (simples(opcao.busca).length < 3) return;
        const achados = procurarSisu(d, opcao.busca);
        lista.innerHTML = achados.slice(0, 8).map(k => { const c = cursoSisu(d, k); return `<li><button type="button" class="discreto opcao-sisu" data-indice="${i}" data-curso="${k}">${escapar(c.curso)} <small>${escapar(c.sigla)} · ${escapar(c.campus)} · ${escapar(c.grau)}, ${escapar(c.turno)}</small></button></li>`; }).join('');
        estado.textContent = !achados.length ? 'Nenhum curso da lista com essas palavras. Confira a grafia ou digite os pesos e a nota de corte à mão.'
          : achados.length > 8 ? `${achados.length} cursos encontrados. Os 8 primeiros estão abaixo; acrescente uma palavra para achar o seu.`
          : achados.length === 1 ? '1 curso encontrado.' : `${achados.length} cursos encontrados.`;
      }).catch(() => { lista.replaceChildren(); estado.textContent = 'Não deu para carregar a lista de cursos agora. Digite os pesos e a nota de corte à mão.'; });
    }
    form.addEventListener('input', evento => {
      recolher();
      conteudo.querySelector('#resultado-nota').replaceChildren();
      conteudo.querySelector('#erro-nota').textContent='';
      const busca = evento.target.closest('.busca-sisu input[type=search]');
      if (busca) { rascunho.opcoes[Number(busca.dataset.indice)].busca = busca.value; listar(Number(busca.dataset.indice)); }
      rascunho.opcoes.forEach((o, i) => marcarMudanca(i));
    });
    form.addEventListener('keydown', evento => { if (evento.key === 'Enter' && evento.target.closest('.busca-sisu input[type=search]')) evento.preventDefault(); });
    form.addEventListener('click', evento => {
      const escolha = evento.target.closest('.opcao-sisu'), limpar = evento.target.closest('.limpar-sisu');
      if (escolha) {
        const i = Number(escolha.dataset.indice);
        recolher(); aplicarSisu(i, Number(escolha.dataset.curso), 0); mostrar(conteudo, opcoesTela);
        const seletor = conteudo.querySelector('#sisu-modalidade-' + i); if (seletor) seletor.focus();
      } else if (limpar) {
        const i = Number(limpar.dataset.indice);
        rascunho.opcoes[i] = opcaoVazia(); mostrar(conteudo, opcoesTela); conteudo.querySelector('#sisu-' + i).focus();
      }
    });
    form.addEventListener('change', evento => {
      const seletor = evento.target.closest('select[id^="sisu-modalidade-"]');
      if (!seletor) return;
      const i = Number(seletor.dataset.indice);
      recolher(); aplicarSisu(i, rascunho.opcoes[i].sisu.curso, Number(seletor.value)); mostrar(conteudo, opcoesTela);
      conteudo.querySelector('#sisu-modalidade-' + i).focus();
    });
    rascunho.opcoes.forEach((opcao, i) => { if (opcao.sisu) desenharEscolhido(i); else if (opcao.busca) listar(i); });
    conteudo.querySelector('#adicionar-opcao').onclick = () => {
      if(rascunho.opcoes.length>=3) return;
      recolher(); rascunho.opcoes.push(opcaoVazia()); mostrar(conteudo, opcoesTela);
      conteudo.querySelector('#instituicao-'+(rascunho.opcoes.length-1)).focus();
    };
    conteudo.querySelectorAll('.remover-opcao').forEach(botao => {botao.onclick=()=>{
      recolher(); rascunho.opcoes.splice(Number(botao.dataset.indice),1); mostrar(conteudo, opcoesTela);
      conteudo.querySelector('#adicionar-opcao').focus();
    };});
    // Abrir detalhes antes de o navegador focar um peso inválido oculto.
    form.addEventListener('invalid',evento => { const detalhes=evento.target.closest('details'); if(detalhes) detalhes.open=true; },true);
    form.onsubmit = evento => {
      evento.preventDefault(); recolher();
      const resultado = conteudo.querySelector('#resultado-nota');
      const erro = conteudo.querySelector('#erro-nota');
      try {
        const calculos=rascunho.opcoes.map(opcao => calcular(rascunho.notas,opcao.pesos,opcao.corte));
        erro.textContent='';
        resultado.innerHTML=`<h2>Resultado da sua simulação</h2><p>Média simples das cinco notas: <strong>${formato.format(calculos[0].mediaSimples)}</strong>.</p>${calculos.map((r,i) => {
          const opcao=rascunho.opcoes[i];
          const contexto=[opcao.instituicao,opcao.curso,opcao.modalidade,opcao.edicao].filter(v=>v.trim()).map(escapar).join(' · ');
          const comparacao=r.meta===null?'Informe uma nota de corte de referência para comparar com sua meta.':`Referência informada: ${formato.format(r.meta)}. ${Math.abs(r.diferenca)<1e-9?'Sua média coincide com a referência.':r.diferenca<0?`Faltam ${formato.format(-r.diferenca)} pontos para essa referência.`:`Sua média está ${formato.format(r.diferenca)} pontos acima dessa referência.`}`;
          return `<article class="resultado-opcao"><h3>Opção ${i+1}${contexto?': '+contexto:''}</h3><p class="media-nota"><strong>${formato.format(r.media)}</strong><span>média com os pesos informados</span></p><p>${comparacao}</p><details><summary>Participação de cada área na média</summary><dl class="parcelas-nota">${areas.map(([id,nome],j)=>`<div><dt>${nome}</dt><dd>${formato.format(r.parcelas[j])} pontos na média · peso ${escapar(opcao.pesos[id])} · ${formato.format(r.participacoes[j]*100)}%</dd></div>`).join('')}</dl></details>${r.meta===null?'':`<h4>Quanto preciso tirar em cada área?</h4><p>Cada linha muda somente uma nota e mantém as outras como você informou. São alternativas para atingir a referência, sem previsão de TRI.</p><dl class="metas-nota">${r.necessarias.map(n => `<div><dt>${n.nome}</dt><dd>${n.estado==='sem-peso'?'Peso zero: esta área não altera a média.':n.estado==='atingida'?'As outras áreas já atingem a referência, mesmo com zero nesta.':n.estado==='acima-limite'?'A meta exigiria mais de 1.000 na redação. Ajuste também as notas de outras áreas.':`${formato.format(n.nota)} pontos${n.id==='redacao'?'':'; a viabilidade depende da escala TRI da edição.'}`}</dd></div>`).join('')}</dl>`}</article>`;
        }).join('')}<p class="nota">Simulação com dados informados por você. Atingir uma referência histórica não garante aprovação.</p>`;
        resultado.focus();
      } catch(e) { resultado.replaceChildren(); erro.textContent=e.message; erro.focus(); }
    };
  }
  const api={areas,numero,calcular,mostrar,limpar};
  if(typeof module!=='undefined' && module.exports) module.exports=api;
  else raiz.PUSimulador=api;
})(typeof window!=='undefined'?window:globalThis);
