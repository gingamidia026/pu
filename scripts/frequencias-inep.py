#!/usr/bin/env python3
# Frequência de marcação por item do Enem (microdados Inep).
# Uso: python3 -I scripts/frequencias-inep.py <ano>   (pasta: PU_MICRODADOS_INEP, padrão ~/craft/Enem-frentes/dados/inep)
# Cópia de Enem-frentes/dados/inep/frequencias.py (executor Haiku, 17/11/2026), só com a pasta configurável.
# Entrada: <pasta>/<ano>/ITENS_PROVA_<ano>.csv e RESULTADOS_<ano>.csv extraídos do zip oficial. Saída: <pasta>/frequencias_<ano>.csv.
# Regra da prova de Linguagens (LC): a cadeia TX_RESPOSTAS_LC tem 45 posições; a posição k
# corresponde a CO_POSICAO k. Nas posições 1 a 5 há um item de inglês (TP_LINGUA=0) e um de
# espanhol (TP_LINGUA=1) por posição; a letra vale para o item da língua escolhida pelo
# participante (TP_LINGUA do RESULTADOS). Por isso a contagem de LC nas posições 1 a 5 só
# considera quem tem TP_LINGUA igual à língua do item.
import csv, sys, os, glob, collections, json

csv.field_size_limit(10**7)
BASE = os.environ.get('PU_MICRODADOS_INEP', os.path.expanduser('~/craft/Enem-frentes/dados/inep'))
ANO = sys.argv[1]
DIR = os.path.join(BASE, ANO)
AREAS = ['CN', 'CH', 'LC', 'MT']
TAM_CADEIA = {'CN': 45, 'CH': 45, 'LC': 45, 'MT': 45}  # confirmado no dicionário e nos dados
LETRAS = 'ABCDE'
NC = 9  # índices: 0 = presentes; 1..5 = A..E; 6 = branco; 7 = dupla; 8 = outro

def novo():
    return [0] * NC

def cat_idx(ch):
    if ch == '':
        return 8
    if ch in LETRAS:
        return 1 + LETRAS.index(ch)
    if ch == '.':
        return 6
    if ch == '*':
        return 7
    return 8

# ---------- itens ----------
# CO_POSICAO é numeração global da prova: LC 1-45, CH 46-90, CN 91-135, MT 136-180.
# A cadeia TX_RESPOSTAS_<área> tem 45 letras na ordem dessa numeração (índice = pos - base).
itens_path = os.path.join(DIR, f'ITENS_PROVA_{ANO}.csv')
itens = []  # linhas do ITENS já normalizadas
with open(itens_path, encoding='latin-1', newline='') as f:
    for r in csv.DictReader(f, delimiter=';'):
        itens.append({
            'area': r['SG_AREA'], 'co_prova': int(r['CO_PROVA']), 'cor': r['TX_COR'],
            'pos': int(r['CO_POSICAO']), 'co_item': r['CO_ITEM'], 'gab': r['TX_GABARITO'],
            'lingua': r['TP_LINGUA'], 'adaptado': r['IN_ITEM_ADAPTADO'],
            'aband': r['IN_ITEM_ABAN'],
        })
chaves_vistas = set()
base = {}
for it in itens:
    base[it['area']] = min(base.get(it['area'], 10**9), it['pos'])
for a in AREAS:
    assert base[a] == {'LC': 1, 'CH': 46, 'CN': 91, 'MT': 136}[a], ('base inesperada', a, base[a])
posicoes_caderno = collections.defaultdict(set)
for it in itens:
    posicoes_caderno[(it['area'], it['co_prova'])].add(it['pos'])
for (a, cp), ps in posicoes_caderno.items():
    assert ps == set(range(base[a], base[a] + TAM_CADEIA[a])), ('posições fora do bloco', a, cp)
