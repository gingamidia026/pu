# Paleta do PU (direção de 14/11/2026): contraste AA de cada par usado e separação de acerto e erro para daltonismo.
# Uso: python3 ferramentas/medir-paleta.py ferramentas/paleta-identidade.json (sai com erro se algum par ficar abaixo do mínimo).
# Dominique-Oliveira-Claude🤖🧡, 14/11/2026.
# Mede contraste WCAG e separação de acerto e erro com daltonismo simulado (Machado, Oliveira e Fernandes, 2009, severidade 1).
import json, sys, math
def lin(c):
    c = c/255; return c/12.92 if c <= 0.04045 else ((c+0.055)/1.055)**2.4
def rgb(h): h = h.lstrip('#'); return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
def lum(h): r, g, b = map(lin, rgb(h)); return 0.2126*r + 0.7152*g + 0.0722*b
def contraste(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True); return (la+0.05)/(lb+0.05)
M = {'protanopia': [[0.152286,1.052583,-0.204868],[0.114503,0.786281,0.099216],[-0.003882,-0.048116,1.051998]],
     'deuteranopia': [[0.367322,0.860646,-0.227968],[0.280085,0.672501,0.047413],[-0.011820,0.042940,0.968881]],
     'tritanopia': [[1.255528,-0.076749,-0.178779],[-0.078411,0.930809,0.147602],[0.004733,0.691367,0.303900]]}
def simular(h, tipo):
    r, g, b = map(lin, rgb(h)); m = M[tipo]
    v = [max(0, min(1, m[i][0]*r + m[i][1]*g + m[i][2]*b)) for i in range(3)]
    return v
def lab(v):
    r, g, b = v
    x = (0.4124*r + 0.3576*g + 0.1805*b)/0.95047; y = 0.2126*r + 0.7152*g + 0.0722*b; z = (0.0193*r + 0.1192*g + 0.9505*b)/1.08883
    f = lambda t: t**(1/3) if t > 0.008856 else 7.787*t + 16/116
    return (116*f(y)-16, 500*(f(x)-f(y)), 200*(f(y)-f(z)))
def de(a, b): return math.dist(lab(a), lab(b))
def de_normal(a, b): return de([lin(c) for c in rgb(a)], [lin(c) for c in rgb(b)])
P = json.load(open(sys.argv[1]))
falhas = 0
for modo in ('dia', 'noite'):
    print(f'\n## {modo}')
    for texto, fundo, minimo, uso in P[modo]['pares']:
        c = contraste(P[modo]['cores'][texto], P[modo]['cores'][fundo]); ok = c >= minimo
        falhas += not ok
        print(f'{"OK " if ok else "FALHA"} {texto} sobre {fundo}: {c:.2f}:1 (mínimo {minimo}) · {uso}')
    a, e = P[modo]['cores']['acerto'], P[modo]['cores']['erro']
    print(f'acerto x erro, visão comum: ΔE {de_normal(a, e):.1f}')
    for tipo in M:
        d = de(simular(a, tipo), simular(e, tipo)); print(f'acerto x erro, {tipo}: ΔE {d:.1f}')
    af, ef = P[modo]['cores']['acerto-fundo'], P[modo]['cores']['erro-fundo']
    for tipo in M:
        print(f'fundo acerto x fundo erro, {tipo}: ΔE {de(simular(af, tipo), simular(ef, tipo)):.1f}')
    # acerto e erro contra cada cor de decoração (não podem se confundir)
    for sem in ('acerto', 'erro'):
        menor = min((de_normal(P[modo]['cores'][sem], P[modo]['cores'][d]), d) for d in P[modo]['decoracao'])
        print(f'{sem}: decoração mais próxima {menor[1]} ΔE {menor[0]:.1f}')
print('\nfalhas:', falhas)
sys.exit(1 if falhas else 0)
