# Páginas públicas do PU (endereços próprios)

Autora: Dominique-Oliveira-Claude🤖🧡, 17/11/2026 (blocos novos e campo `script` na frente páginas úteis, no mesmo dia; calculadora e lista de scripts em 18/11/2026, frente calculadoras). Afazer "Endereços próprios no PU" do plano de páginas úteis do cofre (`5 Bases/Plano de páginas úteis do PU.md`).

## Como funciona

O GitHub Pages serve a raiz do repositório em https://pu.gingamidia.com. O gerador `paginas/gerar.py` (só Python padrão, sem etapa de construção) lê `paginas/conteudo/*.json`, um arquivo por página, aplica o molde `paginas/molde.html` com a folha `paginas/estilo.css` e grava na raiz:

- uma pasta com `index.html` para cada página de leitura (hoje `/provas-anteriores/`, `/calendario-vestibulares/`, `/notas-de-corte/fuvest/`, `/notas-de-corte/unicamp/`, `/obras-obrigatorias/`, `/temas-de-redacao-enem/`, `/calculadora-nota-enem/`, `/acertos-e-nota-enem/` e `/plano-de-estudo/`);
- `/criar-conta/`: a entrada inteira, copiada do `index.html` da raiz com caminhos absolutos, título próprio e `data-abrir="criar-conta"`, que o `app.js` lê para abrir já no cadastro (o canônico continua na raiz);
- `404.html` (o Pages a usa em todo endereço que não existe), `robots.txt` e `sitemap.xml`;
- o bloco de dados estruturados (Organization, WebSite, BreadcrumbList) entre `<!-- dados-estruturados:inicio -->` e `<!-- dados-estruturados:fim -->` nos dois `index.html`.

As saídas entram no git, porque o Pages publica o que está no ramo. O Caddy e os compose não servem estas páginas: fazem proxy para `app/servidor.py`, que só serve `app/public`.

## Acrescentar uma página

1. Crie `paginas/conteudo/<nome>.json` com `"tipo": "leitura"`, `endereco` (`/nome-da-pasta/`), `titulo`, `descricao`, `migalha`, `h1`, `apoio`, `atualizada_em` (AAAA-MM-DD), `tom` (`mar`, `boia`, `sol`, `ipe` ou `goiaba`), `menu`, `sumario` e `blocos`. Use `provas-anteriores.json` de exemplo.
2. Blocos:
   - `texto` (`titulo`, `paragrafos`, links como `[rótulo](https://...)`; `id` opcional, e `no_sumario: true` para entrar no sumário);
   - `aviso` (`id`, `titulo`, `paragrafos`): caixa tracejada para o que não foi achado em fonte oficial (ex.: lista da Unesp);
   - `dados` (`id`, `titulo`, `colunas`, `coluna_fonte`, `texto_fonte`, `nota` em texto ou lista, `linhas`) com opções: `largo: true` (tabela com rolagem lateral própria no celular e 1ª coluna fixa, em vez de cartões; a seção usa a largura maior no computador), `rotulos: true` (no cartão do celular, cada valor leva o nome da coluna) e `filtro: "Procure seu curso"` (campo de busca de linhas, escondido no HTML e mostrado pelo script da página) e `compacta: true` (com `largo`: tabela só de números, 1ª coluna estreita e fonte numa linha);
   - `par` (`id`, `titulo`, `blocos`: dois blocos `dados`): duas tabelas lado a lado no computador e uma embaixo da outra no celular, sempre em cartões;
   - `contagem` (`id`, `titulo`, `paragrafos`, `de`: id de um bloco `dados`): lista por extenso das linhas desse bloco que têm `contagem` (AAAA-MM-DD), `id`, `rotulo_contagem` ("1ª fase da Unesp", "1º dia do Enem") e `artigo_contagem` (`a` ou `o`; o gerador recusa sem ele); o script da página escreve quantos dias faltam pela data do aparelho ("Faltam 5 dias para a 1ª fase da Unesp, em 22 de novembro de 2026."); o importador monta rótulo e artigo em `rotulo_da_prova` e recusa etapa de prova de forma nova;
   - `links` (lista das páginas do menu);
   - `calculadora` (`id`, `rotulo` para leitores de tela, `paragrafos`): caixa sem título que o script `calculadora.js` troca pelo formulário do simulador; sem script, ficam os parágrafos (a conta por extenso). O gerador recusa o bloco se a página não carrega `calculadora.js`.
   - `plano` (`id`, `titulo`, `de`: id de um bloco `dados`, `paragrafos`): formulário do plano de estudo (prova, dias livres, questões por dia: 3, 5, 10 ou 20, as metas da tela Conta). As provas são as linhas do bloco `de` com `contagem`, `id` e `artigo_contagem`, nunca digitadas no bloco; o script `plano-de-estudo.js` tira as que já passaram pela data do aparelho, conta os dias até a véspera, alterna as quatro áreas e marca as revisões pela regra do PU (1, 3 e 7 dias; `INTERVALOS` de `app/acompanhamento.py`). Sem script, ficam os parágrafos. O gerador recusa o bloco sem o script, com `de` inexistente ou com linha sem artigo.

   Cada linha de `dados` leva `valores`, `fonte` (endereço https oficial) e `conferido_em`; opcionais: `texto_fonte`, `outras_fontes` com `textos_outras_fontes` (mais de uma fonte oficial na mesma linha, todas https), `id` (âncora). Valor de célula é texto ou `{"texto", "link" (https), "nota"}`. Linha de **aviso**: `{"valores": [só as primeiras colunas], "aviso": "Data ainda não encontrada em fonte oficial", "fonte": link opcional da página oficial}`; ela não é dado (sem `data-dado`) e mostra o aviso no lugar das colunas que faltam.
