#!/usr/bin/env python3
"""
build_app.py — בונה את app.html: אפליקציה עצמאית (קובץ אחד) ליצירת מבחנים, מבחן דיגיטלי עם ציון,
תרגול, גרסאות להדפסה וסטטיסטיקה. המאגר (bank.json) מוטמע בתוך הקובץ, כך שפשוט פותחים אותו בדפדפן.

רץ אוטומטית בסוף build_bank.py. אפשר גם ידנית:
    python3 build_app.py [bank.json] [-o app.html]
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def build(bank_path, out_path, print_enabled=True, standalone=True):
    tpl = open(os.path.join(HERE, 'app_template.html'), encoding='utf-8').read()
    data = json.load(open(bank_path, encoding='utf-8'))
    js = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    page = tpl.replace('/*__BANK__*/null', js).replace('/*__PRINT__*/false', 'true' if print_enabled else 'false')
    if standalone:
        page = ('<!doctype html>\n<html lang="he" dir="rtl"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
                + page.replace('<header class="top">', '</head><body>\n<header class="top">', 1) + '\n</body></html>')
    open(out_path, 'w', encoding='utf-8').write(page)
    return out_path


def main(bank_path=None, out=None):
    bank_path = bank_path or os.path.join(HERE, 'bank.json')
    out = out or os.path.join(os.path.dirname(os.path.abspath(bank_path)), 'app.html')
    build(bank_path, out)
    root_index = os.path.join(os.path.dirname(HERE), 'index.html')
    build(bank_path, root_index)
    if os.environ.get('ARTIFACT_OUT'):   # גרסה לפרסום כ-Artifact (בלי כפתור הדפסה)
        build(bank_path, os.environ['ARTIFACT_OUT'], print_enabled=False, standalone=False)
    print(f'האפליקציה עודכנה: {out} וגם {root_index}')


if __name__ == '__main__':
    args = sys.argv[1:]
    o = None
    if '-o' in args:
        i = args.index('-o'); o = args[i + 1]; del args[i:i + 2]
    main(args[0] if args else None, o)
