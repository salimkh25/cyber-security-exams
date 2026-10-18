#!/usr/bin/env python3
"""
build_bank.py — בונה מאגר שאלות אמריקאיות (bank.json) מקובצי PDF של מבחנים.

הנחה: בכל שאלה, התשובה הראשונה (א / 1) היא הנכונה.
במאגר התשובה הנכונה נשמרת תמיד ראשונה ברשימת options (אינדקס 0).

שימוש:
    python3 build_bank.py <תיקיית מבחנים> [-o bank.json]

התיקייה נסרקת רקורסיבית לכל קבצי ה-PDF. שאלות כפולות (אותה שאלה במבחנים/עותקים שונים)
מאוחדות לרשומה אחת, עם רשימת כל המקורות.
תיקונים ידניים (קוד, טבלאות וכו') נשמרים בקובץ fixes.json שליד הסקריפט ומוחלים בכל הרצה,
כך שאפשר להוסיף מבחנים חדשים לתיקייה ולהריץ שוב בלי לאבד תיקונים.
"""
import argparse, json, os, re, sys
from difflib import SequenceMatcher

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract  # noqa: E402
from extract import pdf_lines  # noqa: E402

HEB_LETTERS = 'אבגדה'
FOOTER = [r'^עמוד\s*\d+\s*מתוך\s*\d+$', r"^מבחן מס'", r'^קוד מבחן', r'^\d+\s*מתוך\s*\d+$']
Q_HDR = re.compile(r'^שאלה\s*מספר\s*(\d+)\s*:?\s*(.*)$')
Q_NUM = re.compile(r'^(\d{1,2})\s*\.\s+(.*)$')
OPT_HEB = re.compile(r'^([אבגדה])\s*[.)]\s*(.*)$')
OPT_NUM = re.compile(r'^([1-5])\s*\.\s*(.*)$')
OPT_NUM_REV = re.compile(r'^(.*\S)\s*\.([1-5])$')       # "MAC and Encrypt .1" (שורה כולה באנגלית)
OPT_NUM_REV2 = re.compile(r'^([^\u0590-\u05FF]*\S)\s*\.([1-5])\s+(.*)$')  # "28 .2 בחזקת 7"
OPT_HEB_REV = re.compile(r'^(.*\S)\s*\.([אבגדה])$')
DATE_RE = re.compile(r'(?<!\d)(\d{2})(\d{2})(20\d{2})(?!\d)')


def clean_lines(lines):
    out = []
    for l in lines:
        l = re.sub(r'[ \t ]+', ' ', l).strip()
        if not l or any(re.search(p, l) for p in FOOTER):
            continue
        out.append(l)
    return out


def mc_section(lines):
    """מחזיר רק את חלק השאלות האמריקאיות (מדלג על חלק פתוח אם קיים)."""
    start = 0
    for i, l in enumerate(lines):
        if re.search(r"חלק\s*ב'?\s*:?\s*שאלות\s*ברירה", l.replace(' ', ' ')) or \
           re.search(r"חלקב'?:?שאלותברירה", l.replace(' ', '')):
            start = i + 1
    return lines[start:]


def option_label(line, mode):
    if mode == 'heb':
        m = OPT_HEB.match(line)
        if m: return HEB_LETTERS.index(m.group(1)), m.group(2)
        m = OPT_HEB_REV.match(line)
        if m and not re.search('[֐-׿]', m.group(1)): return HEB_LETTERS.index(m.group(2)), m.group(1)
    else:
        m = OPT_NUM.match(line)
        if m: return int(m.group(1)) - 1, m.group(2)
        m = OPT_NUM_REV.match(line)
        if m and not re.search('[֐-׿]', m.group(1)): return int(m.group(2)) - 1, m.group(1)
        m = OPT_NUM_REV2.match(line)
        if m: return int(m.group(2)) - 1, m.group(1) + ' ' + m.group(3)
    return None


def join(lines):
    """מחבר שורות שנשברו בגלל רוחב העמוד, אך שומר שבירות משמעותיות (רשימות, טבלאות)."""
    out = ''
    for l in lines:
        if not out:
            out = l
        elif re.match(r'^(•|-|\d+\.|[א-ה]\.|\*)\s', l) or out.endswith((':', '?')) or is_table_row(l):
            out += '\n' + l
        else:
            out += ' ' + l
    return out.strip()


def is_table_row(l):
    toks = l.split(' ')
    return l.count('*') >= 2 or (len(toks) >= 5 and sum(len(t) <= 4 for t in toks) >= 0.7 * len(toks))


def split_options(block, mode):
    """block = שורות השאלה. מוצא את רצף האפשרויות א..ד האחרון."""
    starts = [i for i, l in enumerate(block) if (lab := option_label(l, mode)) and lab[0] == 0]
    for s in reversed(starts):
        opts, cur, expect = [], None, 0
        for l in block[s:]:
            lab = option_label(l, mode)
            if lab and lab[0] == expect:
                if cur is not None: opts.append(cur)
                cur = [lab[1]]; expect += 1
            else:
                cur.append(l)
        opts.append(cur)
        if len(opts) >= 2:
            return block[:s], [join(o) for o in opts]
    return block, []


