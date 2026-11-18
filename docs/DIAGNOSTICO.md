# Diagnóstico de erros do aluno

Autora: Dominique-Oliveira-Claude🤖🧡. Afazer "Diagnóstico de erros no PU", 17/11/2026.

A tela `#diagnostico` ("Onde você mais erra") mostra ao aluno, pelas questões que ele mesmo respondeu, os assuntos em que mais erra, como está em relação à média dos outros alunos e o que estudar primeiro.

## De onde vem cada dado

| Dado | Origem |
|---|---|
| Respostas do aluno | Tabela `respostas` do banco do PU (`conta`, `questao`, `acerto`, `chute`, `criada`), só da conta da sessão. |
| Assunto e matéria | Campos `materia` e `topico` do catálogo (`.catalogo/atual.json`), os mesmos do perfil por matéria e do foco do Estudar. São a classificação do próprio PU, sem fonte oficial por questão. |
| Assunto em revisão | Campo `revisar` do catálogo (66 questões no catálogo de 14/11: 34 do Enem, 12 da Fuvest, 12 da Unesp, 8 da Unicamp). |
| Provas ativas | Escolha da conta em Conta (`app/provas.py`); questões de prova desligada ficam fora, como no perfil. |
| Média dos outros alunos | As mesmas respostas de todas as contas reais, agregadas por semana na tabela `medias` (chave `diagnostico:<segunda-feira>`). |

Nada vem do gabarito, das soluções ou da estatística do Inep. A frequência dos assuntos no Enem ficou de fora: a distribuição por assunto do catálogo não foi validada (`docs/ESTATISTICAS-INEP.md`) e não pode pesar a ordem como se fosse oficial.

## Cálculo (`diagnostico()` em `app/acompanhamento.py`)

1. **Primeira tentativa.** De cada questão vale só a primeira resposta da conta, dada antes de ver a correção. Refazer a questão depois de ver o gabarito não muda o diagnóstico.
2. **Tropeço.** Erro ou acerto marcado como "chutei". Acerto seguro é o acerto sem chute (a mesma regra da revisão espaçada).
3. **Mínimo: 5 questões diferentes no assunto** (`MINIMO_DIAGNOSTICO`). Abaixo disso o assunto vai para "Ainda não dá para concluir", com o número de questões feitas e quantas faltam, sem porcentagem. Cinco é o menor número em que um único acerto ou erro muda o resultado em 20 pontos, e o mesmo mínimo que o PU já usa para a média dos usuários. Um assunto do catálogo tem menos de 5 questões (Física, "Conhecimentos básicos e fundamentais", 3): ele nunca chega ao resultado.
4. **Precisa de treino:** acerto seguro abaixo de 60% (`CORTE_TREINO`), o corte que o "Próximo passo" do Progresso já usava. Com 60% ou mais o assunto vai para "Você vai bem em".
5. **Ordem "o que estudar primeiro":** dentro de "precisa de treino", do maior para o menor **limite inferior do intervalo de Wilson de 95%** da taxa de tropeço (`wilson_inferior`, z = 1,96):

   `(p + z²/2n − z·√(p(1−p)/n + z²/4n²)) / (1 + z²/n)`, com p = tropeços / n e n = questões feitas no assunto.

   Com a mesma taxa de erro, o assunto com mais respostas fica à frente; um assunto com poucas respostas e taxa alta não passa à frente de outro com muitas respostas e taxa um pouco menor (exemplo do teste: 4 tropeços em 5, Wilson 0,38, fica atrás de 14 em 20, Wilson 0,48). Empate: mais tropeços, depois mais questões, depois matéria e assunto em ordem alfabética.
6. **Lista final:** primeiro "precisa de treino" (nessa ordem), depois "vai bem" (mesma ordem) e por último "ainda não dá para concluir" (mais questões feitas primeiro). O primeiro de "precisa de treino" vira o "Comece por".

## Média dos outros alunos e privacidade

