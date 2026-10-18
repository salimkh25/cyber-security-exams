#!/usr/bin/env python3
"""
topics.py — חלוקת שאלות המאגר לנושאים (clustering) + ניתוח חזרות.

שיטה: TF-IDF על מילות התוכן של כל שאלה (שאלה + תשובות), ואז K-Means "מעוגן":
המרכזים ההתחלתיים נבנים ממילות מפתח של נושאי הקורס, והאלגוריתם מזיז אותם לפי הנתונים.
כך מתקבלים אשכולות עם שם משמעותי במקום "אשכול 7". דורש רק numpy.

מוסיף לכל שאלה ב-bank.json:
  topic          — שם הנושא
  topic_score    — דמיון לקוסינוס למרכז האשכול (כמה "טיפוסית" השאלה לנושא)
  exam_count     — בכמה מבחנים שונים (תאריכים שונים) השאלה הופיעה
  variant_group  — מזהה קבוצת "וריאציות": שאלות עם אותו גוף שאלה אך תשובות שונות
"""
import collections, json, math, re, sys
from difflib import SequenceMatcher
import numpy as np

TOPICS = {
    'הצפנה סימטרית וצפנים קלאסיים': 'des aes 3des ecb cbc block צופן צפנים קיסר vigenère ויז׳נר החלפה מונואלפבתי one time pad otp xor סימטרי סימטרית mode operation plaintext ciphertext',
    'RSA, מפתח ציבורי וחתימות': 'rsa textbook חתימה דיגיטלית חתימות signature פומבי פרטי public private key gen ϕ phi אסימטרית א-סימטרית הכחשה להתכחש',
    'דיפי-הלמן והחלפת מפתחות': 'דיפי הלמן diffie hellman לוגריתם הדיסקרטי המשותף החלפת מפתחות g n מודולו',
    'Hash, MAC וסיסמאות': 'hash salt pepper mac tag סיסמא סיסמאות password username preimage collision resistance digest encrypt then and integrity authenticity hmac message authentication codes',
    'PKI, תעודות, CT ו-OCSP': 'ca תעודה תעודות certificate transparency ct ocsp stapling crl sct לוגרים מוניטורים root store chain trust revocation',
    'TLS / HTTPS': 'tls ssl https handshake clienthello serverhello finish pre master secret session cipher suite hsts preload strict transport security clientkeyexchange',
    'אבטחת Web': 'xss csrf token sql injection same origin policy csp cookie cookies samesite httponly iframe דפדפן חיטוי קידוד encoding sanitization x-frame-options dom reflected stored sql injection inputusername inputpassword שאילתא שאילתת blind get בקשת cross site scripting',
    'רשתות: ARP, DNS, DoS ו-Firewall': 'arp dns poisoning הרעלת קמינסקי syn flood dos ddos botnet firewall חומת ids ips ip mac switch spoofing ping nmap port פורט tcp mitm off-path eavesdropping',
    'ביטקוין ובלוקצ׳יין': 'ביטקוין בלוקצ׳יין בלוקצ\'יין בלוק miner כרייה כורים proof work fork double spending escrow merkle מרקל עסקה טרנזקציה טרנזקציות script p2pkh nonce ארנק hash160 checksig equalverify input output micro payments mining pools',
}
STOP = set('של את על אם או גם כי לא הוא היא הם זה זו אשר כאשר כך יש אין עם בין מה איזו איזה מבין הבאות הבאים '
           'הטענות הטענה נכונה אינה נכון לגבי בהקשר כדי רק כל אליס בוב לבוב לאליס ובוב התוקף תוקף the a of to and '
           'is in that it for be with by on as an are this'.split())


def tokens(text):
    t = re.sub(r'<[^>]+>', ' ', text).lower().replace("'", '׳')
    return [w for w in re.findall(r'[a-zϕ][a-z0-9ϕ\-]*|[א-ת׳"\-]{2,}', t) if w not in STOP]


def tfidf(docs):
    df = collections.Counter(w for d in docs for w in set(d))
    vocab = sorted(w for w, c in df.items() if c >= 2)
    idx = {w: i for i, w in enumerate(vocab)}
    X = np.zeros((len(docs), len(vocab)))
    for i, d in enumerate(docs):
        for w, c in collections.Counter(d).items():
            if w in idx:
                X[i, idx[w]] = (1 + math.log(c)) * math.log(len(docs) / df[w])
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9
    return X, vocab, idx, df


def seeded_kmeans(X, seeds, iters=50, seed_weight=0.35):
    C = seeds.copy()
    for _ in range(iters):
        lab = (X @ C.T).argmax(1)
        newC = []
        for j in range(len(C)):
            m = X[lab == j].mean(0) if (lab == j).any() else np.zeros(X.shape[1])
            c = (1 - seed_weight) * m + seed_weight * seeds[j]   # העוגן שומר את הנושא בכיוון שלו
            newC.append(c / (np.linalg.norm(c) + 1e-9))
        newC = np.array(newC)
        if np.allclose(newC, C):
            break
        C = newC
    sims = X @ C.T
    return sims.argmax(1), sims.max(1), C


