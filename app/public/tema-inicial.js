'use strict';
/* Pé na Universidade (PU): tema antes do primeiro quadro.
   Dominique-Oliveira-Claude🤖🧡, 14/11/2026 (integração 2). O app.js carrega com defer e o navegador pode desenhar um quadro
   antes de ele rodar: sem isto, quem usa o noturno via um clarão branco ao abrir. Roda síncrono no <head>, antes do <body>,
   e repete só a decisão do tema do app.js (temaEmVigor e a condição de retomar a conta em iniciar). O app.js confere depois. */
(function () {
  try {
    const ler = chave => { const v = localStorage.getItem(chave); return v === null ? null : JSON.parse(v); };
    const painel = ler('pu.painel.v2');
    if (!painel || !painel.conta) return;
    if (document.documentElement.dataset.publico === '1') {
      const salva = ler('pu.sessao.v1');
      const valida = salva && salva.expira > Date.now() && /^[A-Za-z0-9_-]{20,100}$/.test(salva.token || '');
      if (!(window.ENEM_PUBLICO || {}).habilitado || !valida) return;
    }
    const prefs = ler('pu.prefs.v1.' + (painel.conta.id ?? 0)) || {};
    let tema = prefs.tema === 'diurno' || prefs.tema === 'noturno' ? prefs.tema : '';
    if (!tema) {
      const valido = f => { if (!f || typeof f !== 'string') return false; try { new Intl.DateTimeFormat('en-US', {timeZone: f}); return true; } catch { return false; } };
      let fuso = valido(prefs.fuso) ? prefs.fuso : '';
      if (!fuso) { try { const f = Intl.DateTimeFormat().resolvedOptions().timeZone; fuso = valido(f) ? f : ''; } catch { fuso = ''; } }
      let hora = new Date().getHours();
      if (fuso) {
        try {
          const h = Number(new Intl.DateTimeFormat('en-US', {timeZone: fuso, hour: 'numeric', hourCycle: 'h23'}).formatToParts(new Date()).find(p => p.type === 'hour')?.value);
          if (Number.isFinite(h)) hora = h % 24;
        } catch { /* fica o relógio do aparelho */ }
      }
      tema = hora >= 6 && hora < 18 ? 'diurno' : 'noturno';
    }
    document.documentElement.dataset.tema = tema;
  } catch { /* Armazenamento bloqueado ou dado estranho: o app.js decide sozinho. */ }
})();
