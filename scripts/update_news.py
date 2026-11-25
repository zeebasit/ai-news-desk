#!/usr/bin/env python3
from __future__ import annotations
import hashlib, html, json, math, re, sys
from difflib import SequenceMatcher
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import feedparser
import numpy as np
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/"config.json").read_text(encoding="utf-8"))
WATCH=json.loads((ROOT/"watchlist.json").read_text(encoding="utf-8"))
SET=CFG["settings"]; EW=SET.get("evidence_weights",{}); NOW=datetime.now(timezone.utc); MAXAGE=timedelta(hours=SET["max_age_hours"])
SESSION=requests.Session(); SESSION.headers.update({"User-Agent":"AI-News-Desk/1.0 headline-metadata-only"})

CATEGORY={
"Stavanger/Rogaland":["stavanger","rogaland","sandnes","jæren","jaeren","karmøy","karmoy","haugesund","jåttå","jatta","tananger","sola","ekofisk","vår energi","vaar energi","sus ","stavanger university hospital"],
"Norway":["norway","norwegian","oslo","storting","norges bank","equinor"],
"Tech":["artificial intelligence"," ai ","cyber","ransomware","hack","software","cloud","semiconductor","chip","openai","google","microsoft","apple","meta","nvidia","data center","datacentre","quantum"],
"Middle East":["israel","israeli","gaza","palestin","iran","iranian","iraq","syria","lebanon","saudi","yemen","houthi","qatar","uae","emirates","jordan","oman","hormuz"],
"US/Canada":["united states","u.s.","american","white house","congress","supreme court","federal law","appeals court","canada","canadian","alberta","ontario","quebec","ottawa","los angeles","new york city","chicago","houston","miami","boston","philadelphia","san francisco","seattle","washington dc","washington d.c.","alabama","alaska","arizona","arkansas","california","colorado","connecticut","delaware","florida","georgia","hawaii","idaho","illinois","indiana","iowa","kansas","kentucky","louisiana","maine","maryland","massachusetts","michigan","minnesota","mississippi","missouri","montana","nebraska","nevada","new hampshire","new jersey","new mexico","new york","north carolina","north dakota","ohio","oklahoma","oregon","pennsylvania","rhode island","south carolina","south dakota","tennessee","texas","utah","vermont","virginia","washington state","west virginia","wisconsin","wyoming"],
"Europe/UK":["europe","european","britain","british","england","france","french","germany","german","italy","italian","albania","albanian","spain","poland","ukraine","russia","romania","romanian","denmark","danish","sweden","swedish","finland","finnish","netherlands","dutch","belgium","belgian","austria","austrian","switzerland","swiss","greece","greek","portugal","portuguese","ireland","irish","nato"]
}
IMPACT=[
(20,["earthquake","tsunami","hurricane","cyclone","typhoon","wildfire","flood","flooding","landslide","eruption","state of emergency"]),
(20,["war","invasion","missile","airstrike","drone strike","ceasefire","nuclear","military attack","sanctions","blockade","naval blockade","tanker attack"]),
(20,["cyberattack","cyber attack","ransomware","power grid","critical infrastructure","hospital outage","airport outage","telecom outage","water system"]),
(18,["election","referendum","parliament","presidential","prime minister","government collapses","resigns","impeachment","constitutional"]),
(18,["outbreak","epidemic","pandemic","ebola","cholera","public health emergency"]),
(16,["central bank","interest rate","inflation","recession","oil prices","stock market","financial crisis","bank failure","market selloff","market rout","stocks plunge","futures rally"]),
(22,["bomb threat","bomb threats","mass evacuation","school closures","terrorism alert"]),
(15,["protest","protests","riot","riots","unrest","clashes","mass demonstration"]),
(16,["summit collapses","summit collapse","talks collapse","talks fail","negotiations collapse","negotiations fail","ends without agreement","agreement reached","peace agreement"]),
(13,["shipping","strait","pipeline","refinery","electricity","blackout","railway","airport"]),
(11,["science","spacecraft","mission","climate","breakthrough"])
]
ANCHORS=[
"large natural disaster causing deaths evacuations displacement or infrastructure damage",
"war military escalation missile attack ceasefire sanctions blockade or major diplomacy",
"national election referendum constitutional crisis coup government collapse or political transition",
"large protest civil unrest riots nationwide demonstrations or serious political instability",
"major cyberattack ransomware cyber physical incident or critical infrastructure disruption",
"power grid transport food water hospital telecom financial or essential service disruption",
"public health emergency epidemic outbreak international health threat or medical supply crisis",
"central bank shock inflation recession financial crisis sudden major market disruption",
"major corporate governance leadership change with broad market industry or strategic consequences",
"major merger acquisition takeover restructuring bankruptcy or corporate event with large economic impact",
"important artificial intelligence semiconductor cybersecurity science or technology development",
"major court legal regulatory antitrust or policy decision with wide consequences",
"industrial accident fire collapse explosion transport disaster or mass casualty event",
"government seizure nationalization expropriation or forced transfer of strategic energy assets",
"international defense production agreement joint procurement military industrial partnership",
"frontier artificial intelligence safety assessment systemic risk official warning or serious model vulnerability",
"historic first national spaceflight astronaut mission or scientific exploration milestone",
"official record high institutional mortality suicide or public health trend with quantified evidence",
"major climate energy shipping supply chain commodity or strategic chokepoint disruption",
"important Norway national policy economy security public service or energy development",
"important Stavanger Rogaland transport healthcare energy industry security or local public development"
]
LEADERSHIP_TERMS=["ceo","chief executive","chairman","president","board"]
LEADERSHIP_CHANGE_TERMS=["reinstated","resigns","resigned","ouster","ousted","removed","appointed","returns","return as","succession","steps down","stepped down"]
PAY=set(CFG.get("paywall_sources",[]))
TRUSTED_PATTERNS=["reuters","ap news","associated press","bbc","bloomberg","financial times","axios","al jazeera","drop site","nrk","stavanger aftenblad","aftenbladet","regjeringen","politiet"]
def trusted_source(name):
    n=(name or "").lower()
    return any(p in n for p in TRUSTED_PATTERNS)
def source_family(name):
    n=(name or "").lower()
    if "reuters" in n:return "reuters"
    if "associated press" in n or "ap news" in n:return "ap"
    if "bbc" in n:return "bbc"
    if "bloomberg" in n:return "bloomberg"
    if "financial times" in n:return "ft"
    if "al jazeera" in n:return "aljazeera"
    if "stavanger aftenblad" in n or "aftenbladet" in n:return "aftenbladet"
    if "regjeringen" in n:return "regjeringen"
    if "nrk" in n:return "nrk"
    if "politiet" in n:return "politiet"
    return n
