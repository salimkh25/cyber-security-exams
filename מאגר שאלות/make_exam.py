#!/usr/bin/env python3
"""
make_exam.py — מייצר גרסאות מבחן מעורבבות מתוך bank.json.

דוגמאות:
    python3 make_exam.py                          # מבחן אחד, 10 שאלות
    python3 make_exam.py -v 3 -n 12               # 3 גרסאות, 12 שאלות בכל אחת
    python3 make_exam.py -v 4 --same-questions    # אותן שאלות, סדר שאלות ותשובות שונה בכל גרסה
    python3 make_exam.py -v 3 --no-repeat         # אין שאלה שחוזרת בין הגרסאות
    python3 make_exam.py --years 2024 2025 2026   # רק שאלות שהופיעו במבחנים מהשנים האלה
    python3 make_exam.py --practice               # מצב תרגול אינטראקטיבי (לחיצה = בדיקה מיידית)
    python3 make_exam.py --seed 42                # אותו seed = אותן גרסאות בדיוק

הפלט נשמר בתיקייה (ברירת מחדל: exams/):
    exam_v1.html, exam_v2.html ...   — המבחנים (פותחים בדפדפן; Cmd+P לשמירה כ-PDF)
    answer_key.html                  — מפתח תשובות לכל הגרסאות
    answer_key.json                  — אותו מפתח בפורמט JSON
"""
import argparse, html, json, os, random, re, sys
from datetime import datetime

LETTERS = 'אבגדהו'
HEB = re.compile('[֐-׿]')


# ---------- rendering ----------
TAGS = {'<sub>': '\x01', '</sub>': '\x02', '<sup>': '\x03', '</sup>': '\x04'}


def _esc(s):
    s = html.escape(s, quote=False)
    for tag, ph in TAGS.items():
        s = s.replace(ph, tag)
    return s


def inline(text, rtl=True):
    """escape + allow <sub>/<sup> + `inline code`; inside RTL lines, isolate English runs so brackets render correctly."""
    if '`' in text:
        parts = text.split('`')
        return ''.join(inline(p, rtl) if i % 2 == 0 else f'<bdi dir="ltr"><code>{html.escape(p)}</code></bdi>'
                       for i, p in enumerate(parts))
    for tag, ph in TAGS.items():
        text = text.replace(tag, ph)
    if not rtl:
        return _esc(text)
    out, pos = [], 0
    for m in re.finditer(r'[A-Za-z0-9\x01\x03][^\u0590-\u05FF]*', text):
        run = m.group()
        while run and (run[-1] in ' .,:;?!(-–' or
                       (run[-1] in ')]' and run.count('(') + run.count('[') < run.count(')') + run.count(']'))):
            run = run[:-1]
        out.append(_esc(text[pos:m.start()]))
        out.append('<bdi dir="ltr">' + _esc(run) + '</bdi>')
        pos = m.start() + len(run)
    out.append(_esc(text[pos:]))
    return ''.join(out)


def line_dir(s):
    return 'rtl' if HEB.search(s) else 'ltr'


def render_rich(text):
    """טקסט מהמאגר → HTML. תומך ב: שורות, ```קוד```, טבלאות (שורות שמתחילות ב-|), <sub>/<sup>."""
    out, lines, i = [], text.split('\n'), 0
    while i < len(lines):
        l = lines[i]
        if l.strip().startswith('```'):
            j = i + 1; code = []
            while j < len(lines) and not lines[j].strip().startswith('```'):
                code.append(lines[j]); j += 1
            out.append('<pre dir="ltr">' + html.escape('\n'.join(code)) + '</pre>')
            i = j + 1; continue
        if l.strip().startswith('|'):
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')]); i += 1
            t = '<div class="tbl"><table dir="rtl">'
            for r, row in enumerate(rows):
                tag = 'th' if r == 0 else 'td'
                t += '<tr>' + ''.join(f'<{tag} dir="{line_dir(c)}">{inline(c, line_dir(c) == "rtl")}</{tag}>' for c in row) + '</tr>'
            out.append(t + '</table></div>'); continue
        if l.strip():
            out.append(f'<div class="ln" dir="{line_dir(l)}">{inline(l, line_dir(l) == "rtl")}</div>')
        i += 1
    return '\n'.join(out)


