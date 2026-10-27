# 解析项目使用的 Markdown 链接与标题，代码示例不参与文档依赖校验。
import re
from collections import Counter

def without_fences(text):
    output=[]
    fence=None
    for line in text.splitlines():
        marker=re.match(r'^\s{0,3}(`{3,}|~{3,})',line)
        if marker:
            token=marker.group(1)
            if fence is None:fence=token
            elif token[0]==fence[0] and len(token)>=len(fence):fence=None
            output.append('')
        else:output.append(line if fence is None else '')
    return '\n'.join(output)

def heading_ids(text):
    counts=Counter()
    result=set()
    for line in without_fences(text).splitlines():
        match=re.match(r'^\s{0,3}#{1,6}\s+(.+?)\s*#*$',line)
        if not match:continue
        title=re.sub(r'!?\[([^\]]+)\]\([^)]+\)',r'\1',match.group(1))
        title=re.sub(r'<[^>]+>','',title).replace('`','').casefold()
        base=re.sub(r'\s','-',re.sub(r'[^\w\s-]','',title))
        number=counts[base]
        result.add(base+('-'+str(number) if number else ''))
        counts[base]+=1
    return result

def link_targets(text):
    prose=re.sub(r'(`+).*?\1',lambda m:' '*len(m.group()),without_fences(text))
    values=[]
    references={}
    for name,target in re.findall(r'^\s{0,3}\[([^\]]+)\]:\s*(<[^>]+>|\S+)',prose,re.M):
        references[' '.join(name.casefold().split())]=target
        values.append(target)
    values += re.findall(r'!?\[[^\]]*\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+["\'][^\n]*?["\'])?\s*\)',prose)
    missing=[]
    for label,reference in re.findall(r'!?\[([^\]]+)\]\[([^\]]*)\]',prose):
        key=' '.join((reference or label).casefold().split())
        if key not in references:missing.append(reference or label)
    return values,missing
