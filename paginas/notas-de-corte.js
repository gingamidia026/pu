/* Busca por curso nas páginas de notas de corte (paginas/gerar.py liga este arquivo só nelas).
   Mostra o campo de busca que o HTML traz escondido e esconde as linhas da tabela cujo curso não tem o texto digitado.
   Não busca nada na rede. Sem este script, o campo fica escondido e a tabela aparece inteira.
   Dominique-Oliveira-Claude🤖🧡, 17/11/2026. */
(function () {
  'use strict';
  function simples(texto) {
    return texto.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
  }
  Array.prototype.forEach.call(document.querySelectorAll('[data-filtro]'), function (caixa) {
    var secao = document.getElementById(caixa.getAttribute('data-filtro'));
    var campo = caixa.querySelector('input');
    var total = caixa.querySelector('.filtro-total');
    if (!secao || !campo) return;
    var linhas = Array.prototype.slice.call(secao.querySelectorAll('tbody tr'));
    var nomes = linhas.map(function (linha) { return simples(linha.cells[0].textContent); });
    function filtrar() {
      var procura = simples(campo.value);
      var vistas = 0;
      linhas.forEach(function (linha, i) {
        var mostra = !procura || nomes[i].indexOf(procura) !== -1;
        linha.hidden = !mostra;
        if (mostra) vistas += 1;
      });
      if (!procura) total.textContent = linhas.length + ' linhas na tabela.';
      else if (!vistas) total.textContent = 'Nenhum curso com "' + campo.value.trim() + '". Tente outra parte do nome.';
      else total.textContent = vistas + (vistas === 1 ? ' linha encontrada.' : ' linhas encontradas.');
    }
    campo.addEventListener('input', filtrar);
    caixa.hidden = false;
    filtrar();
  });
})();