CSS = """
:root{--ink:#1d1d1f;--muted:#6e6e73;--line:#d9d9de;--accent:#2f5bd3;--ok:#1f8a4c;--bad:#c0392b;--bg:#fff;--card:#fafafa}
@media (prefers-color-scheme:dark){:root:not(.print){--ink:#ececf0;--muted:#a1a1aa;--line:#3a3a40;--accent:#7aa2ff;--ok:#4cc38a;--bad:#ff6b5e;--bg:#141416;--card:#1c1c20}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 "Arial Hebrew","Rubik","Segoe UI",Arial,sans-serif}
.page{max-width:820px;margin:0 auto;padding:32px 20px 64px}
header{border-bottom:2px solid var(--ink);padding-bottom:14px;margin-bottom:22px}
h1{font-size:24px;margin:0 0 4px}
.meta{color:var(--muted);font-size:14px;display:flex;gap:18px;flex-wrap:wrap}
.fields{display:flex;gap:28px;margin-top:14px;font-size:14px;flex-wrap:wrap}
.fields span{border-bottom:1px solid var(--muted);min-width:150px;display:inline-block}
.q{break-inside:avoid;page-break-inside:avoid;margin:0 0 22px;padding:16px 18px;border:1px solid var(--line);border-radius:10px;background:var(--card)}
.qh{font-weight:700;margin-bottom:6px;display:flex;justify-content:space-between;gap:12px}
.qh small{font-weight:400;color:var(--muted);font-size:12px}
.stem .ln{margin:2px 0}
code{font:14px Menlo,Consolas,monospace;background:rgba(127,127,127,.12);padding:1px 4px;border-radius:4px}
pre{direction:ltr;text-align:left;background:rgba(127,127,127,.12);border-radius:6px;padding:10px 12px;font:13px/1.5 Menlo,Consolas,monospace;overflow-x:auto;white-space:pre}
.tbl{overflow-x:auto;margin:8px 0}
table{border-collapse:collapse;font-size:14px}
td,th{border:1px solid var(--line);padding:4px 8px;text-align:center}
th{background:rgba(127,127,127,.1)}
ol.opts{list-style:none;padding:0;margin:10px 0 0}
ol.opts li{display:flex;gap:10px;padding:6px 8px;border-radius:7px;align-items:flex-start}
ol.opts .l{font-weight:700;min-width:1.6em}
ol.opts .t{flex:1}
.ln[dir=ltr]{text-align:right}
.practice ol.opts li{cursor:pointer;border:1px solid transparent}
.practice ol.opts li:hover{border-color:var(--line)}
.practice li.ok{background:rgba(31,138,76,.15);border-color:var(--ok)!important}
.practice li.bad{background:rgba(192,57,43,.13);border-color:var(--bad)!important}
.practice .done li{cursor:default}
.src{color:var(--muted);font-size:12px;margin-top:8px;display:none}
.done + .src,.reveal .src{display:block}
.score{position:sticky;top:0;background:var(--bg);padding:10px 0;border-bottom:1px solid var(--line);margin-bottom:16px;font-weight:700;z-index:2;display:flex;justify-content:space-between;align-items:center;gap:10px}
.score button{font:inherit;font-size:14px;padding:6px 12px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
.end{text-align:center;color:var(--muted);margin-top:30px}
.key table{width:100%;margin-bottom:26px}
.key td.n{font-weight:700}
.key .note{color:var(--muted);font-size:12px}
@media (max-width:600px){.page{padding:20px 16px 48px}.q{padding:12px}}
@media print{pre{white-space:pre-wrap;word-break:break-all}:root{--bg:#fff;--card:#fff;--ink:#000}.page{max-width:none;padding:0}.q{border-color:#bbb}.score,.src{display:none!important}@page{margin:16mm 14mm}}
"""