def parse_coded(lines):
    """פורמט 'מקודד': טקסט שאלה, [qN], ואז כל תשובה מסתיימת ב-[a]."""
    qs, buf, cur = [], [], None
    for l in lines:
        m = re.match(r'^\[q(\d+)\]$', l)
        if m:
            if cur: qs.append(cur)
            cur = {'num': int(m.group(1)), 'stem': join(buf), 'options': [], 'note': ''}; buf = []
        elif l == '[a]' and cur is not None:
            cur['options'].append(join(buf)); buf = []
        elif l == '[Info]':
            buf = []
        else:
            buf.append(l)
            if cur is not None and len(cur['options']) >= 4:
                qs.append(cur); cur = None
    if cur: qs.append(cur)
    return [q for q in qs if q['options']]


def tidy(t):
    """תיקונים כלליים לשאריות של היפוך כיווניות."""
    t = re.sub(r'\s*-{2,}\s*סוף\s*המבחן\s*-{2,}\s*$', '', t)
    t = re.sub(r'(^|\s)!(\d+)(?=[\s.,]|$)', r'\1\2!', t)          # !25 -> 25!
    t = re.sub(r'(^|\s)%(\d+)(?=[\s.,]|$)', r'\1\2%', t)          # %51 -> 51%
    t = re.sub(r'//:(https?)', r'\1://', t)                        # //:http -> http://
    t = re.sub(r'([\u05d0-\u05ea])\.([\u05d0-\u05ea])(?=\s|$)', r'\1\2.', t)   # עוב.ד -> עובד.
    t = re.sub(r'([\u05d0-\u05ea]) ,([\u05d0-\u05ea])(?=\s|$)', r'\1\2,', t)    # אינטרנ ,ט -> אינטרנט,
    return t.strip()


def parse_exam(path):
    all_lines = clean_lines(pdf_lines(path))
    hdr = next((m.group(1) for l in all_lines[:40] if (m := re.search(r'תאריך\s*הבחינה\s*:?\s*(\d{2}/\d{2}/\d{4})', l))), None)
    lines = mc_section(all_lines)
    penalty = 0 if extract.LAST_MIRROR else 50   # PDF עם גליפים הפוכים - פחות אמין
    qs = parse_coded(lines) if any(re.match(r'^\[q\d+\]$', l) for l in lines) else parse_blocks(lines)
    for q in qs:
        q['stem'] = tidy(q['stem']); q['options'] = [tidy(o) for o in q['options']]
        q['_penalty'] = penalty
        q['_hdr_date'] = hdr
    return qs


def parse_blocks(lines):
    has_hdr = any(Q_HDR.match(l) for l in lines)
    mode = 'heb'
    if has_hdr:
        # אם האפשרויות ממוספרות 1-4 במקום א-ד
        heb = sum(bool(OPT_HEB.match(l)) for l in lines)
        num = sum(bool(OPT_NUM.match(l) or OPT_NUM_REV.match(l)) for l in lines)
        mode = 'num' if num > heb else 'heb'
    blocks, cur, note = [], None, ''
    for l in lines:
        m = Q_HDR.match(l) if has_hdr else Q_NUM.match(l)
        if m:
            if cur: blocks.append(cur)
            rest = m.group(2).strip()
            cur = {'num': int(m.group(1)), 'note': rest if has_hdr else '', 'lines': [] if has_hdr else [rest]}
        elif cur is not None:
            cur['lines'].append(l)
    if cur: blocks.append(cur)
    qs = []
    for b in blocks:
        stem, opts = split_options(b['lines'], mode)
        stem = [l for l in stem if not re.search(r'(בכל|בטופס).*(תשובה|סעיף|התשובה).*(נכונ)', l.replace(' ', ' '))]
        note = b['note'].strip('() ')
        if not opts: continue
        qs.append({'num': b['num'], 'stem': join(stem), 'options': opts, 'note': note})
    return qs


def norm(s):
    return re.sub(r'[\W_]+', '', s).lower()


def noise(q):
    t = q['stem'] + ' '.join(q['options'])
    return len(re.findall(r'(?<!\S)[א-ת](?!\S)', t)) + t.count('  ')


def flags_for(q):
    f = []
    t = q['stem'] + '\n' + '\n'.join(q['options'])
    if len(q['options']) != 4: f.append(f"{len(q['options'])} options")
    if any(is_table_row(l) for l in q['stem'].split('\n')): f.append('table?')
    if re.search(r'(תשוב|סעיפ)\w*\s+[א-ד](\s|$|,|-)|כל (התשובות|הסעיפים|הטענות) (הנ"ל|נכונ)|אף (אחת|תשובה)', ' '.join(q['options'])):
        f.append('options reference each other')
    if q.get('note'): f.append('note')
    if not q['stem'] or any(not o for o in q['options']): f.append('empty text')
    return f


def exam_meta(path):
    m = DATE_RE.search(os.path.basename(path))
    return (f"{m.group(1)}/{m.group(2)}/{m.group(3)}" if m else None)