CAS=re.compile(r"\b(?:(\d{1,5})\s+(?:people\s+)?(?:killed|dead|deaths|died)|(?:kills|killed)\s+(\d{1,5})|death toll (?:rises? to|at|of)?\s*(\d{1,5}))\b",re.I)
AFFECTED_RE=re.compile(r"\b(\d{1,3}(?:[,.]\d{3})+|\d+(?:\.\d+)?\s*(?:million|billion|thousand|m|k))\s+(?:people\s+)?(?:evacuated|displaced|affected|without power|without electricity|without water|hospitalized|injured|missing)\b",re.I)
MONEY_RE=re.compile(
    r"(?P<currency>US\$|C\$|A\$|\$|€|£|USD|EUR|GBP|CHF|CAD|AUD|NOK|SEK|DKK)\s*"
    r"(?P<amount>\d+(?:\.\d+)?)\s*"
    r"(?P<scale>trillion|trn|tn|billion|bn|million|mn|m)\b",re.I
)
MONEY_SCALE_TO_BILLIONS={
    "trillion":1000.0,"trn":1000.0,"tn":1000.0,
    "billion":1.0,"bn":1.0,
    "million":0.001,"mn":0.001,"m":0.001
}
# Coarse conversion factors are only used to bucket order-of-magnitude impact,
# never to display prices or perform financial calculations.
CURRENCY_TO_USD_APPROX={
    "$":1.0,"us$":1.0,"usd":1.0,
    "€":1.05,"eur":1.05,
    "£":1.25,"gbp":1.25,
    "chf":1.10,"c$":0.72,"cad":0.72,"a$":0.65,"aud":0.65,
    "nok":0.095,"sek":0.095,"dkk":0.14
}

def money_values_usd_billions(text):
    vals=[]
    for m in MONEY_RE.finditer(text or ""):
        cur=m.group("currency").lower()
        scale=MONEY_SCALE_TO_BILLIONS.get(m.group("scale").lower(),0)
        factor=CURRENCY_TO_USD_APPROX.get(cur,1.0)
        vals.append(float(m.group("amount"))*scale*factor)
    return vals

def numeric_scale(raw):
    x=raw.lower().replace(",","").strip()
    mult=1
    if "billion" in x: mult=1_000_000_000
    elif "million" in x or x.endswith("m"): mult=1_000_000
    elif "thousand" in x or x.endswith("k"): mult=1_000
    num=re.search(r"\d+(?:\.\d+)?",x)
    return float(num.group())*mult if num else 0

def generic_quantified_signals(text):
    t=text.lower(); points=0; reasons=[]
    pct=[float(x) for x in re.findall(r"\b(\d+(?:\.\d+)?)\s*%",t)]
    market_terms=["stock","stocks","share","shares","nasdaq","s&p","market","markets","futures","index","indices","market value","market cap","valuation"]
    if pct and any(k in t for k in market_terms):
        move=max(pct)
        broad_market=any(k in t for k in ["stock market","markets","nasdaq","s&p","dow","ftse","kospi","nikkei","index","indices","market-wide"])
        if broad_market:
            if move>=20: points+=18; reasons.append("major market reaction")
            elif move>=10: points+=14; reasons.append("large market reaction")
            elif move>=5: points+=9; reasons.append("large market move")
        else:
            if move>=20: points+=6; reasons.append("large company market move")
            elif move>=10: points+=5; reasons.append("company market move")
            elif move>=5: points+=3; reasons.append("company market move")

    money_vals=money_values_usd_billions(text)
    if money_vals:
        value=max(money_vals)
        transaction=any(k in t for k in ["acquire","acquisition","merger","takeover","deal","purchase","buy","sale"])
        value_change=any(k in t for k in ["market value","market cap","valuation","value climbs","value rises","value jumps","value gains","value falls","value drops","value wiped","adds ","added ","loses ","lost "])
        if transaction:
            if value>=10: points+=18; reasons.append("major transaction")
            elif value>=5: points+=12; reasons.append("large transaction")
            elif value>=1: points+=7; reasons.append("significant transaction")
        elif value_change:
            if value>=500: points+=18; reasons.append("major market-value change")
            elif value>=100: points+=14; reasons.append("large market-value change")
            elif value>=25: points+=10; reasons.append("significant market-value change")
            elif value>=10: points+=6; reasons.append("market-value change")

    a=AFFECTED_RE.search(t)
    if a:
        n=numeric_scale(a.group(1))
        if n>=1_000_000: points+=16
        elif n>=100_000: points+=12
        elif n>=10_000: points+=8
        else: points+=5
        reasons.append("large human impact")
    return points,reasons

def cluster_consensus_evidence(group):
    trusted={source_family(x["source"]) for x in group if trusted_source(x["source"])}
    points=0.0; reasons=[]
    n=len(trusted)
    cw=float(EW.get("trusted_source_consensus",5))
    vw=float(EW.get("coverage_velocity",8))
    if n>=5: points+=cw*3.0; reasons.append(f"{n} trusted sources")
    elif n==4: points+=cw*2.4; reasons.append("4 trusted sources")
    elif n==3: points+=cw*1.8; reasons.append("3 trusted sources")
    elif n==2: points+=cw; reasons.append("2 trusted sources")
    if n>=3:
        times=[]
        for x in group:
            if trusted_source(x["source"]):
                try: times.append(dateparser.parse(x["published_at"]))
                except: pass
        if len(times)>=3:
            spread=(max(times)-min(times)).total_seconds()/3600
            newest_age=(NOW-max(times)).total_seconds()/3600
            if spread<=6 and newest_age<=6:
                points+=vw; reasons.append("rapid cross-source coverage")
            elif spread<=12 and newest_age<=12:
                points+=vw*0.625; reasons.append("broad recent coverage")
    return points,reasons, trusted

def clean(x):
    x=html.unescape(x or ""); x=BeautifulSoup(x,"html.parser").get_text(" ",strip=True)
    return re.sub(r"\s+"," ",x).strip()
def title(x):
    t=clean(x); p=re.split(r"\s+-\s+",t)
    return " - ".join(p[:-1]).strip() if len(p)>1 and len(p[-1])<45 else t
def when(e):
    for raw in [getattr(e,"published",None),getattr(e,"updated",None)]:
        if raw:
            try:
                d=dateparser.parse(raw); return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
            except: pass
    return NOW

def entry_image(e):
    for attr in ["media_content","media_thumbnail"]:
        vals=getattr(e,attr,[]) or []
        for item in vals:
            u=item.get("url") if isinstance(item,dict) else None
            if u and u.startswith("http"): return u
    for item in getattr(e,"links",[]) or []:
        if not isinstance(item,dict): continue
        u=item.get("href") or item.get("url")
        typ=(item.get("type") or "").lower()
        rel=(item.get("rel") or "").lower()
        if u and u.startswith("http") and ("image" in typ or rel=="enclosure"):
            return u
    return ""
def grss(q,days=3):
    # Keep enough source history for the UI's Last 3 days filter.
    return "https://news.google.com/rss/search?q="+quote_plus(q+f" when:{days}d")+"&hl=en-US&gl=US&ceid=US:en"