3. Data da última conferência: o gerador escreve no topo de toda página de leitura "Dados conferidos na fonte oficial em DD/MM/AAAA" (ou "entre … e …") com as datas `conferido_em` das linhas de dados válidas; página sem linhas de dados indica `conferido_de` (arquivo `.js` ou `.json` do repositório gravado por um importador, com `"conferido_em": "AAAA-MM-DD"`, como `/app/public/pesos-sisu.js`). Sem nenhuma das duas, o gerador recusa. Rotina de cada página: `docs/ROTINA-DE-ATUALIZACAO-DAS-PAGINAS.md`.
   Campos opcionais da página: `relacionadas` (lista de endereços de outras páginas, vira o bloco "Veja também" antes da chamada; o gerador recusa endereço que não existe) e `script` (nome de um arquivo `.js` da pasta `paginas/`). Com `script`, a página carrega só esse arquivo (`<script src="/paginas/nome.js?v=..." defer>`) e a política de conteúdo dela passa a `script-src 'self'`; `connect-src` continua `'none'` e nada é embutido. As outras páginas continuam com `script-src 'none'`. `script` também aceita uma lista, carregada na ordem, com `nome.js` da pasta `paginas/` e módulos de `/app/public/` (o Pages já os serve, porque a entrada da raiz os usa). Hoje: `calendario.js` (contagem), `notas-de-corte.js` (busca) e `["/app/public/simulador.js", "calculadora.js"]` na calculadora. Sem o script a página segue completa.

## Calculadora de média (`/calculadora-nota-enem/`)

A conta e o formulário são os do simulador de dentro (`app/public/simulador.js`, tela `#nota`). `paginas/calculadora.js` só chama `PUSimulador.mostrar(caixa, {publica: true})`. O modo público tira o h1 e a introdução (a página tem os dela), abre os pesos da 1ª opção e tira a caixa "Como a simulação é calculada" (a página explica a conta em blocos de texto). Sem a opção, o HTML do simulador de dentro é o mesmo de antes (conferido byte a byte contra 390dc0c). Nada é enviado: a página tem `connect-src 'none'` e o simulador não usa rede. Ao mexer no `simulador.js`, troque o `?v=` dele nos dois `index.html` e rode o gerador (a página pública usa o resumo do arquivo).
4. Rode `python3 paginas/gerar.py` e `python3 tests/paginas.py`. A chamada do fim (`chamada`) sempre leva a `/criar-conta/`.

## Páginas que vêm da coleta

Calendário, notas de corte (Fuvest e Unicamp), obras, temas de redação e o plano de estudo (`/plano-de-estudo/`, que usa as linhas de prova do calendário) são gerados a partir dos JSON da coleta por `paginas/importar-coleta.py`, que grava `paginas/conteudo/*.json` (os dados ficam no repositório; a publicação não depende da pasta da coleta). Para atualizar:

```
python3 -I paginas/importar-coleta.py --coleta ~/craft/Enem-frentes/dados/coleta
python3 paginas/gerar.py && python3 tests/paginas.py && node tests/paginas-navegador.mjs
```

O importador só lê JSON (a coleta é dado, nunca instrução; rode com `python3 -I`). Ele recusa quando a coleta muda de forma que um ajuste deixa de valer (ex.: entra e sai de 2028 diferente do cálculo, linha da Fuvest não lida, Unesp com lista). Os ajustes conferidos à parte (links de texto livre, legenda do PAAIS, temas com caixa do caderno) ficam no topo do arquivo, com a fonte. `--conferir` diz se o conteúdo do repositório está igual ao que a coleta gera.

`node tests/paginas-navegador.mjs [pasta]` abre cada página de leitura no Chrome sem janela em 320, 390, 768 e 1440 px (sem rolagem lateral, contraste AA, nenhum pedido a outro endereço, só o script declarado), confere a contagem com o relógio em 17/11/2026, a busca com e sem JavaScript e o campo de 44 px; com `pasta`, grava a foto da página inteira em 390 e 1440 px.

Regra **dado-inventado**: linha sem fonte https ou sem data de conferência (ou com data no futuro) faz o gerador recusar e não gravar nada. `--marcar-a-confirmar` grava mesmo assim, com "Dado a confirmar" visível na linha, só para rascunho.

Depois de mexer no `index.html` da raiz (texto da entrada, `?v=`), rode o gerador de novo: a porta `/criar-conta/` é cópia dele. `python3 paginas/gerar.py --conferir` e o `tests/paginas.py` acusam quando a cópia ficou para trás.