PRACTICE_JS = """
<script>
(function(){
  var right=0, answered=0, total=document.querySelectorAll('.q').length;
  var s=document.getElementById('sc');
  function upd(){ s.textContent = 'ענית על '+answered+' מתוך '+total+' · נכונות: '+right; }
  document.querySelectorAll('ol.opts').forEach(function(ol){
    ol.addEventListener('click',function(e){
      var li=e.target.closest('li'); if(!li||ol.classList.contains('done'))return;
      ol.classList.add('done'); answered++;
      var c=ol.querySelector('li[data-c]');
      if(li===c){li.classList.add('ok');right++;} else {li.classList.add('bad');c.classList.add('ok');}
      upd();
    });
  });
  document.getElementById('rv').addEventListener('click',function(){
    document.querySelectorAll('ol.opts').forEach(function(ol){
      ol.classList.add('done'); ol.querySelector('li[data-c]').classList.add('ok');});
    document.body.classList.add('reveal');
  });
  upd();
})();
</script>
"""


def render_exam(title, version, qs, practice, n_versions):
    parts = [f'<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">'
             f'<meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<title>{html.escape(title)} – גרסה {version}</title><style>{CSS}</style></head>'
             f'<body class="{"practice" if practice else ""}"><div class="page">']
    parts.append(f'<header><h1>{html.escape(title)}</h1><div class="meta">'
                 f'<span>גרסה {version}{f" מתוך {n_versions}" if n_versions > 1 else ""}</span>'
                 f'<span>{len(qs)} שאלות</span><span>יש לבחור את התשובה הנכונה ביותר</span></div>')
    if not practice:
        parts.append('<div class="fields"><div>שם: <span></span></div><div>ת.ז: <span></span></div></div>')
    parts.append('</header>')
    if practice:
        parts.append('<div class="score"><span id="sc"></span><button id="rv">הצג את כל התשובות</button></div>')
    for i, item in enumerate(qs, 1):
        q = item['q']
        parts.append(f'<section class="q"><div class="qh"><span>שאלה {i}</span></div>'
                     f'<div class="stem">{render_rich(q["stem"])}</div><ol class="opts">')
        for j, oi in enumerate(item['order']):
            c = ' data-c="1"' if oi == 0 and practice else ''
            parts.append(f'<li{c}><span class="l">{LETTERS[j]}.</span>'
                         f'<span class="t">{render_rich(q["options"][oi])}</span></li>')
        parts.append('</ol>')
        if practice:
            parts.append(f'<div class="src">מקור: {html.escape(src_label(q))}'
                         f'{" · " + html.escape(q["note"]) if q.get("note") else ""}</div>')
        parts.append('</section>')
    parts.append('<div class="end">— סוף המבחן —</div></div>')
    if practice:
        parts.append(PRACTICE_JS)
    parts.append('</body></html>')
    return '\n'.join(parts)


def src_label(q):
    s = q['sources'][0]
    d = s.get('date') or os.path.basename(s['file'])
    more = f' (+{len(q["sources"]) - 1})' if len(q['sources']) > 1 else ''
    return f'{d}, שאלה {s["num"]}{more}'


def render_key(title, versions):
    rows = [f'<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>מפתח תשובות – {html.escape(title)}</title><style>{CSS}</style></head>'
            f'<body><div class="page key"><header><h1>מפתח תשובות</h1><div class="meta">'
            f'<span>{html.escape(title)}</span><span>{len(versions)} גרסאות</span></div></header>']
    for v, qs in enumerate(versions, 1):
        rows.append(f'<h2>גרסה {v}</h2><div class="tbl"><table><tr><th>שאלה</th><th>תשובה</th>'
                    f'<th>מזהה במאגר</th><th>מקור</th></tr>')
        for i, item in enumerate(qs, 1):
            q = item['q']
            note = f'<div class="note">{html.escape(q["note"])}</div>' if q.get('note') else ''
            rows.append(f'<tr><td class="n">{i}</td><td class="n">{LETTERS[item["order"].index(0)]}</td>'
                        f'<td>{q["id"]}</td><td>{html.escape(src_label(q))}{note}</td></tr>')
        rows.append('</table></div>')
    rows.append('</div></body></html>')
    return '\n'.join(rows)


