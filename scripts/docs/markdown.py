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

def heading_id(title,counts):
    """按页面顺序分配标题锚点；生成导航与检查重复标题共用同一规则。"""
    title=re.sub(r'!?\[([^\]]+)\]\([^)]+\)',r'\1',title)
    title=re.sub(r'<[^>]+>','',title).replace('`','').casefold()
    base=re.sub(r'\s','-',re.sub(r'[^\w\s-]','',title))
    number=counts[base]
    counts[base]+=1
    return base+('-'+str(number) if number else '')

def heading_rows(text):
    """返回原行号、层级、标题和锚点，供链接检查及语义章节读取共用。"""
    counts=Counter()
    result=[]
    for index,line in enumerate(without_fences(text).splitlines()):
        match=re.match(r'^\s{0,3}(#{1,6})\s+(.+?)\s*#*$',line)
        if match:result.append((index,len(match[1]),match[2],heading_id(match[2],counts)))
    return result

def heading_ids(text):
    return {row[3] for row in heading_rows(text)}

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
