#!/usr/bin/env python3
from __future__ import annotations
import hashlib, html, json, math, re, sys
from difflib import SequenceMatcher
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote_plus

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
    r"(?P<currency>US\\$|C\\$|A\\$|\\$|€|£|USD|EUR|GBP|CHF|CAD|AUD|NOK|SEK|DKK)\\s*"
    r"(?P<amount>\\d+(?:\\.\\d+)?)\\s*"
    r"(?P<scale>trillion|trn|tn|billion|bn|million|mn|m)\\b",re.I
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
def grss(q):
    # Keep enough source history for the UI's Last 3 days filter.
    return "https://news.google.com/rss/search?q="+quote_plus(q+" when:3d")+"&hl=en-US&gl=US&ceid=US:en"
def fetch(url,source,weight,limit=100):
    out=[]
    try:
        r=SESSION.get(url,timeout=20); r.raise_for_status(); f=feedparser.parse(r.content)
    except Exception as e:
        print("[warn]",source,e,file=sys.stderr); return out
    for e in f.entries[:limit]:
        t=title(getattr(e,"title","")); u=getattr(e,"link","")
        if not t or not u: continue
        d=when(e)
        if NOW-d>MAXAGE: continue
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
def score(text,weight,semantic):
    t=text.lower(); s=float(weight)+semantic*float(EW.get("semantic_impact",SET.get("semantic_anchor_weight",12))); reasons=[]
    for pts,terms in IMPACT:
        if any(k in t for k in terms):
            s+=pts; reasons.append("high-impact event" if pts>=18 else "significant public impact")
            break
    m=CAS.search(t)
    if m:
        nums=[int(x) for x in m.groups() if x]
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
    leadership=any(k in t for k in LEADERSHIP_TERMS) and any(k in t for k in LEADERSHIP_CHANGE_TERMS)
    if leadership:
        s+=5; reasons.append("leadership/governance change")
    if any(k in t for k in ["norway","norwegian","stavanger","rogaland","sandnes"]):
        s+=float(EW.get("local_relevance",8)); reasons.append("Norway/local relevance")
    mag=re.search(r"\bmagnitude\s+([0-9]+(?:\.[0-9]+)?)",t)
    if mag and float(mag.group(1))<5.0 and not CAS.search(t):
        s-=30; reasons.append("minor event filtered")
    if any(k in t for k in ["celebrity","horoscope","recipe","movie review","football transfer","lottery","christmas tree","royal ceremony","anniversary ceremony","travel tips","restaurant review"]):s-=28
    if any(k in t for k in ["not that unusual","what to know","what you need to know","explainer:","here's what","here is what","what next","what do we know"]):s-=16
    if re.search(r"^(why|how|what|can|could|should|will)\b.*\?$",t.strip()):s-=12
    if any(k in t for k in ["brief delays","minor disruption","brief disruption","quickly restored"]) and not CAS.search(t):s-=8
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
        trusted_ids=[i for i in ids if trusted_source(a[i]["source"])]
        lead_pool=trusted_ids or ids
        lead_i=max(lead_pool,key=lambda i:(score(a[i]["title"]+" "+a[i]["summary"],a[i]["weight"],float(anchor[i]))[0],a[i]["published_at"]))
        lead=a[lead_i]
        alltext=" ".join(x["title"]+" "+x["summary"] for x in group)
        sc,reasons=score(alltext,max(x["weight"] for x in group),max(float(anchor[i]) for i in ids))
        coverage_names={source_family(x["source"]) for x in group}
        cpts,creasons,trusted_names=cluster_consensus_evidence(group)
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
        out.append({"id":sid(lead["title"]),"title":lead["title"],"summary":brief,"image":image,"category":cat,"importance":importance_level(sc,reasons,alltext),"score":round(sc,1),"published_at":max(x["published_at"] for x in group),"source_count":len(trusted_names) if trusted_names else len(coverage_names),"reasons":list(dict.fromkeys(reasons))[:4],"sources":src[:8],"lead_url":lead["url"],"_lead_index":lead_i})
    out=consolidate_selected(out,E)
    out.sort(key=lambda x:(x["score"],x["published_at"]),reverse=True)
    return {"generated_at":NOW.isoformat(),"model_mode":mode,"stories":out[:SET["top_story_limit"]],"watchlist":WATCH.get("events",[])}
def match_previous_story(cur, previous):
    best=None; best_score=0.0
    ct=cur.get("title","")
    csrc={source_family(x.get("name","")) for x in cur.get("sources",[])}
    for old in previous:
        ot=old.get("title","")
        ov=overlap(ct,ot)
        seq=SequenceMatcher(None,ct.lower(),ot.lower()).ratio()
        osrc={source_family(x.get("name","")) for x in old.get("sources",[])}
        src_match=bool(csrc & osrc)
        cat_match=cur.get("category")==old.get("category")
        score=max(seq,ov)+(0.08 if src_match else 0)+(0.04 if cat_match else 0)
        strong=((ov>=0.58 and seq>=0.42) or seq>=0.72 or (src_match and ov>=0.50 and seq>=0.38))
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

        if baseline:
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

def main():
    out=ROOT/"docs"/"data"/"news.json"
    try:
        previous=json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    except Exception:
        previous={}
    a=collect(); print("Collected",len(a),"items"); p=apply_continuity(build(a),previous)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Published",len(p["stories"]),"stories; mode",p["model_mode"])
if __name__=="__main__":main()