# ---------- selection ----------
def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description='מייצר גרסאות מבחן מעורבבות מ-bank.json')
    ap.add_argument('-b', '--bank', default=os.path.join(here, 'bank.json'))
    ap.add_argument('-n', '--questions', type=int, default=10, help='מספר שאלות בכל גרסה (ברירת מחדל 10)')
    ap.add_argument('-v', '--versions', type=int, default=1, help='מספר גרסאות (ברירת מחדל 1)')
    ap.add_argument('--seed', type=int, help='seed לשחזור אותן גרסאות')
    ap.add_argument('--years', nargs='+', help='רק שאלות שהופיעו במבחנים מהשנים האלה')
    ap.add_argument('--same-questions', action='store_true', help='כל הגרסאות עם אותן שאלות (בסדר שונה)')
    ap.add_argument('--no-repeat', action='store_true', help='אין שאלה שחוזרת בין גרסאות')
    ap.add_argument('--no-shuffle-options', action='store_true', help='לא לערבב את סדר התשובות')
    ap.add_argument('--ids', nargs='+', help='רק שאלות עם המזהים האלה מהמאגר (למשל Q012 Q045)')
    ap.add_argument('--skip-noted', action='store_true', help='לדלג על שאלות עם הערה (למשל "התקבלו כל הסעיפים")')
    ap.add_argument('--practice', action='store_true', help='מצב תרגול אינטראקטיבי')
    ap.add_argument('--title', default='מבוא לאבטחת סייבר – מבחן תרגול')
    ap.add_argument('-o', '--out-dir', default=os.path.join(here, 'exams'))
    a = ap.parse_args()

    seed = a.seed if a.seed is not None else random.randrange(10**6)
    rng = random.Random(seed)
    bank = json.load(open(a.bank, encoding='utf-8'))['questions']
    pool = [q for q in bank if not q.get('exclude')]
    if a.years:
        pool = [q for q in pool if any((s.get('date') or '')[6:] in a.years for s in q['sources'])]
    if a.ids:
        pool = [q for q in pool if q['id'] in a.ids]
    if a.skip_noted:
        pool = [q for q in pool if not q.get('note')]
    if not pool:
        sys.exit('אין שאלות שמתאימות לסינון.')

    n = min(a.questions, len(pool))
    if a.no_repeat and n * a.versions > len(pool):
        sys.exit(f'--no-repeat: צריך {n * a.versions} שאלות אבל יש רק {len(pool)} במאגר המסונן.')

    versions, remaining = [], pool[:]
    base = rng.sample(pool, n)
    for v in range(a.versions):
        if a.same_questions:
            chosen = base[:]; rng.shuffle(chosen)
        elif a.no_repeat:
            chosen = rng.sample(remaining, n)
            remaining = [q for q in remaining if q not in chosen]
        else:
            chosen = rng.sample(pool, n)
        items = []
        for q in chosen:
            order = list(range(len(q['options'])))
            if not (a.no_shuffle_options or q.get('fixed_order')):
                rng.shuffle(order)
            items.append({'q': q, 'order': order})
        versions.append(items)

    os.makedirs(a.out_dir, exist_ok=True)
    for v, items in enumerate(versions, 1):
        name = f'{"practice" if a.practice else "exam"}_v{v}.html'
        open(os.path.join(a.out_dir, name), 'w', encoding='utf-8').write(
            render_exam(a.title, v, items, a.practice, a.versions))
    open(os.path.join(a.out_dir, 'answer_key.html'), 'w', encoding='utf-8').write(render_key(a.title, versions))
    json.dump({'seed': seed, 'created': datetime.now().isoformat(timespec='seconds'),
               'versions': [[{'n': i, 'id': it['q']['id'], 'answer': LETTERS[it['order'].index(0)]}
                             for i, it in enumerate(items, 1)] for items in versions]},
              open(os.path.join(a.out_dir, 'answer_key.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'נוצרו {a.versions} גרסאות × {n} שאלות (מתוך {len(pool)} במאגר) → {a.out_dir}   [seed={seed}]')


if __name__ == '__main__':
    main()