def assign_topics(questions):
    docs = [tokens(q['stem']) * 2 + tokens(' '.join(q['options'])) for q in questions]  # לגוף השאלה משקל כפול
    names = list(TOPICS)
    X, vocab, idx, df = tfidf(docs + [tokens(v) for v in TOPICS.values()])
    X, S = X[:len(docs)], X[len(docs):]
    lab, score, C = seeded_kmeans(X, S)
    top_terms = {names[j]: [vocab[i] for i in np.argsort(-C[j])[:8]] for j in range(len(names))}
    for q, l, s in zip(questions, lab, score):
        if q.get('topic_manual'):
            continue
        q['topic'] = names[l]
        q['topic_score'] = round(float(s), 3)
    return top_terms


def repetition(questions):
    for q in questions:
        q['exam_count'] = len({s['date'] for s in q['sources'] if s.get('date')})   # מבחנים אמיתיים (תאריכים שונים)
        q['in_sample_exam'] = any(not s.get('date') for s in q['sources'])     # הופיעה במבחן לדוגמא
    # וריאציות: אותו גוף שאלה (דמיון גבוה) עם תשובות שונות
    norm = [re.sub(r'\W+', '', q['stem']) for q in questions]
    opts = [re.sub(r'\W+', '', '|'.join(sorted(q['options']))) for q in questions]
    parent = list(range(len(questions)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i in range(len(questions)):
        for j in range(i + 1, len(questions)):
            a, b = norm[i], norm[j]
            sm = SequenceMatcher(None, a, b, autojunk=False)
            if not (sm.quick_ratio() > 0.85 and sm.ratio() > 0.85):
                continue
            if min(len(a), len(b)) < 45:
                # גוף גנרי ("איזו טענה אינה נכונה?") – וריאציה רק אם גם התשובות דומות חלקית
                so = SequenceMatcher(None, opts[i], opts[j], autojunk=False)
                if so.ratio() < 0.6:
                    continue
            parent[find(i)] = find(j)
    groups = collections.defaultdict(list)
    for i in range(len(questions)):
        groups[find(i)].append(i)
    gid = 0
    for g in groups.values():
        if len(g) > 1:
            gid += 1
            for i in g:
                questions[i]['variant_group'] = f'V{gid:02d}'
        else:
            questions[g[0]]['variant_group'] = None


def repeated_statements(questions, min_exams=2):
    """טענות (תשובות) שחוזרות במבחנים שונים – גם כשהשאלה עצמה שונה."""
    items = []
    for q in questions:
        dates = {s['date'] for s in q['sources'] if s.get('date')}
        for i, o in enumerate(q['options']):
            n = re.sub(r'\W+', '', re.sub(r'<[^>]+>', '', o)).lower()
            if len(n) >= 25:
                items.append((n, o, q['id'], dates))
    groups = []
    for n, o, qid, dates in items:
        for g in groups:
            if abs(len(g['n']) - len(n)) < 0.15 * len(n):
                sm = SequenceMatcher(None, g['n'], n, autojunk=False)
                if sm.quick_ratio() > 0.9 and sm.ratio() > 0.9:
                    g['dates'] |= dates; g['ids'].add(qid); break
        else:
            groups.append({'n': n, 'text': o, 'dates': set(dates), 'ids': {qid}})
    rep = [g for g in groups if len(g['dates']) >= min_exams and len(g['ids']) >= 2]   # אותה טענה בשאלות שונות
    rep.sort(key=lambda g: (-len(g['dates']), g['text']))
    return [{'text': g['text'], 'exams': len(g['dates']), 'dates': sorted(g['dates'], key=lambda d: d[6:] + d[3:5] + d[:2]),
             'questions': sorted(g['ids'])} for g in rep]


def main(path):
    data = json.load(open(path, encoding='utf-8'))
    qs = data['questions']
    top = assign_topics(qs)
    repetition(qs)
    data['meta']['repeated_statements'] = repeated_statements(qs)
    data['meta']['topics'] = {t: {'count': sum(q['topic'] == t for q in qs), 'top_terms': top[t]} for t in TOPICS}
    json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('נושאים:')
    for t in TOPICS:
        print(f"  {data['meta']['topics'][t]['count']:3d}  {t}")
    print(f"שאלות שהופיעו ביותר ממבחן אמיתי אחד: {sum(q['exam_count'] > 1 for q in qs)}  |  "
          f"קבוצות וריאציות: {len({q['variant_group'] for q in qs if q['variant_group']})}  |  "
          f"טענות שחוזרות: {len(data['meta']['repeated_statements'])}")


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'bank.json')
