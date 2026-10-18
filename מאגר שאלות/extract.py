import sys, re, pdfplumber, unicodedata
HEB = re.compile(r'[֐-׿]')
MIRROR = str.maketrans('()[]{}<>', ')(][}{><')
def is_strong_ltr(c): return bool(re.match(r'[A-Za-z0-9]', c))
def is_rtl(c): return bool(HEB.match(c))
def visual_to_logical(vis, mirror=True):
    # vis: chars in visual left->right order. Base direction RTL.
    # Build runs: LTR run = maximal span starting & ending with strong LTR char (neutrals inside allowed)
    n=len(vis); types=[]
    for c in vis:
        types.append('L' if (is_strong_ltr(c) or c in '\x01\x02\x03\x04') else 'R' if is_rtl(c) else 'N')
    # resolve neutrals: neutral between two L -> L, else R
    res=types[:]
    i=0
    while i<n:
        if types[i]=='N':
            j=i
            while j<n and types[j]=='N': j+=1
            left = types[i-1] if i>0 else 'R'
            right= types[j] if j<n else 'R'
            t = 'L' if (left=='L' and right=='L') else 'R'
            for k in range(i,j): res[k]=t
            i=j
        else: i+=1
    # bracket balancing: unmatched '(' in an L span absorbs following ')' neutrals and vice versa
    i=0
    while i<n:
        if res[i]=='L':
            j=i
            while j<n and res[j]=='L': j+=1
            span=vis[i:j]; extra=span.count('(')-span.count(')')
            k=j
            while extra>0 and k<n and vis[k] in ') ' and res[k]=='R':
                if vis[k]==')': extra-=1
                k+=1
            if k>j:
                while k>j and vis[k-1]==' ': k-=1
                for m in range(j,k): res[m]='L'
            k=i
            extra=span.count(')')-span.count('(')
            while extra>0 and k>0 and vis[k-1] in '( ' and res[k-1]=='R':
                if vis[k-1]=='(': extra-=1
                k-=1
            for m in range(k,i): res[m]='L'
            i=max(j,i+1)
        else: i+=1
    # split into runs, read right-to-left; L runs keep internal order
    runs=[]; i=0
    while i<n:
        j=i
        while j<n and res[j]==res[i]: j+=1
        runs.append((res[i], vis[i:j])); i=j
    out=[]
    for t,s in reversed(runs):
        if t=='L': out.append(s)
        else: out.append(s[::-1].translate(MIRROR) if mirror else s[::-1])
    return ''.join(out)

def page_lines(page, mirror=True):
    chars=[c for c in page.chars]
    if not chars: return []
    sizes=sorted(c['size'] for c in chars); body=sizes[len(sizes)//2]
    big=[c for c in chars if c['size']>=0.85*body]
    small=[c for c in chars if c['size']<0.85*body]
    lines=[]
    for c in sorted(big,key=lambda c:c['top']):
        if lines and abs(c['top']-lines[-1]['top'])<=3:
            L=lines[-1]; L['chars'].append(c); L['bottom']=max(L['bottom'],c['bottom'])
        else:
            lines.append({'top':c['top'],'bottom':c['bottom'],'chars':[c]})
    for c in small:
        mid=(c['top']+c['bottom'])/2
        best=None
        for L in lines:
            if L['top']-c['size']*0.6<=mid<=L['bottom']+c['size']*0.6:
                d=abs(mid-(L['top']+L['bottom'])/2)
                if best is None or d<best[0]: best=(d,L)
        if best:
            L=best[1]; c=dict(c)
            lm=(L['top']+L['bottom'])/2
            c['_sub']= 'sub' if mid>lm+1 else ('sup' if mid<lm-1 else None)
            L['chars'].append(c)
        else:
            lines.append({'top':c['top'],'bottom':c['bottom'],'chars':[c]})
    lines.sort(key=lambda L:L['top'])
    out=[]
    for L in lines:
        ln=sorted(L['chars'],key=lambda c:c['x0'])
        s=''; prev=None
        for c in ln:
            t=c['text']
            if c.get('_sub') and t.strip():
                t='\x01'+t+'\x02' if c['_sub']=='sub' else '\x03'+t+'\x04'
            if prev is not None and c['x0']-prev['x1'] > 0.25*c['size'] and not s.endswith(' ') and c['text']!=' ':
                s+=' '
            s+=t; prev=c
        s=re.sub(r'[\u200e\u200f\u202a-\u202e]','',s)
        s=visual_to_logical(s, mirror).strip()
        s=re.sub('\x01+','<sub>',re.sub('\x02+','</sub>',s))
        s=re.sub('\x03+','<sup>',re.sub('\x04+','</sup>',s))
        s=s.replace('<sub></sub>','').replace('</sub><sub>','').replace('</sup><sup>','')
        out.append(s)
    return out

def _bad_brackets(lines):
    bad=0
    for l in lines:
        m=re.search(r'[()]',l)
        if m and m.group()==')': bad+=1
    return bad

LAST_MIRROR = True

def pdf_lines(path):
    """Extract logical-order lines; auto-detects PDFs that store mirrored bracket glyphs."""
    global LAST_MIRROR
    LAST_MIRROR = True
    with pdfplumber.open(path) as pdf:
        a=[l for p in pdf.pages for l in page_lines(p, True)]
        if _bad_brackets(a) > 3:
            b=[l for p in pdf.pages for l in page_lines(p, False)]
            if _bad_brackets(b) < _bad_brackets(a):
                LAST_MIRROR = False
                return b
        return a

if __name__=='__main__':
    print('\n'.join(pdf_lines(sys.argv[1])))
