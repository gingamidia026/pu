/* Calculadora de média aberta (/calculadora-nota-enem/). A conta e o formulário são os do simulador de dentro do PU
   (app/public/simulador.js, carregado antes deste arquivo); aqui só se liga o modo público, sem conta e sem rede.
   Sem JavaScript, a página mostra a fórmula e o exemplo por extenso. Dominique-Oliveira-Claude🤖🧡, 18/11/2026. */
(function () {
  'use strict';
  var caixa = document.querySelector('[data-calculadora]');
  if (!caixa || !window.PUSimulador) return;
  window.PUSimulador.mostrar(caixa, {publica: true});
})();