def date_key(src):
    d = src.get('date')
    return (d[6:] + d[3:5] + d[:2]) if d else '99999999'


def load_fixes(path):
    if not os.path.exists(path):
        return {}, []
    data = json.load(open(path, encoding='utf-8'))
    return data.get('fixes', {}), data.get('add', [])


def apply_fix(q, fx):
    if 'stem' in fx: q['stem'] = fx['stem']
    if 'options' in fx:
        q['options'] = [n if n is not None else (q['options'][i] if i < len(q['options']) else '')
                        for i, n in enumerate(fx['options'])]
    for k in ('note', 'exclude', 'fixed_order'):
        if k in fx: q[k] = fx[k]
    if 'topic' in fx:
        q['topic'], q['topic_manual'] = fx['topic'], True


def main():
    ap = argparse.ArgumentParser(description='בונה bank.json ממבחני PDF (תשובה א = נכונה)')
    ap.add_argument('folder', help='תיקייה עם קבצי ה-PDF (נסרקת רקורסיבית)')
    ap.add_argument('-o', '--out', default='bank.json')
    ap.add_argument('--fixes', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixes.json'),
                    help='קובץ תיקונים ידניים (ברירת מחדל: fixes.json ליד הסקריפט)')
    a = ap.parse_args()
    fixes, additions = load_fixes(a.fixes)

    pdfs = sorted(os.path.join(r, f) for r, _, fs in os.walk(a.folder) for f in fs if f.lower().endswith('.pdf'))
    bank = []
    for p in pdfs:
        rel = os.path.relpath(p, a.folder)
        try:
            qs = parse_exam(p)
        except Exception as e:
            print(f'!! {rel}: {e}'); continue
        print(f'{len(qs):3d} שאלות  ← {rel}')
        for q in qs:
            q['source'] = {'file': rel, 'date': exam_meta(p) or q.pop('_hdr_date', None), 'num': q.pop('num')}
            q.pop('_hdr_date', None)
            key = norm(q['stem'] + '|'.join(q['options']))
            dup = None
            for b in bank:
                sm = SequenceMatcher(None, b['_key'], key, autojunk=False)
                if sm.quick_ratio() > 0.9 and sm.ratio() > 0.9:
                    dup = b; break
            if dup:
                dup['sources'].append(q['source'])
                if noise(q) < dup['_noise']:  # שומרים את הגרסה הנקייה יותר
                    dup.update(stem=q['stem'], options=q['options'], _key=key, _noise=noise(q))
                if q['note'] and not dup.get('note'): dup['note'] = q['note']
            else:
                bank.append({'stem': q['stem'], 'options': q['options'], 'note': q['note'],
                             'sources': [q['source']], '_key': key, '_noise': noise(q)})

    # תיקונים ידניים: מוחלים על רשומה אם אחד המקורות שלה מופיע ב-fixes.json
    nfix = 0
    for b in bank:
        for src in b['sources']:
            fx = fixes.get(f"{os.path.basename(src['file'])}#{src['num']}")
            if fx:
                apply_fix(b, fx); nfix += 1
                if fx.get('clear_flags') or 'stem' in fx: b['_clear_flags'] = True
                break
    for ad in additions:
        if not any(os.path.basename(s['file']) == os.path.basename(ad['source']['file']) and s['num'] == ad['source']['num']
                   for b in bank for s in b['sources']):
            bank.append({'stem': ad['stem'], 'options': ad['options'], 'note': ad.get('note', ''),
                         'sources': [ad['source']], '_clear_flags': True})
            nfix += 1

    out = []
    bank.sort(key=lambda b: (min(date_key(s) for s in b['sources']), b['sources'][0]['num']))
    for i, b in enumerate(bank, 1):
        for k in ('_key', '_noise'): b.pop(k, None)
        clear = b.pop('_clear_flags', False)
        b['sources'].sort(key=date_key)
        q = {'id': f'Q{i:03d}', 'year': (b['sources'][0].get('date') or '')[6:] or None, **b}
        q['flags'] = [] if clear else flags_for(q)
        q.setdefault('fixed_order', 'options reference each other' in q['flags'])
        q.setdefault('exclude', False)
        out.append(q)

    meta = {'description': 'מאגר שאלות אמריקאיות. options[0] היא תמיד התשובה הנכונה.',
            'fields': {'exclude': 'true = לא ייכנס למבחנים', 'fixed_order': 'true = לא לערבב את סדר התשובות',
                       'flags': 'אזהרות אוטומטיות לבדיקה ידנית', 'note': 'הערה מהמבחן המקורי (למשל "התקבל גם סעיף ב")',
                       'sources': 'כל המבחנים שבהם השאלה הופיעה'}}
    json.dump({'meta': meta, 'questions': out}, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    nflag = sum(bool(q['flags']) for q in out)
    import topics
    topics.main(a.out)
    try:
        import build_app
        build_app.main(a.out)
    except ImportError:
        pass
    print(f'\n{len(out)} שאלות ייחודיות נשמרו ל-{a.out}  |  {nfix} תיקונים ידניים הוחלו  |  {nflag} מסומנות לבדיקה')


if __name__ == '__main__':
    main()
