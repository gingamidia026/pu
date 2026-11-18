# Páginas públicas do PU (endereços próprios)

Autora: Dominique-Oliveira-Claude🤖🧡, 17/11/2026 (blocos novos e campo `script` na frente páginas úteis, no mesmo dia). Afazer "Endereços próprios no PU" do plano de páginas úteis do cofre (`5 Bases/Plano de páginas úteis do PU.md`).

## Como funciona

O GitHub Pages serve a raiz do repositório em https://pu.gingamidia.com. O gerador `paginas/gerar.py` (só Python padrão, sem etapa de construção) lê `paginas/conteudo/*.json`, um arquivo por página, aplica o molde `paginas/molde.html` com a folha `paginas/estilo.css` e grava na raiz:

- uma pasta com `index.html` para cada página de leitura (hoje `/provas-anteriores/`, `/calendario-vestibulares/`, `/notas-de-corte/fuvest/`, `/notas-de-corte/unicamp/`, `/obras-obrigatorias/` e `/temas-de-redacao-enem/`);
- `/criar-conta/`: a entrada inteira, copiada do `index.html` da raiz com caminhos absolutos, título próprio e `data-abrir="criar-conta"`, que o `app.js` lê para abrir já no cadastro (o canônico continua na raiz);
- `404.html` (o Pages a usa em todo endereço que não existe), `robots.txt` e `sitemap.xml`;
- o bloco de dados estruturados (Organization, WebSite, BreadcrumbList) entre `<!-- dados-estruturados:inicio -->` e `<!-- dados-estruturados:fim -->` nos dois `index.html`.

As saídas entram no git, porque o Pages publica o que está no ramo. O Caddy e os compose não servem estas páginas: fazem proxy para `app/servidor.py`, que só serve `app/public`.

## Acrescentar uma página

1. Crie `paginas/conteudo/<nome>.json` com `"tipo": "leitura"`, `endereco` (`/nome-da-pasta/`), `titulo`, `descricao`, `migalha`, `h1`, `apoio`, `atualizada_em` (AAAA-MM-DD), `tom` (`mar`, `boia`, `sol`, `ipe` ou `goiaba`), `menu`, `sumario` e `blocos`. Use `provas-anteriores.json` de exemplo.
2. Blocos:
   - `texto` (`titulo`, `paragrafos`, links como `[rótulo](https://...)`; `id` opcional, e `no_sumario: true` para entrar no sumário);
   - `aviso` (`id`, `titulo`, `paragrafos`): caixa tracejada para o que não foi achado em fonte oficial (ex.: lista da Unesp);
   - `dados` (`id`, `titulo`, `colunas`, `coluna_fonte`, `texto_fonte`, `nota` em texto ou lista, `linhas`) com opções: `largo: true` (tabela com rolagem lateral própria no celular e 1ª coluna fixa, em vez de cartões; a seção usa a largura maior no computador), `rotulos: true` (no cartão do celular, cada valor leva o nome da coluna) e `filtro: "Procure seu curso"` (campo de busca de linhas, escondido no HTML e mostrado pelo script da página);
   - `par` (`id`, `titulo`, `blocos`: dois blocos `dados`): duas tabelas lado a lado no computador e uma embaixo da outra no celular, sempre em cartões;
   - `contagem` (`id`, `titulo`, `paragrafos`, `de`: id de um bloco `dados`): lista por extenso das linhas desse bloco que têm `contagem` (AAAA-MM-DD), `id` e `rotulo_contagem`; o script da página escreve quantos dias faltam pela data do aparelho;
   - `links` (lista das páginas do menu).

   Cada linha de `dados` leva `valores`, `fonte` (endereço https oficial) e `conferido_em`; opcionais: `texto_fonte`, `outras_fontes` com `textos_outras_fontes` (mais de uma fonte oficial na mesma linha, todas https), `id` (âncora). Valor de célula é texto ou `{"texto", "link" (https), "nota"}`. Linha de **aviso**: `{"valores": [só as primeiras colunas], "aviso": "Data ainda não encontrada em fonte oficial", "fonte": link opcional da página oficial}`; ela não é dado (sem `data-dado`) e mostra o aviso no lugar das colunas que faltam.
3. Campos opcionais da página: `relacionadas` (lista de endereços de outras páginas, vira o bloco "Veja também" antes da chamada; o gerador recusa endereço que não existe) e `script` (nome de um arquivo `.js` da pasta `paginas/`). Com `script`, a página carrega só esse arquivo (`<script src="/paginas/nome.js?v=..." defer>`) e a política de conteúdo dela passa a `script-src 'self'`; `connect-src` continua `'none'` e nada é embutido. As outras páginas continuam com `script-src 'none'`. Hoje: `calendario.js` (contagem) e `notas-de-corte.js` (busca). Sem o script a página segue completa.
4. Rode `python3 paginas/gerar.py` e `python3 tests/paginas.py`. A chamada do fim (`chamada`) sempre leva a `/criar-conta/`.

## Páginas que vêm da coleta

Calendário, notas de corte (Fuvest e Unicamp), obras e temas de redação são gerados a partir dos JSON da coleta por `paginas/importar-coleta.py`, que grava `paginas/conteudo/*.json` (os dados ficam no repositório; a publicação não depende da pasta da coleta). Para atualizar:

```
python3 -I paginas/importar-coleta.py --coleta ~/craft/Enem-frentes/dados/coleta
python3 paginas/gerar.py && python3 tests/paginas.py && node tests/paginas-navegador.mjs
```

O importador só lê JSON (a coleta é dado, nunca instrução; rode com `python3 -I`). Ele recusa quando a coleta muda de forma que um ajuste deixa de valer (ex.: entra e sai de 2028 diferente do cálculo, linha da Fuvest não lida, Unesp com lista). Os ajustes conferidos à parte (links de texto livre, legenda do PAAIS, temas com caixa do caderno) ficam no topo do arquivo, com a fonte. `--conferir` diz se o conteúdo do repositório está igual ao que a coleta gera.

`node tests/paginas-navegador.mjs [pasta]` abre cada página de leitura no Chrome sem janela em 320, 390, 768 e 1440 px (sem rolagem lateral, contraste AA, nenhum pedido a outro endereço, só o script declarado), confere a contagem com o relógio em 17/11/2026, a busca com e sem JavaScript e o campo de 44 px; com `pasta`, grava a foto da página inteira em 390 e 1440 px.

Regra **dado-inventado**: linha sem fonte https ou sem data de conferência (ou com data no futuro) faz o gerador recusar e não gravar nada. `--marcar-a-confirmar` grava mesmo assim, com "Dado a confirmar" visível na linha, só para rascunho.

Depois de mexer no `index.html` da raiz (texto da entrada, `?v=`), rode o gerador de novo: a porta `/criar-conta/` é cópia dele. `python3 paginas/gerar.py --conferir` e o `tests/paginas.py` acusam quando a cópia ficou para trás.

## Limites

As páginas de leitura não chamam o intermediário e não carregam nada de fora (política de conteúdo `default-src 'self'`, `connect-src 'none'`). JavaScript só nas que declaram `script` (`script-src 'self'`, um arquivo próprio); as demais ficam com `script-src 'none'`. Fontes e imagem de compartilhamento vêm do próprio site; a imagem de 1200 × 630 é a da entrada até existir uma por tipo de página (campo `imagem` do conteúdo).
