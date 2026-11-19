"""Parse cited financial quantities without dropping their scale or unit."""
from dataclasses import dataclass,replace
from decimal import Decimal
import re

SMALL=dict(zip('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split(),range(20)))
TENS=dict(zip('twenty thirty forty fifty sixty seventy eighty ninety'.split(),range(20,100,10)))
SCALES={'thousand':1000,'million':1000000,'billion':1000000000,'trillion':1000000000000}
WORD=re.compile(r'\b(?:'+'|'.join(SMALL|TENS|SCALES|{'hundred':100})+r')\b',re.I)


def written(text):
    tokens=text.lower().replace('-',' ').split()
    if not tokens or tokens[0]=='and' or tokens[-1]=='and':raise ValueError('Unsupported written amount')
    total=group=0;previous=None;last_scale=10**15
    for token in tokens:
        if token=='and':continue
        if token in SMALL or token in TENS:
            value=(SMALL|TENS)[token]
            if previous in SMALL or (previous in TENS and value>=10):raise ValueError('Unsupported written amount')
            group+=value
        elif token=='hundred':
            if group>9 or previous=='hundred':raise ValueError('Unsupported written amount')
            group=(group or 1)*100
        elif token in SCALES:
            scale=SCALES[token]
            if scale>=last_scale:raise ValueError('Unsupported written amount')
            total+=(group or 1)*scale;group=0;last_scale=scale
        else:raise ValueError('Unsupported written amount')
        previous=token
    return Decimal(total+group)


@dataclass(frozen=True)
class Quantity:
    start:int
    end:int
    value:Decimal | None
    unit:str
    printed:str


def quantity(text,start,end,value):
    unit='scalar';tail=text[end:]
    scale=re.match(r'\s*(thousand|million|billion|trillion)\b',tail,re.I)
    if scale:
        value*=SCALES[scale[1].lower()];end+=scale.end();tail=text[end:]
    rate=re.match(r'\s*(basis\s+points?|bps\b|percentage\s+points?|percent(?:age)?\b|%)',tail,re.I)
    if rate:
        label=rate[1].lower()
        unit='rate_change' if label.startswith(('basis','bps','percentage point')) else 'rate'
        value/=10000 if label.startswith(('basis','bps')) else 100
        end+=rate.end()
    else:
        currency=re.search(r'(USD|EUR|GBP|\$|€|£)\s*$',text[:start],re.I)
        following=re.match(r'\s*(USD|EUR|GBP|dollars?|euros?|pounds?|shares?)\b',tail,re.I)
        if currency or following:
            label=(currency[1] if currency else following[1]).lower()
            unit={'$':'USD','dollar':'USD','dollars':'USD','usd':'USD','€':'EUR','eur':'EUR','euro':'EUR','euros':'EUR','£':'GBP','gbp':'GBP','pound':'GBP','pounds':'GBP','share':'shares','shares':'shares'}[label]
            if following:end+=following.end()
    return Quantity(start,end,value,unit,text[start:end])


def quantities(text,number_pattern,word_matches):
    result=[]
    for match in number_pattern.finditer(text):
        raw=match[0].replace(',','').replace('−','-')
        # Leave the percent suffix to the same unit parser used for words.
        end=match.end()-int(raw.endswith('%'))
        value=Decimal(raw.removesuffix('%'))
        result.append(quantity(text,match.start(),end,value))
    eligible={(m.start(),m.end()) for m in word_matches}
    groups=[]
    for match in WORD.finditer(text):
        if groups and re.fullmatch(r'[\s-]+|\s+and\s+',text[groups[-1][-1].end():match.start()]):groups[-1].append(match)
        else:groups.append([match])
    for group in groups:
        start,end=group[0].start(),group[-1].end()
        explicit=re.match(r'\s*(?:bps|basis\s+points?|percentage\s+points?|percent|USD|EUR|GBP|dollars?|euros?|pounds?|shares?)\b',text[end:],re.I)
        if not explicit and not any((m.start(),m.end()) in eligible for m in group):continue
        if any(q.start<=start<q.end for q in result):continue # magnitude after digits
        try:result.append(quantity(text,start,end,written(text[start:end])))
        except ValueError:result.append(Quantity(start,end,None,'unsupported',text[start:end]))
    return result


def matches(claim,source):
    if claim.value is None or claim.value!=source.value:return False
    return claim.unit==source.unit or 'scalar' in (claim.unit,source.unit)


def section_scale(lines,index):
    """Read explicit, standalone unit declarations within the cited section.

    A sentence describing one table is not a section-wide declaration. A new
    SEC Item/Part or financial statement ends the preceding unit scope.
    """
    scale=None
    for line in lines[:index+1]:
        if re.match(r'^\s*(?:Item\s+\d+[A-Z]?\b|PART\s+[IVX]+\b|CONSOLIDATED\s+(?:STATEMENTS|BALANCE))',line,re.I):scale=None
        declaration=re.match(r'^\s*\(?\s*(?:amounts|dollar amounts|dollars)\s+in\s+(thousands|millions|billions|trillions)\b',line,re.I)
        if declaration:scale=Decimal(SCALES[declaration[1].lower().removesuffix('s')])
    return scale


def source_quantities(lines,index,number_pattern,word_matches):
    text=lines[index]
    result=quantities(text,number_pattern,word_matches)
    scale=section_scale(lines,index)
    if scale is None:return result
    scaled=[]
    for q in result:
        explicit=any(re.search(r'\b'+unit+r'\b',q.printed,re.I) for unit in SCALES)
        per_share=re.match(r'\s*(?:per\s+(?:(?:basic|diluted|common)\s+)?share\b|/\s*share\b)',text[q.end:],re.I)
        per_share=per_share or re.search(r'\b(?:per\s+(?:(?:basic|diluted|common)\s+)?share|EPS)\b[^,;:.]{0,30}$',text[:q.start],re.I)
        if q.unit in {'USD','EUR','GBP'} and not explicit and not per_share and q.value is not None:
            q=replace(q,value=q.value*scale)
        scaled.append(q)
    return scaled


def enumeration_spans(line):
    """Recognize a list's labels without hiding parenthesized amounts."""
    labels=list(re.finditer(r'\((\d+)\)(?=\s+[A-Za-z])',line))
    if not labels:return []
    prefix=line[:labels[0].start()].strip()
    if prefix and not prefix.endswith(':'):return []
    if [int(m[1]) for m in labels]!=list(range(1,len(labels)+1)):return []
    units=r'\s*(?:USD|EUR|GBP|dollars?|euros?|pounds?|thousand|million|billion|trillion|percent|basis|shares?|units?|members?|warehouses?|contracts?)\b'
    if any(re.match(units,line[m.end():],re.I) for m in labels):return []
    return [m.span() for m in labels]


def heading_spans(line):
    """Heading counters are IDs; a magnitude/unit immediately after is not."""
    patterns=[r'^\s*(?:(?:#{1,6}|==)\s*)?\d+[.)]\s+',
              r'^\s*(?:#{1,6}|==)\s*\d+\s+']
    spans=[]
    units=r'(?:USD|EUR|GBP|dollars?|euros?|pounds?|thousands?|millions?|billions?|trillions?|percent|basis|bps|shares?|units?|members?|warehouses?)\b'
    for pattern in patterns:
        m=re.match(pattern,line)
        if m and not re.match(units,line[m.end():],re.I):spans.append(m.span())
    return spans