- Mesma medida do aluno: percentual de acerto seguro na primeira tentativa, por assunto. Entra só quem tem 5 questões ou mais no assunto; a média só aparece com **5 ou mais outros alunos** (`MINIMO_ALUNOS`).
- Respostas até a segunda-feira 00h (UTC) da semana, em cache semanal: uma resposta nova de outro aluno não muda a média na hora.
- A conta de teste fica fora, e a própria conta sai da soma (a média é "dos outros").
- A resposta da API leva só números do próprio aluno e a média arredondada: nenhum identificador de conta, e-mail, questão ou resposta de outro aluno (conferido em `tests/acompanhamento.py`).

## Onde aparece e quanto custa

- O servidor manda `diagnostico` no `GET /api/painel` e no `acompanhamento` da resposta de `POST /api/questoes/<id>` (questão avulsa e conjunto). São rotas que o intermediário público já aceita: nenhuma rota nova e nenhuma viagem a mais (~3 s cada). A tela monta com o painel já guardado no aparelho.
- Tamanho: um item por assunto com resposta (47 assuntos no catálogo, de 170 a 280 bytes cada, conforme o tamanho do nome), bem abaixo dos 100 KB (`tests/provas_ativas.py` confere o painel com 2.480 questões).
- Entradas: o "Próximo passo" do Progresso passa a ser o "Comece por" do diagnóstico, com o botão "Ver todos os assuntos" (ou "Ver onde você mais erra"); a tela de meta cumprida diz em que assunto o aluno mais erra, com link. O menu continua com cinco destinos (um sexto não cabe em 320 px) e marca Progresso na tela do diagnóstico.
- "Treinar" leva ao Estudar com o foco no assunto (o mesmo foco por matéria e assunto que já existia).

## Classificações em revisão e inglês

- As **questões com `revisar`** ficam fora da conta, e a tela diz quantas respostas ficaram de fora. Motivo: `docs/CLASSIFICACOES-EM-REVISAO.md` diz que elas seguem em revisão e que nenhuma classificação foi trocada; com o assunto incerto, a resposta poderia apontar o aluno para o assunto errado.
- As **3 questões de inglês** com habilidade divergente (enem:2024:1:1:2, enem:2024:1:1:4, enem:2025:1:1:3) diferem só na habilidade citada no campo `assunto`. O diagnóstico agrupa pelo `topico`, que é "Língua estrangeira moderna" nas 10 questões de inglês, então elas entram normalmente e o resultado não muda com a revisão da habilidade.

## O que fica para Dominique decidir

1. Mínimo de 5 questões por assunto e corte de 60%: valores escolhidos agora, documentados aqui e nas constantes do `app/acompanhamento.py`.
2. Questões em revisão: deixar de fora (como está) ou contar com marca na tela.
3. "Chutei" certo contar como tropeço (como está) ou como acerto.
4. Alternativa errada mais escolhida pelo aluno (citada no cartão): não entrou. O que existe é a errada mais marcada no Inep, que já aparece na correção de cada questão do Enem 2024 e 2025.
5. Publicação: o ramo `frente/diagnostico` não foi levado ao `main` nem ao ar. O cartão "Divulgar o diagnóstico de erros do PU" depende disso.

## Testes

- `python3 tests/acompanhamento.py`: classe `Diagnostico` (aluno sem respostas, ordem pesada pelo número de respostas, mínimo exato e empate, primeira tentativa e chute, assunto em revisão, prova desligada e questão removida, isolamento e média dos outros).
- `node tests/fluida-navegador.mjs`: estado vazio em 390 e 1440 com o menu em Progresso; conta com respostas de teste na ordem certa, sem porcentagem abaixo de 5, botão do primeiro assunto na primeira tela do celular, entrada pelo Progresso e treino no assunto; a tela entra nas varreduras de rolagem lateral (320, 390, 768), cor e faixa, contraste AA nos temas diurno e noturno, com dados montados na página (nomes longos, média, chute e revisão) e vazia.

## Atualizações

- 17/11/2026 21:20 · Dominique-Oliveira-Claude🤖🧡 · Documento criado com fontes, fórmula, mínimos, privacidade e pendências. **Por quê:** afazer "Diagnóstico de erros no PU" pedido por Dominique Oliveira🐧❤️.
