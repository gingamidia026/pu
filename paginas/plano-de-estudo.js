/* Plano de estudo (/plano-de-estudo/). paginas/gerar.py liga este arquivo só nesta página.
   Lê as provas que já estão no HTML (<option data-data="AAAA-MM-DD">, tiradas da coleta do calendário), os dias livres
   e as questões por dia, e escreve cada dia de estudo de hoje (data do aparelho) até a véspera da prova, com as quatro
   áreas alternadas e as revisões na regra do PU (1, 3 e 7 dias; app/acompanhamento.py, INTERVALOS). Não busca nada na
   rede e não grava nada. Sem este script, a página mostra a conta por extenso. Dominique-Oliveira-Claude🤖🧡, 18/11/2026. */
(function () {
  'use strict';
  var form = document.querySelector('[data-plano]');
  var caixa = document.querySelector('[data-plano-saida]');
  var resumo = document.querySelector('[data-plano-resumo]');
  var saida = document.querySelector('[data-plano-lista]');
  if (!form || !caixa || !resumo || !saida) return;
  var AREAS = ['Linguagens', 'Ciências Humanas', 'Ciências da Natureza', 'Matemática'];
  var INTERVALOS = [1, 3, 7];
  var VISIVEIS = 14;
  var DIAS = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'];
  var MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
  var UM_DIA = 24 * 60 * 60 * 1000;

  var dois = function (n) { return (n < 10 ? '0' : '') + n; };
  var curta = function (d) { return dois(d.getDate()) + '/' + dois(d.getMonth() + 1); };
  var extenso = function (d) { return (d.getDate() === 1 ? '1º' : d.getDate()) + ' de ' + MESES[d.getMonth()] + ' de ' + d.getFullYear(); };
  var plural = function (n, um, varios) { return n + ' ' + (n === 1 ? um : varios); };
  var lerData = function (texto) { var p = texto.split('-').map(Number); return new Date(p[0], p[1] - 1, p[2]); };
  var somar = function (d, n) { return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n); };
  var dif = function (a, b) { return Math.round((b - a) / UM_DIA); };
  var elemento = function (tag, classe, texto) { var e = document.createElement(tag); if (classe) e.className = classe; if (texto !== undefined) e.textContent = texto; return e; };

  var agora = new Date();
  var hoje = new Date(agora.getFullYear(), agora.getMonth(), agora.getDate());
  var select = form.querySelector('select');
  // Provas que já passaram (ou são hoje) saem da lista; a primeira que sobra fica escolhida.
  Array.prototype.slice.call(select.options).forEach(function (o) { if (lerData(o.getAttribute('data-data')) <= hoje) o.remove(); });
  form.hidden = false; caixa.hidden = false;
  var semScript = form.parentNode.querySelector('.sem-script');
  if (semScript) semScript.hidden = true;
  form.addEventListener('submit', function (evento) { evento.preventDefault(); });

  // Dias de estudo: de hoje até a véspera, só nos dias da semana marcados.
  function diasDeEstudo(prova, semana) {
    var lista = [];
    for (var d = hoje; d < prova; d = somar(d, 1)) if (semana.indexOf(d.getDay()) >= 0) lista.push(d);
    return lista;
  }
  // Para cada dia de origem, a revisão vai ao primeiro dia de estudo na data devida ou depois; a volta seguinte conta dali.
  function revisoes(dias) {
    var porDia = dias.map(function () { return []; });
    dias.forEach(function (origem, i) {
      var marco = origem, j = i;
      for (var volta = 0; volta < INTERVALOS.length; volta++) {
        var devida = somar(marco, INTERVALOS[volta]);
        while (j < dias.length && dias[j] < devida) j++;
        if (j >= dias.length) break;
        porDia[j].push({origem: origem, volta: volta + 1});
        marco = dias[j];
      }
    });
    return porDia;
  }
  function itemDoDia(d, n, porDia, inicio) {
    var li = elemento('li');
    li.appendChild(elemento('span', 'dia', DIAS[d.getDay()] + ', ' + curta(d)));
    // Quantas de cada área, na ordem em que aparecem no dia (o rodízio continua do dia anterior).
    var ordem = [], conta = {};
    for (var k = 0; k < porDia; k++) {
      var area = AREAS[(inicio + k) % AREAS.length];
      if (!conta[area]) { conta[area] = 0; ordem.push(area); }
      conta[area]++;
    }
    var partes = ordem.map(function (a) { return conta[a] + ' de ' + a; });
    var lista = partes.length > 1 ? partes.slice(0, -1).join(', ') + ' e ' + partes[partes.length - 1] : partes[0];
    li.appendChild(document.createTextNode(plural(porDia, 'questão nova', 'questões novas') + ', uma área de cada vez: ' + lista + '.'));
    if (n.length) {
      var voltas = n.map(function (r) { return curta(r.origem) + ' (' + r.volta + 'ª volta)'; });
      li.appendChild(elemento('span', 'revisao', 'Revisão do que você errou ou chutou em ' + voltas.join(', ') + '.'));
    } else {
      li.appendChild(elemento('span', 'revisao', 'Sem revisão marcada para este dia.'));
    }
    return li;
  }
  function montar() {
    saida.textContent = ''; resumo.textContent = '';
    var opcao = select.selectedOptions[0];
    if (!opcao) {
      resumo.textContent = 'As provas desta lista já passaram. Confira as próximas datas nas páginas oficiais das bancas.';
      return;
    }
    var prova = lerData(opcao.getAttribute('data-data'));
    var nome = opcao.getAttribute('data-artigo') + ' ' + opcao.getAttribute('data-rotulo').replace(/^[A-ZÀ-Ý](?=[a-zà-ý])/, function (c) { return c.toLowerCase(); });
    var semana = Array.prototype.slice.call(form.querySelectorAll('input[name=dia]:checked')).map(function (c) { return Number(c.value); });
    var porDia = Number((form.querySelector('input[name=por-dia]:checked') || {value: 5}).value);
    if (!semana.length) {
      resumo.textContent = 'Marque pelo menos um dia livre na semana para ver o plano.';
      return;
    }
    var dias = diasDeEstudo(prova, semana);
    var faltam = dif(hoje, prova);
    if (!dias.length) {
      resumo.textContent = 'Nenhum dia livre até ' + nome + ', em ' + extenso(prova) + '.';
      saida.appendChild(elemento('p', '', 'Faltam ' + plural(faltam, 'dia', 'dias') + ' e nenhum deles cai num dia da semana que você marcou.'));
      return;
    }
    resumo.textContent = plural(dias.length, 'dia de estudo', 'dias de estudo') + ' até ' + nome + ', em ' + extenso(prova) + '.';
    saida.appendChild(elemento('p', '', 'Com ' + plural(porDia, 'questão', 'questões') + ' por dia, são ' + plural(dias.length * porDia, 'questão nova', 'questões novas') +
      ', mais as revisões. A conta começa hoje, ' + curta(hoje) + ', e vai até a véspera da prova.'));
    var rev = revisoes(dias);
    var lista = elemento('ol', 'plano-dias');
    dias.slice(0, VISIVEIS).forEach(function (d, i) { lista.appendChild(itemDoDia(d, rev[i], porDia, i * porDia)); });
    saida.appendChild(lista);
    if (dias.length > VISIVEIS) {
      var mais = elemento('details');
      mais.appendChild(elemento('summary', '', 'Ver os outros ' + plural(dias.length - VISIVEIS, 'dia', 'dias')));
      var resto = elemento('ol', 'plano-dias');
      resto.start = VISIVEIS + 1;
      dias.slice(VISIVEIS).forEach(function (d, i) { resto.appendChild(itemDoDia(d, rev[VISIVEIS + i], porDia, (VISIVEIS + i) * porDia)); });
      mais.appendChild(resto);
      saida.appendChild(mais);
    }
    var acoes = elemento('p', 'acoes');
    var botao = elemento('a', 'botao', 'Começar no PU');
    botao.href = '/criar-conta/';
    acoes.appendChild(botao);
    saida.appendChild(acoes);
  }
  form.addEventListener('change', montar);
  montar();
})();
