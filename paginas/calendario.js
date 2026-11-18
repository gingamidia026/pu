/* Contagem regressiva do calendário dos vestibulares (paginas/gerar.py liga este arquivo só nesta página).
   Lê as datas que já estão no HTML (<li data-data="AAAA-MM-DD">), compara com a data do aparelho e escreve
   quantos dias faltam para a próxima prova. Não busca nada na rede. Sem este script, a lista mostra as datas por extenso.
   Dominique-Oliveira-Claude🤖🧡, 17/11/2026. */
(function () {
  'use strict';
  var saida = document.querySelector('[data-contagem-saida]');
  var itens = Array.prototype.slice.call(document.querySelectorAll('.datas-de-prova li[data-data]'));
  if (!saida || !itens.length) return;
  var agora = new Date();
  var hoje = new Date(agora.getFullYear(), agora.getMonth(), agora.getDate());
  var dia = 24 * 60 * 60 * 1000;
  var proxima = null;
  itens.forEach(function (item) {
    var partes = item.getAttribute('data-data').split('-').map(Number);
    var data = new Date(partes[0], partes[1] - 1, partes[2]);
    if (data < hoje) {
      item.classList.add('passou');
      var marca = document.createElement('span');
      marca.className = 'ja-foi';
      marca.textContent = ' (já passou)';
      item.appendChild(marca);
    } else if (!proxima) {
      proxima = { item: item, dias: Math.round((data - hoje) / dia) };
    }
  });
  if (!proxima) {
    saida.textContent = 'As provas desta lista já passaram. Confira as próximas datas nas páginas oficiais.';
    return;
  }
  proxima.item.classList.add('proxima');
  // Rótulo da lista ("1ª fase da Unesp", "Prova de Conhecimentos Gerais da Famerp") com o artigo dado pelo gerador
  // (data-artigo): "a 1ª fase da Unesp", "o 1º dia do Enem", "a prova de Conhecimentos Gerais da Famerp".
  var rotulo = proxima.item.querySelector('a').textContent;
  if (/^[A-ZÀ-Ý][a-zà-ý]/.test(rotulo)) rotulo = rotulo.charAt(0).toLowerCase() + rotulo.slice(1);
  var nome = (proxima.item.getAttribute('data-artigo') || 'a') + ' ' + rotulo;
  var quando = proxima.item.querySelector('time').textContent;
  if (proxima.dias === 0) {
    saida.textContent = 'A próxima prova é hoje: ' + nome + '.';
  } else {
    saida.textContent = (proxima.dias === 1 ? 'Falta 1 dia' : 'Faltam ' + proxima.dias + ' dias') + ' para ' + nome + ', em ' + quando + '.';
  }
})();
