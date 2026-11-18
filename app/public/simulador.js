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
  function opcaoVazia() { return {instituicao:'', curso:'', modalidade:'', edicao:'', corte:'', pesos:Object.fromEntries(areas.map(([id]) => [id,'1']))}; }
  let rascunho;
  function limpar() { rascunho = {notas:Object.fromEntries(areas.map(([id]) => [id,''])), opcoes:[opcaoVazia()]}; }
  limpar();
  // publica: a calculadora aberta do site (/calculadora-nota-enem/), que traz o próprio h1 e não tem conta.
  function mostrar(conteudo, opcoesTela = {}) {
    const publica = opcoesTela.publica === true;
    const campo = (id, rotulo, valor, extra='') => `<label for="${id}">${rotulo}</label><input id="${id}" name="${id}" value="${escapar(valor)}" autocomplete="off" ${extra}>`;
    const decimal = 'type="text" inputmode="decimal" maxlength="16" pattern="[0-9]+([.,][0-9]+)?" required';
    conteudo.innerHTML = `<section class="simulador${publica?' simulador-publico':''}"${publica?'':' aria-labelledby="titulo-nota"'}>${publica?'':'<h1 id="titulo-nota">Simule sua nota Enem.</h1><p>Teste suas notas, aplique os pesos do curso e veja quanto falta para a sua meta.</p>'}<p class="nota">Você informa as notas por área. A simulação calcula médias; a nota TRI não pode ser obtida apenas pelo número de acertos.</p><form id="simular-nota"><section aria-labelledby="suas-notas"><h2 id="suas-notas">Suas notas por área</h2><p>Use seu boletim de uma mesma edição ou as notas que deseja alcançar. Nenhum campo vem preenchido com uma previsão.</p><div class="campos-notas">${areas.map(([id,nome]) => `<div>${campo('nota-'+id,nome,rascunho.notas[id],decimal)}</div>`).join('')}</div><small>Redação: de 0 a 1.000. Nas provas objetivas, a escala TRI varia conforme a edição.</small></section><section aria-labelledby="opcoes-cursos"><h2 id="opcoes-cursos">Compare suas opções</h2><p>Adicione até três opções. Informe os pesos do edital e, se quiser comparar, uma nota de corte de referência da mesma modalidade. Os pesos começam em 1 para calcular a média simples.</p><div id="opcoes-nota">${rascunho.opcoes.map((opcao,i) => `<fieldset class="opcao-nota"><legend>Opção ${i+1}</legend><div class="campos-opcao"><div>${campo('instituicao-'+i,'Instituição',opcao.instituicao,'maxlength="100" type="text"')}</div><div>${campo('curso-'+i,'Curso',opcao.curso,'maxlength="100" type="text"')}</div><div>${campo('modalidade-'+i,'Modalidade de concorrência ou cota',opcao.modalidade,'maxlength="100" type="text"')}</div><div>${campo('edicao-'+i,'Edição da seleção de referência',opcao.edicao,'maxlength="40" type="text"')}</div><div>${campo('corte-'+i,'Nota de corte de referência (opcional)',opcao.corte,decimal.replace(' required',''))}</div></div><details${publica?' open':''}><summary>Pesos por área da opção ${i+1}</summary><div class="campos-pesos">${areas.map(([id,nome]) => `<div>${campo('peso-'+i+'-'+id,nome,opcao.pesos[id],decimal)}</div>`).join('')}</div><small>Um peso zero exclui a área apenas desta média. Pelo menos um peso deve ser maior que zero. Confira também as notas mínimas exigidas pelo edital.</small></details>${i>0?`<button type="button" class="discreto remover-opcao" data-indice="${i}">Remover opção ${i+1}</button>`:''}</fieldset>`).join('')}</div><button type="button" class="discreto" id="adicionar-opcao" ${rascunho.opcoes.length>=3?'disabled':''}>Adicionar opção</button></section><p class="erro-campo" id="erro-nota" role="alert" tabindex="-1"></p><button type="submit">Calcular minha simulação</button></form><div id="resultado-nota" tabindex="-1" aria-live="polite"></div>${publica?'':`<details class="metodo-nota"><summary>Como a simulação é calculada</summary><p>Média ponderada = soma de cada nota multiplicada pelo peso ÷ soma dos pesos. Com todos os pesos iguais, o resultado é a média simples.</p><p>Para encontrar a nota necessária em uma área, mantemos as outras quatro notas fixas e resolvemos a mesma fórmula para a meta informada. As metas de cada área são cenários separados.</p><p>Pesos e cortes são dados informados por você, sem consulta automática a faculdades. A comparação não considera notas mínimas, bonificações, desempate ou as demais regras de seleção e não garante aprovação. O rascunho fica nesta aba e é apagado ao sair da conta ou recarregar.</p><p>Referência: <a href="https://www.gov.br/inep/pt-br/centrais-de-conteudo/acervo-linha-editorial/publicacoes-institucionais/avaliacoes-e-exames-da-educacao-basica/entenda-a-sua-nota-no-enem-guia-do-participante" target="_blank" rel="noopener noreferrer">Inep: entenda a sua nota no Enem</a>.</p></details>`}</section>`;
    const form = conteudo.querySelector('#simular-nota');
    function recolher() {
      areas.forEach(([id]) => {rascunho.notas[id]=form.elements['nota-'+id].value;});
      rascunho.opcoes.forEach((opcao,i) => {
        ['instituicao','curso','modalidade','edicao','corte'].forEach(chave => {opcao[chave]=form.elements[chave+'-'+i].value;});
        areas.forEach(([id]) => {opcao.pesos[id]=form.elements['peso-'+i+'-'+id].value;});
      });
    }
    form.addEventListener('input', () => {
      recolher();
      conteudo.querySelector('#resultado-nota').replaceChildren();
      conteudo.querySelector('#erro-nota').textContent='';
    });
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