entradas = collections.defaultdict(list)  # (area, co_prova) -> [(chave, idx_cadeia, lingua_req)]
for it in itens:
    ck = (it['area'], it['co_prova'], it['pos'], it['lingua'])
    assert ck not in chaves_vistas, ('item duplicado', ck)
    chaves_vistas.add(ck)
    if it['area'] == 'LC' and it['pos'] > 5:
        assert it['lingua'] == '', ('LC pos>5 com língua', ck)
    if it['area'] == 'LC' and it['pos'] <= 5:
        assert it['lingua'] in ('0', '1'), ('LC pos<=5 sem língua', ck)
    entradas[(it['area'], it['co_prova'])].append(
        (ck, it['pos'] - base[it['area']], it['lingua'] if it['area'] == 'LC' and it['pos'] <= 5 else None))

# ---------- resultados ----------
cands = [p for p in glob.glob(os.path.join(DIR, '*.csv'))
         if os.path.basename(p).upper().startswith(('RESULTADOS_', 'MICRODADOS_ENEM_'))]
assert len(cands) == 1, cands
res_path = cands[0]
print('arquivo de resultados:', res_path, flush=True)

pres_count = collections.Counter()     # área -> presentes (qualquer caderno)
pres_valores = collections.Counter()   # (área, valor TP_PRESENCA) -> n
sem_itens = collections.Counter()      # (área, co_prova) presentes sem itens no ITENS
tam_cadeia = collections.Counter()     # (área, tamanho da cadeia) -> n (presentes)
counts = collections.defaultdict(novo)  # chave do item -> contadores
resp_anom = collections.Counter()
with open(res_path, encoding='latin-1', newline='') as f:
    rd = csv.reader(f, delimiter=';')
    h = next(rd)
    ix = {c: i for i, c in enumerate(h)}
    need = ['TP_LINGUA'] + [f'{p}_{a}' for a in AREAS for p in ('TP_PRESENCA', 'CO_PROVA', 'TX_RESPOSTAS')]
    for c in need:
        assert c in ix, ('coluna ausente', c)
    i_tl = ix['TP_LINGUA']
    i_pr = {a: ix[f'TP_PRESENCA_{a}'] for a in AREAS}
    i_cp = {a: ix[f'CO_PROVA_{a}'] for a in AREAS}
    i_rs = {a: ix[f'TX_RESPOSTAS_{a}'] for a in AREAS}
    n_lin = 0
    for row in rd:
        n_lin += 1
        tl = row[i_tl]
        for a in AREAS:
            pv = row[i_pr[a]]
            pres_valores[(a, pv)] += 1
            if pv != '1':
                continue
            pres_count[a] += 1
            cp = int(row[i_cp[a]]) if row[i_cp[a]].strip() else -1
            resp = row[i_rs[a]]
            tam_cadeia[(a, len(resp))] += 1
            if len(resp) != TAM_CADEIA[a]:
                resp_anom[(a, len(resp))] += 1
            ent = entradas.get((a, cp))
            if ent is None:
                sem_itens[(a, cp)] += 1
                continue
            for ck, idx, lreq in ent:
                if lreq is not None and tl != lreq:
                    continue
                c = counts[ck]
                c[0] += 1
                ch = resp[idx] if idx < len(resp) else ''
                c[cat_idx(ch)] += 1
    print('linhas lidas:', n_lin, flush=True)

# ---------- saídas ----------
def fmt_pct(n_gab, n_pres):
    return '' if n_pres == 0 else f'{100.0 * n_gab / n_pres:.2f}'.replace('.', ',')

cab = ['ano', 'co_prova', 'cor', 'area', 'posicao', 'co_item', 'lingua', 'gabarito', 'anulado',
       'n_presentes', 'n_A', 'n_B', 'n_C', 'n_D', 'n_E', 'n_branco', 'n_dupla', 'n_outro', 'pct_acerto']
