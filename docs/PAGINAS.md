# Páginas públicas do PU (endereços próprios)

Autora: Dominique-Oliveira-Claude🤖🧡, 17/11/2026. Afazer "Endereços próprios no PU" do plano de páginas úteis do cofre (`5 Bases/Plano de páginas úteis do PU.md`).

## Como funciona

O GitHub Pages serve a raiz do repositório em https://pu.gingamidia.com. O gerador `paginas/gerar.py` (só Python padrão, sem etapa de construção) lê `paginas/conteudo/*.json`, um arquivo por página, aplica o molde `paginas/molde.html` com a folha `paginas/estilo.css` e grava na raiz:

- uma pasta com `index.html` para cada página de leitura (hoje `/provas-anteriores/`);
- `/criar-conta/`: a entrada inteira, copiada do `index.html` da raiz com caminhos absolutos, título próprio e `data-abrir="criar-conta"`, que o `app.js` lê para abrir já no cadastro (o canônico continua na raiz);
- `404.html` (o Pages a usa em todo endereço que não existe), `robots.txt` e `sitemap.xml`;
- o bloco de dados estruturados (Organization, WebSite, BreadcrumbList) entre `<!-- dados-estruturados:inicio -->` e `<!-- dados-estruturados:fim -->` nos dois `index.html`.

As saídas entram no git, porque o Pages publica o que está no ramo. O Caddy e os compose não servem estas páginas: fazem proxy para `app/servidor.py`, que só serve `app/public`.

## Acrescentar uma página

1. Crie `paginas/conteudo/<nome>.json` com `"tipo": "leitura"`, `endereco` (`/nome-da-pasta/`), `titulo`, `descricao`, `migalha`, `h1`, `apoio`, `atualizada_em` (AAAA-MM-DD), `tom` (`mar`, `boia`, `sol`, `ipe` ou `goiaba`), `menu`, `sumario` e `blocos`. Use `provas-anteriores.json` de exemplo.
2. Blocos: `texto` (`titulo`, `paragrafos`, links como `[rótulo](https://...)`), `dados` (`id`, `titulo`, `colunas`, `coluna_fonte`, `texto_fonte`, `nota`, `linhas`) e `links` (lista das páginas). Cada linha de `dados` leva `valores`, `fonte` (endereço https oficial) e `conferido_em`.
3. Rode `python3 paginas/gerar.py` e `python3 tests/paginas.py`. A chamada do fim (`chamada`) sempre leva a `/criar-conta/`.

Regra **dado-inventado**: linha sem fonte https ou sem data de conferência (ou com data no futuro) faz o gerador recusar e não gravar nada. `--marcar-a-confirmar` grava mesmo assim, com "Dado a confirmar" visível na linha, só para rascunho.

Depois de mexer no `index.html` da raiz (texto da entrada, `?v=`), rode o gerador de novo: a porta `/criar-conta/` é cópia dele. `python3 paginas/gerar.py --conferir` e o `tests/paginas.py` acusam quando a cópia ficou para trás.

## Limites

As páginas de leitura não têm JavaScript, não chamam o intermediário e não carregam nada de fora (política de conteúdo `default-src 'self'`, `script-src 'none'`, `connect-src 'none'`). Fontes e imagem de compartilhamento vêm do próprio site; a imagem de 1200 × 630 é a da entrada até existir uma por tipo de página (campo `imagem` do conteúdo).