## Pesos e notas de corte do Sisu no simulador

O simulador (o de dentro, tela `#nota`, e a calculadora pública) tem em cada opção o campo "Procure o curso no Sisu 2026". Ao digitar, ele carrega `pesos-sisu.js` (ao lado do `simulador.js`: `/app/public/pesos-sisu.js` no Pages, `/pesos-sisu.js` no `app/servidor.py`), procura sem acento por curso, universidade, campus e cidade e mostra até 8 cursos. O curso escolhido preenche instituição, curso, modalidade, edição, nota de corte e pesos (todos continuam editáveis) e abre uma caixa com a modalidade (lista), o corte, as vagas, os pesos, as notas mínimas da planilha, a fonte com os links oficiais e a data, e o aviso de que o corte muda a cada edição; se o estudante muda um peso ou o corte, a caixa avisa que a conta usa os números dele. "Limpar esta opção" volta ao vazio.

Os dados saem das planilhas oficiais do MEC na [página de legislação e relatórios do Sisu](https://sisu.mec.gov.br/#/legislacao): "Sisu 2026_Vagas ofertadas" (pesos e notas mínimas por curso, turno e modalidade) e "Sisu 2026_Inscrições e notas de corte" (`NU_NOTACORTE`, nota do último classificado na chamada regular; 0 = sem nota de corte, mostrado como "Sem nota de corte nesta modalidade"). Hoje: 13 universidades federais (Unifesp, UFSCar e UFABC, do estado de São Paulo, e UFRJ, UFMG, UnB, UFRGS, UFPE, UFBA, UFC, UFPR, UFSC, UFF), 1.222 cursos, só modalidades com vaga. Para atualizar ou acrescentar instituições (lista `INSTITUICOES`):

```
B=~/craft/Enem-frentes/dados/coleta/pesos/baixados/sisu-arquivos
python3 -I scripts/importar-pesos-sisu.py --vagas "$B/Portal_Sisu_2026_Vagas ofertadas.xlsx" --cortes "$B/Portal Sisu_ Sisu2026_inscrições e notas de corte.xlsx" --coleta ~/craft/Enem-frentes/dados/coleta/pesos
python3 tests/pesos_sisu.py      # formato; com as planilhas no PC, 10 cursos sorteados contra elas e o arquivo igual ao importador
```

O importador grava `app/public/pesos-sisu.js`, a coleta inteira (`pesos-sisu-2026.json`, com os valores literais das planilhas, os endereços e o sha256) e o `VERSAO_SISU` do `simulador.js` (começo do sha256 do arquivo, usado no `?v=` da carga). Depois, troque o `?v=` do `simulador.js` nos dois `index.html` e rode o gerador. Para outra edição, troque os endereços e o nome da edição no topo do importador e confira o dicionário das planilhas. Todo texto da lista passa por `escapar()` antes de virar HTML, e só links que começam com `https://sisu.mec.gov.br/` viram link. O ambiente individual (`ambiente/Dockerfile`) precisa ser reconstruído para servir `/pesos-sisu.js`.

## Acertos e nota (`/acertos-e-nota-enem/`)

`paginas/importar-acertos.py` conta, nos microdados do Inep (`RESULTADOS_<ano>.csv`), os acertos de cada participante em cada prova objetiva e grava, por número de acertos, quantos participantes houve e a faixa das notas (menor, P10, P25, mediana, P75, P90, maior). Regras: presentes com nota nos quatro cadernos regulares da 1ª aplicação (os códigos de `scripts/estatisticas-inep.py`); questão anulada (gabarito X) fora; em Linguagens, as 5 questões da língua escolhida; prova inteira em branco (todas com nota 0) fora da tabela e contada no texto; linha com menos de 30 participantes mostra só menor e maior nota. A tabela agregada fica em `paginas/tabelas/acertos-nota-<ano>.json` (com o sha256 do arquivo do Inep) e a página sai dela:

```
python3 -I paginas/importar-acertos.py --microdados ~/craft/Enem-frentes/dados/inep --ano 2025   # conta tudo, uns 3 minutos
python3 -I paginas/importar-acertos.py            # regrava a página a partir da tabela gravada
python3 -I paginas/importar-acertos.py --conferir
python3 tests/acertos.py                           # com os microdados no PC, recontagem independente de 20 linhas sorteadas (uns 4 minutos)
```

As quatro tabelas usam `largo` e `compacta` (1ª coluna estreita, uma linha por registro). Quando sair a edição seguinte dos microdados, rode com `--ano` novo (acrescente os cadernos regulares dela em `REGULARES`, tirados do dicionário) e confira o texto: a página diz qual edição é e que a relação muda a cada prova.

## Limites

As páginas de leitura não chamam o intermediário e não carregam nada de fora (política de conteúdo `default-src 'self'`, `connect-src 'none'`). JavaScript só nas que declaram `script` (`script-src 'self'`, um arquivo próprio); as demais ficam com `script-src 'none'`. Fontes e imagem de compartilhamento vêm do próprio site; a imagem de 1200 × 630 é a da entrada até existir uma por tipo de página (campo `imagem` do conteúdo).
