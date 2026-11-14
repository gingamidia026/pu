# Provas do PU: Enem, Fuvest, Unesp, Unicamp e Famerp

Autora: Dominique-Oliveira-Claude🤖🧡. Pedido de Dominique Oliveira🐧❤️ em 14/11/2026: os últimos cinco anos de provas do Enem, USP, Unesp, Unicamp e Famerp, com a plataforma fluida, e a escolha das provas que cada pessoa vai prestar.

## Catálogo

- Origem verdadeira: as notas do cofre Vestibular, uma por questão, em `Provas Enem/Questões`, `Provas Fuvest/Questões`, `Provas Unesp/Questões`, `Provas Unicamp/Questões` e `Provas Famerp/Questões`. Só a do Enem é obrigatória. `scripts/sincronizar-questoes.py` exporta tudo para `.catalogo/atual.json`, como antes.
- Chave estável por questão: `<prova>:<ano>:<dia>:<caderno>:<número>`. A do Enem não mudou (`enem:2024:1:1:1`), então os IDs e o histórico de respostas continuam ligados às mesmas questões. Questões novas recebem IDs novos, sem reutilizar.
- Campos novos de cada questão no catálogo: `prova` (`enem`, `fuvest`, `unesp`, `unicamp`, `famerp`), `edicao` ("Fuvest 2026"), `fonteNome` (Inep, Fuvest, Vunesp ou Comvest) e `fonte`, o endereço oficial do PDF. Fora do Enem, a nota precisa de `fonte_url` num endereço oficial (`www.fuvest.br`, `www.comvest.unicamp.br`, `documento.vunesp.com.br`).
- Letras por prova: Unicamp tem A a D; as outras, A a E.
- Questão com dúvida de extração ou de gabarito: a nota fica no cofre com `fora_do_ar: true` e o motivo, e a sincronização a deixa fora do catálogo (`foraDoAr` no resumo). Anulada continua fora do treino.
- Só a parte objetiva com gabarito oficial. As fases dissertativas são decisão de Dominique (afazer "Fases dissertativas no PU").

## Extrator

O mesmo `ferramentas/importar-prova` importa e corrige (regra **extrator-unico-em-lotes**).

- `reparo_texto.py`: os cadernos do Enem 2021 usam a Arial com glifos `gNN` sem mapa Unicode, e o pdftotext devolvia lixo. O reparo compara o desenho de cada glifo com glifos de nome conhecido e, sem par, usa a ordem padrão de glifos conferida contra 110 glifos (até o 171 igual; do 173 ao 256 deslocada em um). Só completa o que falta no mapa da fonte. O que sobra vira U+FFFD e a questão sai do ar. A cópia reparada vai para um cache fora do cofre; o PDF original não muda.
- Cabeçalho e rodapé sem faixa (2021 a 2023), letra da alternativa separada do texto (2022) e linha justificada partida (2021) são tratados no recorte. 2024 e 2025 saem iguais às notas publicadas (180 de 180 em cada caderno).
- Uma questão que falha não derruba a prova: vira pendência e, na gravação, nota fora do ar. A correção automática do `pu reiniciar` preserva essas notas em vez de travar o lote.
- A assinatura da ferramenta na correção automática cobre todos os `.py` do extrator.

## Provas ativas de cada conta (contrato para a interface)

Sem rota nova: o intermediário público não muda.

- **Ler:** `GET /api/painel` traz `provas: {disponiveis: [{id, nome, questoes, edicoes: [2027, 2026, ...]}], ativas: ["enem", ...]}` e `catalogo.ativas` (questões das provas ativas). `disponiveis` vem na ordem Enem, Fuvest (USP), Unesp, Unicamp, Famerp, só com as que existem no catálogo.
- **Gravar:** `POST /api/dispositivos` com `{"acao": "provas", "ativas": ["enem", "fuvest"]}`. Resposta `{"ok": true, "provas": {disponiveis, ativas}}`. Lista vazia, sigla desconhecida, valor que não é lista ou mais de 20 itens: 400, nada gravado. Sem sessão: 401. Depois de gravar, a interface pede `/api/painel` de novo (índice, densidade e questão inicial mudam).
- **Padrão:** sem escolha gravada, todas as provas estão ativas, inclusive as que entrarem no catálogo depois. Gravar a lista completa apaga a escolha e volta ao padrão. A conta de teste segue o padrão.
- **O que respeita a lista:** índice de matérias e assuntos (foco por matéria), densidade (volta pelo banco), questão inicial do dia, revisão espaçada (caderno e vencidas), perfil por assunto e o simulado (que a interface sorteia do índice e da densidade). A média semanal dos usuários continua calculada com o catálogo inteiro, porque é comum a todas as contas.
- **Volta pelo banco:** questão nova no catálogo, ou de prova reativada, entra na volta em andamento. Questão de prova desativada fica registrada, mas sai da conta e da fila; a volta termina quando todas as questões das provas ativas foram feitas.
- `GET /api/questoes/<id>` continua respondendo qualquer questão do catálogo pelo ID (o envio de uma questão de prova desativada é aceito e entra no histórico).
- O campo antigo `questoes` do painel (lista do catálogo inteiro) agora vem vazio: com as cinco provas passaria de 100 KB, e a interface atual não o usa.

## O que ainda supõe só o Enem

Fica para a frente da interface e para decisões de Dominique (afazer "Simulado com várias provas no PU"): o texto "Prova original no site do Inep" (usar `fonteNome`), a busca "Enem <ano> resolução comentada" (usar `edicao`), o tempo de referência de 3 minutos por questão do Enem no simulado, o aviso de TRI e o simulador de nota (só Enem), a composição do simulado com várias provas e as alternativas A a D da Unicamp na tela. Dia e caderno continuam no catálogo; fora do Enem, dia é 1 e caderno é a versão da prova (`V1`, `QY`).

## Verificação

`python3 tests/provas_ativas.py` (padrão com todas, gravação, recorte, isolamento entre contas, volta só com as ativas, quatro alternativas, conta de teste e catálogo sintético de 2.480 questões com painel abaixo de 100 KB), `tests/testar.py`, `tests/acompanhamento.py`, `tests/conjuntos.py`, `tests/sincronizacao.py`; extrator com a cópia do cofre: `PU_COFRE_VESTIBULAR=<cópia> .venv-extracao/bin/python -I tests/extracao.py` e `tests/extracao_enem_antigo.py`. Fluidez: `python3 tests/medir_fluidez.py <pasta do catálogo>`.

## Atualizações

- 14/11/2026 06:12 · Dominique-Oliveira-Claude🤖🧡 · Documento criado com o catálogo de cinco provas, o extrator e o contrato das provas ativas. **Por quê:** pedido de Dominique Oliveira🐧❤️ de 14/11/2026.
