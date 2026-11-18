'use strict';
const assert=require('node:assert/strict');
const {areas,calcular,numero}=require('../app/public/simulador.js');
const obj=valores=>Object.fromEntries(areas.map(([id],i)=>[id,valores[i]]));
const perto=(a,b)=>assert(Math.abs(a-b)<1e-8,`${a} != ${b}`);
const notas=obj([800,750,800,750,850]);
// Exemplo real da Etapa 1 da planilha do cofre: pesos 2,1,2,1,2.
const pesos=obj([2,1,2,1,2]);
const r=calcular(notas,pesos,810);
perto(r.media,800);perto(r.mediaSimples,790);perto(r.diferenca,-10);
perto(r.parcelas.reduce((s,n)=>s+n,0),r.media);
for(const n of r.necessarias) {
 const novas={...notas,[n.id]:n.nota};
 perto(calcular(novas,pesos).media,810);
}
perto(calcular(notas,obj([1,1,1,1,1])).media,790);
perto(calcular(notas,obj([0,0,0,0,1]),900).media,850);
assert.equal(calcular(notas,obj([0,0,0,0,1]),900).necessarias[0].estado,'sem-peso');
assert.equal(calcular(notas,pesos,'').meta,null);
assert.equal(calcular(notas,pesos,0).meta,0);
assert.equal(calcular(notas,pesos,0).necessarias[0].estado,'atingida');
assert.equal(calcular(notas,pesos,1500).necessarias[4].estado,'acima-limite');
perto(numero(' 785,25 ','nota'),785.25);
for(const entrada of ['',null,undefined,NaN,Infinity,-1,'1.234,5','1e3','abc',{},true]) assert.throws(()=>numero(entrada,'nota'));
assert.throws(()=>calcular(notas,obj([0,0,0,0,0])),/peso/);
assert.throws(()=>calcular({...notas,redacao:1001},pesos),/Redação/);
// Notas objetivas não são limitadas artificialmente a 1.000.
perto(calcular(obj([1001,1001,1001,1001,1000]),obj([1,1,1,1,1])).media,1000.8);
for(let i=0;i<50;i++) {
 const ns=obj([i*10,200+i,350+i*2,900-i,600]);
 const ps=obj([i+1,2,0,4,3]);
 perto(calcular(ns,ps).media,calcular(ns,obj([i+1,2,0,4,3].map(p=>p*7))).media);
}
// Modo público (/calculadora-nota-enem/): sem h1 próprio e sem o texto da conta; o de dentro continua com os dois.
const {mostrar,limpar}=require('../app/public/simulador.js');
const desenhar=opcoes=>{const vazio=()=>({addEventListener(){},focus(){},replaceChildren(){},elements:{},dataset:{}});const c={innerHTML:'',querySelector:vazio,querySelectorAll:()=>[]};limpar();mostrar(c,opcoes);return c.innerHTML;};
const dentro=desenhar(), publica=desenhar({publica:true});
assert(dentro.includes('<h1 id="titulo-nota">')&&dentro.includes('sair da conta')&&dentro.includes('<details><summary>Pesos'));
assert(!publica.includes('<h1')&&!publica.includes('sair da conta')&&publica.includes('<details open><summary>Pesos')&&publica.includes('simulador-publico'));
console.log('OK: média simples/ponderada, exemplo da planilha, inversão por área, pesos zero, metas vazias/zero/impossíveis, decimais, entradas inválidas e modo público da calculadora.');