def fetch(url,source,weight,limit=100,max_age=None):
    out=[]
    try:
        r=SESSION.get(url,timeout=20); r.raise_for_status(); f=feedparser.parse(r.content)
    except Exception as e:
        print("[warn]",source,e,file=sys.stderr); return out
    for e in f.entries[:limit]:
        t=title(getattr(e,"title","")); u=getattr(e,"link","")
        if not t or not u: continue
        d=when(e)
        if NOW-d>(max_age if max_age is not None else MAXAGE): continue
        s=clean(getattr(e,"summary","") or getattr(e,"description",""))[:500]
        actual=source
        try: actual=clean(e.source.get("title")) or source
        except: pass
        out.append({"title":t,"url":u,"source":actual,"published_at":d.isoformat(),"summary":s,"image":entry_image(e),"weight":weight,"paywalled":actual in PAY or source in PAY})
    return out
def collect():
    jobs=[]
    # Direct feeds get the widest window; discovery searches are capped before
    # embeddings so broad coverage does not turn into thousands of candidates.
    for f in CFG["direct_feeds"]: jobs.append((f["url"],f["name"],f["weight"],60))
    for s in CFG["trusted_sources"]: jobs.append((grss("site:"+s["domain"]),s["name"],s["weight"],40))
    for s in CFG.get("focused_searches",[]): jobs.append((grss(s["query"]),s["name"],s.get("weight",8),30))
    for q in CFG["global_sweeps"]: jobs.append((grss(q),"Global sweep",5,20))
    a=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(fetch,*job) for job in jobs]
        for future in as_completed(futures):
            try: a.extend(future.result())
            except Exception as e: print("[warn] fetch worker",e,file=sys.stderr)
    d={}
    for x in a:
        k=(re.sub(r"\W+"," ",x["title"].lower()).strip(),x["source"].lower())
        if k not in d or x["published_at"]>d[k]["published_at"]: d[k]=x
    return list(d.values())

def toks(x):
    stop={"the","and","for","with","from","after","into","over","amid","says","say","new","latest","this","that","its"}
    return {w for w in re.findall(r"[a-z0-9]+",x.lower()) if len(w)>2 and w not in stop}
def overlap(a,b):
    A,B=toks(a),toks(b)
    return len(A&B)/max(1,min(len(A),len(B))) if A and B else 0

def entityish(text):
    words=re.findall(r"\b[A-ZÆØÅ][A-Za-zÆØÅæøå0-9.-]{1,}\b",text or "")
    stop={"The","This","That","After","Before","How","Why","What","Can","Could","Will","New","Latest","Major"}
    return {w.lower().rstrip(".") for w in words if w not in stop}

def number_tokens(text):
    raw=re.findall(r"\b\d+(?:\.\d+)?\b",text or "")
    out=set(raw)
    for x in raw:
        if "." in x: out.add(x.split(".")[0])
    return out
def embeddings(texts):
    try:
        from sentence_transformers import SentenceTransformer
        m=SentenceTransformer(SET["semantic_model"])
        allv=m.encode(texts+ANCHORS,normalize_embeddings=True,batch_size=64,show_progress_bar=False)
        return np.asarray(allv[:len(texts)]),np.asarray(allv[len(texts):]),"sentence-transformers"
    except Exception as e:
        print("[warn] semantic fallback",e,file=sys.stderr)
        v=TfidfVectorizer(max_features=7000,ngram_range=(1,2),stop_words="english")
        z=v.fit_transform(texts+ANCHORS)
        return z[:len(texts)],z[len(texts):],"tfidf"
class DSU:
    def __init__(self,n): self.p=list(range(n))
    def f(self,x):
        while self.p[x]!=x: self.p[x]=self.p[self.p[x]]; x=self.p[x]
        return x
    def u(self,a,b):
        a,b=self.f(a),self.f(b)
        if a!=b:self.p[b]=a