out1 = os.path.join(BASE, f'frequencias_{ANO}.csv')
falhas = 0; passam = 0
agreg = collections.OrderedDict()
ncad = collections.defaultdict(set)
gabs_por_item = collections.defaultdict(set)
with open(out1, 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f, delimiter=';')
    w.writerow(cab)
    for it in itens:
        ck = (it['area'], it['co_prova'], it['pos'], it['lingua'])
        c = counts.get(ck, novo())
        soma = sum(c[1:])
        if soma == c[0]:
            passam += 1
        else:
            falhas += 1
        anulado = 'sim' if it['gab'] == 'X' else 'nao'
        n_gab = c[1 + LETRAS.index(it['gab'])] if (it['gab'] != '' and it['gab'] in LETRAS) else 0
        pct = '' if it['gab'] == 'X' else fmt_pct(n_gab, c[0])
        w.writerow([ANO, it['co_prova'], it['cor'], it['area'], it['pos'], it['co_item'],
                    it['lingua'], it['gab'], anulado, c[0], *c[1:], pct])
        # agregado por CO_ITEM (e língua)
        gkey = (it['area'], it['co_item'], it['lingua'])
        ag = agreg.setdefault(gkey, {'gab': it['gab'], 'anul': anulado, 'c': novo(), 'pct_n_gab': 0})
        for k in range(NC):
            ag['c'][k] += c[k]
        ag['pct_n_gab'] += n_gab
        ncad[gkey].add(it['co_prova'])
        gabs_por_item[gkey].add(it['gab'])
print('conferência 1 (soma dos marcados == presentes):', 'passam', passam, 'falham', falhas, flush=True)
out2 = os.path.join(BASE, f'frequencias_por_item_{ANO}.csv')
cab2 = ['ano', 'area', 'co_item', 'lingua', 'gabarito', 'anulado', 'n_presentes', 'n_A', 'n_B', 'n_C',
        'n_D', 'n_E', 'n_branco', 'n_dupla', 'n_outro', 'pct_acerto', 'n_cadernos']
with open(out2, 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f, delimiter=';')
    w.writerow(cab2)
    for gkey, ag in agreg.items():
        area, co_item, lingua = gkey
        gabs = gabs_por_item[gkey]
        if len(gabs) > 1:
            print('ATENÇÃO gabarito divergente entre cadernos:', gkey, gabs, flush=True)
        gab = ag['gab']
        anulado = ag['anul']
        c = ag['c']
        pct = '' if anulado == 'sim' else fmt_pct(ag['pct_n_gab'], c[0])
        w.writerow([ANO, area, co_item, lingua, gab, anulado, c[0], *c[1:], pct, len(ncad[gkey])])

# Conferência 2 da linha por item: mesma soma
falhas2 = sum(1 for g, ag in agreg.items() if sum(ag['c'][1:]) != ag['c'][0])
print('conferência 1b (agregado por item):', 'falham', falhas2, flush=True)

resumo = {
    'ano': ANO, 'arquivo_resultados': os.path.basename(res_path),
    'linhas_lidas': n_lin,
    'presentes_por_area': dict(pres_count),
    'valores_TP_PRESENCA': {f'{a}={v!r}': n for (a, v), n in sorted(pres_valores.items())},
    'tamanho_cadeia_por_area': {f'{a}:{t}': n for (a, t), n in sorted(tam_cadeia.items())},
    'cadeias_fora_do_tamanho_esperado': {f'{a}:{t}': n for (a, t), n in resp_anom.items()},
    'presentes_sem_itens_no_caderno': {f'{a}:{cp}': n for (a, cp), n in sorted(sem_itens.items())},
    'linhas_frequencia_ok': passam, 'linhas_frequencia_falha': falhas,
    'itens_por_area': dict(collections.Counter(a for (a, _, _, _) in chaves_vistas)),
    'cadernos_por_area': {a: len({cp for (aa, cp) in entradas if aa == a}) for a in AREAS},
    'itens_distintos_co_item_por_area': {a: len({g[1] for g in agreg if g[0] == a}) for a in AREAS},
}
with open(os.path.join(DIR, f'resumo_{ANO}.json'), 'w', encoding='utf-8') as f:
    json.dump(resumo, f, ensure_ascii=False, indent=2)
print(json.dumps(resumo, ensure_ascii=False, indent=2), flush=True)