def cluster(a,E,mode):
    S=cosine_similarity(E)
    th=SET["semantic_dedupe_threshold"] if mode=="sentence-transformers" else .60
    distinctive={"blockade","referendum","ransomware","earthquake","tsunami","wildfire","landslide","eruption","ceasefire","coup","impeachment","merger","acquisition","takeover","bomb","evacuation","outbreak","epidemic","blackout"}
    item_cat=[category(x["title"]+" "+x["summary"]) for x in a]

    def pair_match(i,j):
        sem=float(S[i,j]); ov=overlap(a[i]["title"],a[j]["title"])
        ti,tj=toks(a[i]["title"]),toks(a[j]["title"])
        close_time=abs((dateparser.parse(a[i]["published_at"])-dateparser.parse(a[j]["published_at"])).total_seconds())<=24*3600
        category_agree=(item_cat[i]==item_cat[j]) or "World" in (item_cat[i],item_cat[j])
        shared_distinctive=bool(ti & tj & distinctive)
        shared_entities=entityish(a[i]["title"]) & entityish(a[j]["title"])
        shared_numbers=number_tokens(a[i]["title"]) & number_tokens(a[j]["title"])

        # Extremely high semantic similarity can stand on its own.
        if sem>=max(.90,th+.06):
            return True
        # Otherwise require category compatibility plus lexical/event evidence.
        if not category_agree:
            return False
        if sem>=th and ov>=.20:
            return True
        if close_time and sem>=th-.08 and ov>=.42:
            return True
        if shared_distinctive and close_time and sem>=th-.12 and ov>=.30:
            return True
        if close_time and len(shared_entities)>=2 and shared_numbers and sem>=th-.14:
            return True
        return False

    # Representative-based clustering prevents transitive "bridge" articles from
    # chaining unrelated events into one giant cluster.
    order=sorted(range(len(a)),key=lambda i:(a[i]["weight"],a[i]["published_at"]),reverse=True)
    groups=[]; reps=[]
    for i in order:
        best=None; best_sem=-1.0
        for k,rep in enumerate(reps):
            if not pair_match(i,rep):
                continue
            members=groups[k]
            if len(members)>=3:
                compatible=sum(
                    1 for j in members
                    if float(S[i,j])>=th-.08 and overlap(a[i]["title"],a[j]["title"])>=.18
                )
                if compatible<max(1,len(members)//2):
                    continue
            if float(S[i,rep])>best_sem:
                best=k; best_sem=float(S[i,rep])
        if best is None:
            groups.append([i]); reps.append(i)
        else:
            groups[best].append(i)
    return groups

def category(text):
    t=" "+text.lower()+" "
    for c in ["Stavanger/Rogaland","Norway","Tech","Middle East","US/Canada","Europe/UK"]:
        if any(k in t for k in CATEGORY[c]):return c
    return "World"
# Paired signals require both an event/action and a consequential domain.
# No named entities, particular countries, or specific headlines are required.
def general_event_signals(text):
    t=text.lower()
    rules=[
        (24,"strategic asset intervention",
         r"\b(?:seiz\w*|expropriat\w*|nationali[sz]\w*|take(?:s|n)? control|took control|forced sale|asset freeze|assum\w* control)\b",
         r"\b(?:oilfields?|oil fields?|gas fields?|refiner\w*|pipeline\w*|ports?|mines?|energy assets?|power plants?|strategic assets?)\b"),
        (23,"defence industrial agreement",
         r"\b(?:defen[cs]e|military|weapons?|drones?|missiles?|fighter jets?|warships?|munitions?)\b",
         r"\b(?:joint production|co-production|coproduction|manufactur\w*|produc\w*|build\w*|procurement|industrial partnership)\b",
         r"\b(?:agreement|deal|accord|contract|partner\w*|sign\w*|joint|co-production|coproduction)\b"),
        (24,"frontier AI safety development",
         r"\b(?:artificial intelligence|ai|language models?|frontier models?)\b",
         r"\b(?:safety|systemic risk|catastrophic risk|security risk|dangerous capabilities|misalignment|deception)\b",
         r"\b(?:warn\w*|report\w*|assessment|evaluat\w*|research\w*|findings?|test\w*|study|studies|framework|agreement|concern\w*)\b"),
        (25,"historic space milestone",
         r"\b(?:astronaut\w*|spaceflight|space station|space mission|lunar mission|moon landing|orbital flight)\b",
         r"\b(?:first|historic|record[- ]breaking|unprecedented)\b",
         r"\b(?:select\w*|launch\w*|land\w*|fly|flies|flight|mission|travel\w*|send\w*|sent|reach\w*|orbit\w*|astronaut\w*)\b"),
        (24,"record institutional or health trend",
         r"\b(?:suicides?|mortality|deaths?|overdose\w*|infections?|hospitali[sz]ations?|disease|maternal mortality)\b",
         r"\b(?:record(?: high)?|highest|unprecedented|surge\w*|sharp rise|doubl\w*)\b",
         r"\b(?:official|data|report\w*|figures?|statistics|rate|cases?|military|army|armed forces|population|national|public health|health agency)\b")
    ]
    matches=[(pts,reason) for pts,reason,*patterns in rules
             if all(re.search(p,t) for p in patterns)]
    accident=re.search(r"\b(?:explosion\w*|blast\w*|fire|crash\w*|derail\w*|collapse\w*|industrial accident|mine accident|factory accident)\b",t)
    # Match plain integers and comma-separated counts, including reverse order.
    fatalities=[int(x.replace(",","")) for x in re.findall(
        r"\b(\d{1,3}(?:,\d{3})+|\d+)\s+(?:people\s+|workers\s+|passengers\s+)?(?:killed|dead|deaths|died)\b",t)]
    fatalities += [int(x.replace(",","")) for x in re.findall(
        r"\b(?:kills?|killed|left dead|death toll (?:rises? to|at|of))\s+(?:at least\s+)?(\d{1,3}(?:,\d{3})+|\d+)\b",t)]
    injuries=[int(x.replace(",","")) for x in re.findall(
        r"\b(\d{1,3}(?:,\d{3})+|\d+)\s+(?:people\s+|workers\s+|passengers\s+)?(?:injured|hurt|hospitali[sz]ed|missing)\b",t)]
    injuries += [int(x.replace(",","")) for x in re.findall(
        r"\b(?:injures?|injured|hospitali[sz]es?)\s+(?:at least\s+)?(\d{1,3}(?:,\d{3})+|\d+)\b",t)]
    if accident and (max(fatalities,default=0)>=5 or max(injuries,default=0)>=20):
        matches.append((26,"significant accident with human impact"))
    if not matches:return 0,[]
    # Cap the contribution to avoid stacking correlated evidence.
    return max(p for p,_ in matches),[reason for _,reason in matches]

def retrospective_age(title):
    """Approximate explicitly stated elapsed time; never infer the event date as fact."""
    t=title.lower()
    units={"day":1,"week":7,"month":30,"year":365,"decade":3650}
    numbers={"a":1,"an":1,"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9,"ten":10}
    m=re.search(r"\b(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)[ -]+(day|week|month|year|decade)s?\s+(?:on\b|later\b|ago\b|after\b|since\b)",t)
    if not m:
        m=re.search(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)[ -]+(day|week|month|year|decade)s?[- ]anniversary\b",t)
    if m:
        n=int(m[1]) if m[1].isdigit() else numbers[m[1]]
        return min(7300,n*units[m[2]])
    if re.search(r"\b(?:first anniversary|one-year anniversary|last year)\b",t):return 365
    return None

def retrospective_only(title):
    t=title.lower()
    age=retrospective_age(t)
    marker=bool((age and age>=30) or re.search(r"\b(?:on the anniversary|looking back|in retrospect|remembering|anniversary of)\b",t))
    recap=bool(re.search(r"\b(?:what to know|what we know|what happened|how it happened|looking back|in retrospect|remembering|in pictures|timeline|explained|commemorates?|marks? the anniversary)\b",t))
    if not (marker and recap):return False
    # Do not discard contemporary decisions just because the title references an old event.
    new_action=re.search(r"\b(?:finds?|concludes?|releases?|publishes?|issues?|orders?|rules?|charges?|arrests?|convicts?|sentences?|announces?|approves?|rejects?|resigns?|opens?|launches?|agrees?|signs?|begins?|starts?|resumes?|reveals?|confirms?|unveils?|votes?|reopens?|completes?|submits?|increases?|falls?|rises?|dies?|warns?|demands?|proposes?)\b",t)
    return not new_action

def is_analysis_headline(title):
    t=title.lower().strip()
    return retrospective_only(title) or bool(re.search(r"^(?:analysis|opinion|editorial|commentary|explainer|fact check)\s*[:—–-]",t)
        or re.search(r"^(?:why|how|what)\b.*\b(?:means?|matters?|could mean|to know|to expect|comes? next|happens? next)\b",t)
        or re.search(r"^(?:here['’]s what|here is what|what we know|what you need to know)\b",t))

def score(text,weight,semantic):
    t=text.lower(); s=float(weight)+semantic*float(EW.get("semantic_impact",SET.get("semantic_anchor_weight",12))); reasons=[]
    for pts,terms in IMPACT:
        if any(k in t for k in terms):
            s+=pts; reasons.append("high-impact event" if pts>=18 else "significant public impact")
            break
    nums=[int(x) for m in CAS.finditer(t) for x in m.groups() if x and int(x)>0]
    if nums:
        s+=min(22,5+math.log10(max(nums))*7); reasons.append("reported fatalities")
        if max(nums)>=10 and any(k in t for k in ["attack","attacks","strike","strikes","bombing","shelling","drone","missile"]):
            s+=14; reasons.append("mass-casualty attack")
    if any(k in t for k in ["nationwide","state of emergency","hundreds of thousands","millions","hundreds of schools"]):
        s+=float(EW.get("quantified_scale",10)); reasons.append("large scale")
    if "naval blockade" in t or "shipping blockade" in t:
        s+=5; reasons.append("strategic chokepoint risk")
    qpts,qreasons=generic_quantified_signals(t)
    s+=qpts; reasons.extend(qreasons)
    epts,ereasons=general_event_signals(t)
    s+=epts; reasons.extend(ereasons)
    leadership=any(k in t for k in LEADERSHIP_TERMS) and any(k in t for k in LEADERSHIP_CHANGE_TERMS)
    if leadership:
        s+=5; reasons.append("leadership/governance change")
    if any(k in t for k in ["norway","norwegian","stavanger","rogaland","sandnes"]):
        s+=float(EW.get("local_relevance",8)); reasons.append("Norway/local relevance")
    mag=re.search(r"\bmagnitude\s+([0-9]+(?:\.[0-9]+)?)",t)
    if mag and float(mag.group(1))<5.0 and not nums:
        s-=30; reasons.append("minor event filtered")
    if any(k in t for k in ["celebrity","horoscope","recipe","movie review","football transfer","lottery","christmas tree","royal ceremony","anniversary ceremony","travel tips","restaurant review"]):s-=28
    if any(k in t for k in ["not that unusual","what to know","what you need to know","explainer:","here's what","here is what","what next","what do we know"]):s-=16
    if re.search(r"^(why|how|what|can|could|should|will)\b.*\?$",t.strip()):s-=12
    if any(k in t for k in ["brief delays","minor disruption","brief disruption","quickly restored"]) and not nums:s-=8
    return s,reasons
def sid(t): return hashlib.sha1(" ".join(sorted(toks(t))[:12]).encode()).hexdigest()[:12]
def importance_level(sc,reasons,text):
    r=set(reasons); t=text.lower()
    severe_reasons={"large human impact","large scale","strategic chokepoint risk"}
    severe_terms=["nuclear","invasion","state of emergency","mass casualty","public health emergency","critical infrastructure","nationwide blackout","major cyberattack","military attack"]
    critical_evidence=bool(r & severe_reasons) or any(k in t for k in severe_terms)
    if sc>=68 and critical_evidence:return "Critical"
    if sc>=46:return "Major"
    return "Notable"

def consolidate_selected(stories,E):
    if len(stories)<2:return stories
    event_terms={"blockade","warship","missile","earthquake","tsunami","wildfire","flood","landslide","eruption","ceasefire","referendum","election","ransomware","cyberattack","merger","acquisition","takeover","bomb","evacuation","outbreak","blackout","protest","riot","strike","pipeline","refinery"}
    ordered=sorted(stories,key=lambda x:(x["score"],x["published_at"]),reverse=True)
    merged=[]
    for s in ordered:
        i=s.get("_lead_index")
        target=None
        for m in merged:
            j=m.get("_lead_index")
            if i is None or j is None:continue
            if bool(s.get("background_only"))!=bool(m.get("background_only")):continue
            same_cat=(s["category"]==m["category"]) or "World" in (s["category"],m["category"])
            if not same_cat:continue
            try:
                close=abs((dateparser.parse(s["published_at"])-dateparser.parse(m["published_at"])).total_seconds())<=30*3600
            except:
                close=True
            if not close:continue
            sem=float(cosine_similarity(E[i:i+1],E[j:j+1])[0,0])
            ov=overlap(s["title"],m["title"])
            ent=len(entityish(s["title"]) & entityish(m["title"]))
            shared_event=bool(toks(s["title"]) & toks(m["title"]) & event_terms)
            same=(sem>=.88 or
                  (sem>=.78 and ov>=.30) or
                  (sem>=.72 and ov>=.42) or
                  (sem>=.68 and shared_event and (ov>=.18 or ent>=1)) or
                  (ent>=2 and ov>=.18) or
                  (shared_event and ent>=1 and ov>=.16) or
                  (shared_event and ov>=.32))
            if same:
                target=m;break
        if target is None:
            merged.append(dict(s));continue

        # Higher-scoring card remains the representative; merge evidence/sources only.
        families={source_family(x["name"]) for x in target.get("sources",[])}
        for src in s.get("sources",[]):
            fam=source_family(src["name"])
            if fam not in families:
                target.setdefault("sources",[]).append(src);families.add(fam)
        target["sources"]=target.get("sources",[])[:8]
        target["source_count"]=len(families)
        target["published_at"]=max(target["published_at"],s["published_at"])
        target["reasons"]=list(dict.fromkeys(target.get("reasons",[])+s.get("reasons",[])))[:4]
        if not target.get("summary") and s.get("summary"):target["summary"]=s["summary"]
        if not target.get("image") and s.get("image"):target["image"]=s["image"]
        rank={"Notable":1,"Major":2,"Critical":3}
        if rank.get(s.get("importance"),0)>rank.get(target.get("importance"),0):
            target["importance"]=s["importance"]
    for s in merged:s.pop("_lead_index",None)
    return merged

def build(a):
    if not a:return {"generated_at":NOW.isoformat(),"model_mode":"none","stories":[],"watchlist":WATCH.get("events",[])}
    texts=[x["title"]+". "+x["summary"] for x in a]; E,A,mode=embeddings(texts)
    anchor=cosine_similarity(E,A).max(axis=1); out=[]
    for ids in cluster(a,E,mode):
        group=[a[i] for i in ids]
        factual_ids=[i for i in ids if not is_analysis_headline(a[i]["title"])]
        # A trusted, consequential historical recap may appear as Background, not breaking news.
        background_only=False
        if not factual_ids:
            factual_ids=[i for i in ids if retrospective_only(a[i]["title"]) and trusted_source(a[i]["source"])]
            if not factual_ids:continue
            background_only=True
        trusted_ids=[i for i in factual_ids if trusted_source(a[i]["source"])]
        lead_pool=trusted_ids or factual_ids
        lead_i=max(lead_pool,key=lambda i:(score(a[i]["title"]+" "+a[i]["summary"],a[i]["weight"],float(anchor[i]))[0],a[i]["published_at"]))
        lead=a[lead_i]
        factual_group=[a[i] for i in factual_ids]
        alltext=" ".join(x["title"]+" "+x["summary"] for x in factual_group)
        sc,reasons=score(alltext,max(x["weight"] for x in factual_group),max(float(anchor[i]) for i in factual_ids))
        coverage_names={source_family(x["source"]) for x in group}
        cpts,creasons,trusted_names=cluster_consensus_evidence(factual_group)
        sc+=cpts; reasons.extend(creasons)
        reason_set=set(reasons)
        if len(trusted_names)>=3 and ("large company market move" in reason_set or "company market move" in reason_set):
            sc+=8; reasons.append("corroborated market impact")
        if len(trusted_names)>=3 and "leadership/governance change" in reason_set:
            sc+=8; reasons.append("corroborated governance impact")
        if len(trusted_names)>=3 and "major transaction" in reason_set:
            sc+=5; reasons.append("corroborated transaction impact")
        if not trusted_names and len(coverage_names)>=3:
            sc+=2
        lead_cat=category(lead["title"]+" "+lead["summary"])
        cat_votes=defaultdict(int)
        for x in group: cat_votes[category(x["title"]+" "+x["summary"])]+=1
        max_votes=max(cat_votes.values())
        tied=[k for k,v in cat_votes.items() if v==max_votes]
        cat=lead_cat if lead_cat in tied else tied[0]
        if cat=="World" and lead_cat!="World" and cat_votes["World"]<=cat_votes[lead_cat]+1:
            cat=lead_cat
        if cat in ["Norway","Stavanger/Rogaland"]:
            if sc<36:continue
            if not trusted_names and sc<44:continue
        else:
            if sc<SET["minimum_score"]:continue
            if not trusted_names and sc<46:continue
        if background_only:
            # It passed the ordinary significance gate above; separate old impact from current news.
            sc=min(sc,40.0)
            reasons=["historical background, not a new event"]
        display_group=[x for x in group if trusted_source(x["source"])] or group
        src=[]; seen=set(); seen_names=set()
        for x in sorted(display_group,key=lambda q:(q["weight"],q["published_at"]),reverse=True):
            fam=source_family(x["source"])
            if x["url"] in seen or fam in seen_names:continue
            seen.add(x["url"]); seen_names.add(fam)
            src.append({"name":x["source"],"url":x["url"],"published_at":x["published_at"],"paywalled":x["paywalled"]})
        lead_summary=lead.get("summary","").strip()
        if len(lead_summary)>=60:
            brief=lead_summary[:360]
        else:
            brief_candidates=[x.get("summary","").strip() for x in display_group if source_family(x["source"])==source_family(lead["source"]) and len(x.get("summary","").strip())>=60]
            brief=(brief_candidates[0][:360] if brief_candidates else lead_summary[:360])
        image=lead.get("image","") or next((x.get("image","") for x in display_group if source_family(x["source"])==source_family(lead["source"]) and x.get("image")), "")
        out.append({"id":sid(lead["title"]),"title":lead["title"],"summary":brief,"image":image,"category":cat,"importance":"Notable" if background_only else importance_level(sc,reasons,alltext),"background_only":background_only,"score":round(sc,1),"published_at":max(x["published_at"] for x in group),"source_count":len(trusted_names) if trusted_names else len(coverage_names),"reasons":list(dict.fromkeys(reasons))[:4],"sources":src[:8],"lead_url":lead["url"],"_lead_index":lead_i})
    out=consolidate_selected(out,E)
    out.sort(key=lambda x:(x["score"],x["published_at"]),reverse=True)
    return {"generated_at":NOW.isoformat(),"model_mode":mode,"stories":out[:SET["top_story_limit"]],"watchlist":WATCH.get("events",[])}
def match_previous_story(cur, previous):
    best=None; best_score=0.0
    ct=cur.get("title","")
    csrc={source_family(x.get("name","")) for x in cur.get("sources",[])}
    cents=entityish(ct)
    for old in previous:
        ot=old.get("title","")
        ov=overlap(ct,ot)
        seq=SequenceMatcher(None,ct.lower(),ot.lower()).ratio()
        osrc={source_family(x.get("name","")) for x in old.get("sources",[])}
        src_overlap=len(csrc & osrc)
        src_match=src_overlap>0
        cat_match=cur.get("category")==old.get("category")
        shared_entities=len(cents & entityish(ot))
        try:
            old_ref=dateparser.parse(old.get("first_reported_at",old.get("published_at","")))
            cur_ref=dateparser.parse(cur.get("published_at",""))
            time_close=abs((cur_ref-old_ref).total_seconds())<=48*3600
        except:
            time_close=True

        score=max(seq,ov)+(0.08 if src_match else 0)+(0.04 if cat_match else 0)+min(.12,shared_entities*.03)
        strong=(
            (ov>=0.58 and seq>=0.42)
            or seq>=0.72
            or (src_match and ov>=0.50 and seq>=0.38)
            or (cat_match and time_close and src_overlap>=1 and shared_entities>=2 and ov>=0.28)
            or (cat_match and time_close and shared_entities>=3 and ov>=0.22)
        )
        if strong and score>best_score:
            best,best_score=old,score
    return best

def apply_continuity(payload, previous):
    prev=previous.get("stories",[]) if isinstance(previous,dict) else []
    run_time=dateparser.parse(payload.get("generated_at",NOW.isoformat()))
    prev_generated=None
    try:
        prev_generated=dateparser.parse(previous.get("generated_at",""))
    except:
        prev_generated=None
    momentum_window=float(SET.get("coverage_momentum_window_hours",3))
    momentum_min=int(SET.get("coverage_momentum_min_new_sources",2))
    history_hours=float(SET.get("coverage_history_hours",12))
    velocity_weight=float(EW.get("coverage_velocity",8))

    for s in payload.get("stories",[]):
        old=match_previous_story(s,prev)
        if not old:
            s["first_reported_at"]=s["published_at"]
            s["update_count"]=0
            s["updated"]=False
            s["coverage_history"]=[{"at":payload.get("generated_at",NOW.isoformat()),"source_count":int(s.get("source_count",0))}]
            continue

        s["id"]=old.get("id",s["id"])
        s["first_reported_at"]=old.get("first_reported_at",old.get("published_at",s["published_at"]))
        old_sources={source_family(x.get("name","")) for x in old.get("sources",[])}
        new_sources={source_family(x.get("name","")) for x in s.get("sources",[])}
        old_time=dateparser.parse(old.get("published_at",s["published_at"]))
        new_time=dateparser.parse(s["published_at"])
        material=(s.get("title")!=old.get("title") or len(new_sources-old_sources)>0 or new_time>old_time+timedelta(minutes=10))
        s["update_count"]=int(old.get("update_count",0))+(1 if material else 0)
        s["updated"]=bool(material)

        history=[]
        for h in old.get("coverage_history",[]) or []:
            try:
                ht=dateparser.parse(h.get("at",""))
                if run_time-ht<=timedelta(hours=history_hours):
                    history.append({"at":ht.isoformat(),"source_count":int(h.get("source_count",0))})
            except:
                pass
        if not history and prev_generated:
            history=[{"at":prev_generated.isoformat(),"source_count":int(old.get("source_count",0))}]

        current_count=int(s.get("source_count",0))
        baseline=None
        for h in history:
            try:
                ht=dateparser.parse(h["at"])
            except:
                continue
            age=(run_time-ht).total_seconds()/3600
            if 0.25<=age<=momentum_window:
                if baseline is None or ht<dateparser.parse(baseline["at"]):
                    baseline=h

        if baseline and not s.get("background_only"):
            elapsed=max(0.01,(run_time-dateparser.parse(baseline["at"])).total_seconds()/3600)
            growth=max(0,current_count-int(baseline.get("source_count",0)))
            if growth>=momentum_min:
                factor=1.0 if growth>=3 else 0.75
                bonus=velocity_weight*factor
                s["score"]=round(float(s.get("score",0))+bonus,1)
                s["reasons"]=list(dict.fromkeys((s.get("reasons") or [])+["rapid coverage growth"]))[:4]
                s["coverage_momentum"]={"new_sources":growth,"hours":round(elapsed,2),"bonus":round(bonus,1)}
                s["importance"]=importance_level(s["score"],s["reasons"],s.get("title","")+" "+s.get("summary",""))

        history.append({"at":payload.get("generated_at",NOW.isoformat()),"source_count":current_count})
        # De-duplicate timestamps and keep a short history only.
        by_at={h["at"]:h for h in history}
        s["coverage_history"]=sorted(by_at.values(),key=lambda h:h["at"])[-12:]

    payload["stories"].sort(key=lambda x:(x.get("score",0),x.get("published_at","")),reverse=True)
    return payload

# Context enrichment does not change ranking or the selected set.
CONTEXT_DAYS=7300
CONTEXT_ARCHIVE_LIMIT=500
CONTEXT_REPORT_LIMIT=6
CONTEXT_QUERY_LIMIT=12
CONTEXT_QUERY_VERSION=4
CONTEXT_STOP=set("a an the as at by of in to for from and or with into through over under its their his her is are was were be been being has have had can could would should will may might year years month months week weeks day days on ago later after before since anniversary about what know why how who when where this that these those here there deadly killed kills death deaths people latest update updates news report reports reporting says said more much new old first look looking back remember remembering last next today yesterday live breaking explained explainer guide timeline world suspected allegedly alleged officials official chief rep representative minister president democratic republican three two four five six seven eight nine ten dozens least".split())
CONTEXT_EVENTS=set("fire blaze explosion blast crash derailment flood earthquake tsunami wildfire hurricane cyclone landslide conflict war invasion ceasefire blockade sanctions election referendum coup protest strike outbreak epidemic pandemic refinery takeover acquisition merger lawsuit trial inquiry investigation accident disaster cyberattack ransomware outage breach bankruptcy collapse resignation assassination shooting returns reinstatement leadership market valuation stocks shares military warship drones spaceflight astronaut safety framework suicide mortality aid hunger famine".split())
CONTEXT_EQUIVALENTS={"return":"returns","returned":"returns","reinstated":"returns","reinstates":"returns","wars":"war","drones":"drone","warships":"warship","talks":"negotiation","negotiations":"negotiation","resigns":"resignation","resigned":"resignation","sanctioned":"sanctions","blaze":"fire","fires":"fire","explosions":"explosion","blast":"explosion","crashes":"crash","flooding":"flood","earthquakes":"earthquake","protests":"protest","elections":"election","investigations":"investigation","inquiries":"inquiry","mergers":"merger","acquisitions":"acquisition","takeovers":"takeover","sanction":"sanctions"}

def context_date(raw):
    try:
        dt=dateparser.parse(raw)
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except (ValueError,TypeError,OverflowError):
        return None

def context_report(item):
    title=item.get("title","").strip()
    url=item.get("lead_url") or item.get("url","")
    sources=item.get("sources",[])
    lead_source=next((x for x in sources if x.get("url")==url),{})
    source=item.get("source") or lead_source.get("name","")
    date=context_date(lead_source.get("published_at") or item.get("published_at"))
    if not title or not date or not trusted_source(source) or urlparse(url).scheme not in ("http","https") or not urlparse(url).netloc:
        return None
    if date>NOW+timedelta(minutes=10) or date<NOW-timedelta(days=CONTEXT_DAYS):
        return None
    return {"title":title[:400],"source":source,"url":url,"published_at":date.isoformat()}

def context_words(title):
    return list(dict.fromkeys(CONTEXT_EQUIVALENTS.get(w,w) for w in re.findall(r"[^\W\d_]+",title.lower(),re.UNICODE)
                              if len(w)>=2 and w not in CONTEXT_STOP))

def context_entities(title):
    return {w for w in entityish(title) if w not in CONTEXT_STOP and w not in CONTEXT_EVENTS}

def context_related(title,other,anchored=False):
    a,b=set(context_words(title)),set(context_words(other))
    shared=a&b
    entities=context_entities(title)&context_entities(other)
    ov=len(shared)/max(1,min(len(a),len(b)))
    specific=shared-entities-CONTEXT_EVENTS
    # A shared action/domain word plus multiple named anchors is strong evidence.
    if len(entities)>=3 and len(shared)>=4 and (shared-entities):return True
    if len(shared)>=3 and ((len(entities)>=2 and ov>=.45 and (specific or len(shared)>=4)) or
        (len(entities)>=1 and len(shared)>=4 and ov>=.65) or
        (len(shared)>=5 and ov>=.85)):
        return True
    # Date-anchored historical search can match shorter original headlines.
    # Location/entity plus event alone is NOT sufficient outside that date window.
    return anchored and len(entities)>=2 and bool(shared&CONTEXT_EVENTS) and len(shared)>=3

def context_query(title):
    # Remove publisher suffixes and prefer compact event-specific terms.
    title=re.split(r"\s+[|–—]\s+|\s+-\s+",title,maxsplit=1)[0]
    words=context_words(title)
    entities=context_entities(title)
    named=[w for w in words if w in entities]
    events=[w for w in words if w in CONTEXT_EVENTS and w not in named]
    if not named and not events:return ""
    # Keep short, high-information event nouns (e.g. fire, war, coup).
    terms=named[:3]+events[:2]
    for word in words:
        if word not in terms and len(terms)<3:terms.append(word)
    return " ".join(terms[:5]) if len(terms)>=2 else ""

def context_plan(title,date):
    age=retrospective_age(title)
    long_running=bool(re.search(r"\b(?:inquiry|investigation|trial|lawsuit|appeal|aftermath|reconstruction|ongoing|long-running|peace talks)\b",title,re.I))
    if age and age>=30:
        target=date-timedelta(days=age)
        margin=min(120,max(14,int(age*.12)))
        horizon=min(CONTEXT_DAYS,age+margin+30)
        return [(horizon,target-timedelta(days=margin),target+timedelta(days=margin)),(horizon,None,None),(min(CONTEXT_DAYS,max(730,horizon*2)),None,None)]
    if long_running:return [(180,None,None),(365,None,None),(730,None,None)]
    return [(30,None,None),(180,None,None),(365,None,None),(730,None,None)]

def context_search_url(query,plan):
    days,start,end=plan
    if start and end:
        q=f"{query} after:{start.date().isoformat()} before:{(end+timedelta(days=1)).date().isoformat()}"
        return "https://news.google.com/rss/search?q="+quote_plus(q)+"&hl=en-US&gl=US&ceid=US:en"
    if days>30:
        q=f"{query} after:{(NOW-timedelta(days=days)).date().isoformat()}"
        return "https://news.google.com/rss/search?q="+quote_plus(q)+"&hl=en-US&gl=US&ceid=US:en"
    return grss(query,days=days)

def add_story_context(payload,previous,articles,discover=True):
    previous=previous if isinstance(previous,dict) else {}
    raw_archive=list(previous.get("context_archive",[]))
    for old in previous.get("stories",[]):
        raw_archive.append(old)
        raw_archive.extend(old.get("context",{}).get("earlier_reporting",[]))
    raw_archive.extend(payload.get("stories",[]))
    previous_by_id={s.get("id"):s for s in previous.get("stories",[])}
    archive={}
    for item in raw_archive:
        report=context_report(item)
        if report:archive[report["url"]]=report
    recent=[]
    for article in articles:
        report=context_report(article)
        if report:recent.append(report)
    # Old string timestamps deliberately reset once to migrate the improved query algorithm.
    checks={}
    for key,value in previous.get("context_checks",{}).items():
        if not isinstance(value,dict) or value.get("version")!=CONTEXT_QUERY_VERSION:continue
        dt=context_date(value.get("at"))
        if dt and NOW-timedelta(days=30)<=dt<=NOW:checks[key]=value
    work=[]
    for story in payload.get("stories",[]):
        lead_report=context_report(story)
        date=context_date(lead_report["published_at"] if lead_report else story.get("published_at"))
        if not date:continue
        title=story["title"]; query=context_query(title)
        plans=context_plan(title,date)
        horizon=max(p[0] for p in plans)
        first=plans[0]; anchor_start,anchor_end=first[1:]
        urls={x.get("url") for x in story.get("sources",[])}
        urls.add(story.get("lead_url"))
        def eligible(report):
            dt=context_date(report["published_at"])
            anchored=bool(anchor_start and anchor_start<=dt<=anchor_end)
            # Explicit opinion is not evidence; factual explainers may be useful background.
            return (report["url"] not in urls and date-timedelta(days=horizon)<=dt<=date-timedelta(hours=6)
                and toks(title)!=toks(report["title"])
                and context_related(title,report["title"],anchored)
                and not re.search(r"^(?:opinion|editorial|commentary)\s*[:—–-]",report["title"],re.I))
        candidates=[r for r in list(archive.values())+recent if eligible(r)]
        key=story.get("id","")
        prior=previous_by_id.get(key,{})
        # Do not discard already accepted reporting simply because a new lead or query appeared.
        # Require the prior lead to match, and retain only trusted, genuinely earlier, distinct reports.
        if prior and (prior.get("title")==title or context_related(title,prior.get("title",""))):
            for item in prior.get("context",{}).get("earlier_reporting",[]):
                report=context_report(item)
                if report and report["url"] not in urls and context_date(report["published_at"])<date and toks(title)!=toks(report["title"]):
                    candidates.append(report)
        check=checks.get(key,{})
        if check.get("query")!=query:check={}
        last=context_date(check.get("at"))
        stage=min(max(0,int(check.get("stage",0))),len(plans)-1)
        # Unsearched stories go first; failed searches progress after 30 minutes,
        # successful searches cool down for 24 hours.
        delay=timedelta(hours=24) if check.get("matched") or stage==len(plans)-1 and check.get("exhausted") else timedelta(minutes=30)
        due=(last is None or NOW-last>=delay)
        work.append(dict(story=story,date=date,query=query,plans=plans,stage=stage,last=last,due=due,key=key,candidates=candidates,
                         horizon=horizon,anchor_start=anchor_start,anchor_end=anchor_end,urls=urls))
    def priority(w):
        return (w["last"] is not None,w["last"] or datetime.min.replace(tzinfo=timezone.utc),bool(w["candidates"]),not bool(w["anchor_start"]),-w["story"].get("score",0))
    queries=0
    for w in sorted(work,key=priority):
        story=w["story"];title=story["title"];query=w["query"];stage=w["stage"];plans=w["plans"];candidates=w["candidates"]
        # Background eligibility is broader than top-story ranking.
        if not (discover and w["key"] and query and w["due"] and queries<CONTEXT_QUERY_LIMIT):
            continue
        if len({r["url"] for r in candidates})>=3 and not w["anchor_start"]:continue
        queries+=1
        plan=plans[stage];days,start,end=plan
        # Alternate a compact named/topic query on widening attempts instead of repeating all terms.
        search_query=query
        if stage>0 and len(query.split())>3:
            terms=query.split(); event_terms=[x for x in terms if x in CONTEXT_EVENTS]
            search_query=" ".join(list(dict.fromkeys(terms[:2]+event_terms[:1] or terms[:3])))
        matches=[]
        try:
            older=fetch(context_search_url(search_query,plan),"Context discovery",5,45,max_age=timedelta(days=days+30))
            for item in older:
                report=context_report(item)
                if not report:continue
                dt=context_date(report["published_at"])
                if start and not start<=dt<=end:continue
                anchored=bool(w["anchor_start"] and w["anchor_start"]<=dt<=w["anchor_end"])
                if (report["url"] not in w["urls"] and w["date"]-timedelta(days=w["horizon"])<=dt<=w["date"]-timedelta(hours=6)
                    and toks(title)!=toks(report["title"])
                    and context_related(title,report["title"],anchored)
                    and not re.search(r"^(?:opinion|editorial|commentary)\s*[:—–-]",report["title"],re.I)):
                    matches.append(report)
            candidates.extend(matches)
        except Exception as exc:
            print("[warn] context discovery",exc,file=sys.stderr)
        checks[w["key"]]={"version":CONTEXT_QUERY_VERSION,"query":query,"at":NOW.isoformat(),
            "stage":min(stage+1,len(plans)-1) if start or not matches else stage,
            "matched":bool(matches) and not bool(start),"exhausted":not matches and stage==len(plans)-1,
            "searched_days":days}
    for w in work:
        unique={}
        for report in sorted(w["candidates"],key=lambda r:r["published_at"]):
            normalized=" ".join(sorted(context_words(report["title"])))
            if normalized and normalized not in unique:unique[normalized]=report
        reports=list(unique.values())
        reports=reports[:1]+reports[-(CONTEXT_REPORT_LIMIT-1):] if len(reports)>CONTEXT_REPORT_LIMIT else reports
        for report in reports:archive[report["url"]]=report
        check=checks.get(w["key"],{})
        w["story"]["context"]={"earlier_reporting":reports,"coverage_from":reports[0]["published_at"] if reports else None,
            "search_query":w["query"] or w["story"]["title"],"search_days":w["horizon"],
            "searched_days":check.get("searched_days"),"search_status":"matched" if reports else ("searched" if check else "queued")}
    # Keep matched old reports for current cards even if the general archive is full.
    pinned={r["url"]:r for w in work for r in w["story"]["context"]["earlier_reporting"]}
    remaining=sorted((r for k,r in archive.items() if k not in pinned),key=lambda r:r["published_at"],reverse=True)
    payload["context_archive"]=(list(pinned.values())+remaining)[:CONTEXT_ARCHIVE_LIMIT]
    payload["context_checks"]=dict(sorted(checks.items(),key=lambda x:x[1]["at"],reverse=True)[:CONTEXT_ARCHIVE_LIMIT])
    print("Context coverage:",sum(bool(w["story"]["context"]["earlier_reporting"]) for w in work),"/",len(work),"cards;",queries,"historical searches")
    return payload

def main():
    out=ROOT/"docs"/"data"/"news.json"
    try:
        previous=json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    except Exception:
        previous={}
    a=collect(); print("Collected",len(a),"items")
    if not a:
        raise RuntimeError("Collection returned no articles; preserving previous feed")
    p=apply_continuity(build(a),previous)
    if not p["stories"] and previous.get("stories"):
        raise RuntimeError("Ranking returned no stories; preserving previous feed")
    # Enrichment failure must not prevent normal publication.
    try:
        p=add_story_context(p,previous,a)
    except Exception as exc:
        print("[warn] story context unavailable",exc,file=sys.stderr)
        p["context_archive"]=previous.get("context_archive",[])
        p["context_checks"]=previous.get("context_checks",{})
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Published",len(p["stories"]),"stories; mode",p["model_mode"])
if __name__=="__main__":main()
