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
"Norway":["norway","norwegian","oslo","storting","regjeringen","norges bank","equinor"],
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
MONEY_RE=re.compile(r"\$\s*(\d+(?:\.\d+)?)\s*(billion|million)\b",re.I)

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
    market_terms=["stock","stocks","share","shares","nasdaq","s&p","market","markets","futures","index","indices","market value"]
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
    m=MONEY_RE.search(t)
    if m and any(k in t for k in ["acquire","acquisition","merger","takeover","deal","purchase","buy","sale"]):
        value=float(m.group(1))*(1000 if m.group(2).lower()=="billion" else 1)
        if value>=10_000: points+=18; reasons.append("major transaction")
        elif value>=5_000: points+=12; reasons.append("large transaction")
        elif value>=1_000: points+=7; reasons.append("significant transaction")
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
    points=0; reasons=[]
    n=len(trusted)
    if n>=5: points+=15; reasons.append(f"{n} trusted sources")
    elif n==4: points+=12; reasons.append("4 trusted sources")
    elif n==3: points+=9; reasons.append("3 trusted sources")
    elif n==2: points+=5; reasons.append("2 trusted sources")
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
                points+=8; reasons.append("rapid cross-source coverage")
            elif spread<=12 and newest_age<=12:
                points+=5; reasons.append("broad recent coverage")
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
    S=cosine_similarity(E); d=DSU(len(a)); th=SET["semantic_dedupe_threshold"] if mode=="sentence-transformers" else .60
    distinctive={"blockade","referendum","ransomware","earthquake","tsunami","wildfire","landslide","eruption","ceasefire","coup","impeachment","merger","acquisition","takeover","bomb","evacuation","outbreak","epidemic","blackout"}
    for i in range(len(a)):
        for j in range(i+1,len(a)):
            ov=overlap(a[i]["title"],a[j]["title"])
            ti,tj=toks(a[i]["title"]),toks(a[j]["title"])
            shared_distinctive=(ti & tj & distinctive)
            close_time=abs((dateparser.parse(a[i]["published_at"])-dateparser.parse(a[j]["published_at"])).total_seconds())<=18*3600
            same_event_hint=bool(shared_distinctive) and close_time and ov>=.35 and S[i,j]>=th-.16
            if S[i,j]>=th or (S[i,j]>=th-.08 and ov>=.52) or same_event_hint:
                d.u(i,j)
    g=defaultdict(list)
    for i in range(len(a)):g[d.f(i)].append(i)
    return list(g.values())
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
        cat=category(alltext)
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
        brief_candidates=[x.get("summary","").strip() for x in display_group if len(x.get("summary","").strip())>=70]
        brief=max(brief_candidates,key=len)[:360] if brief_candidates else ""
        image=next((x.get("image","") for x in display_group if x.get("image")), "")
        out.append({"id":sid(lead["title"]),"title":lead["title"],"summary":brief,"image":image,"category":cat,"importance":importance_level(sc,reasons,alltext),"score":round(sc,1),"published_at":max(x["published_at"] for x in group),"source_count":len(trusted_names) if trusted_names else len(coverage_names),"reasons":list(dict.fromkeys(reasons))[:4],"sources":src[:8],"lead_url":lead["url"]})
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
    for s in payload.get("stories",[]):
        old=match_previous_story(s,prev)
        if not old:
            s["first_reported_at"]=s["published_at"]
            s["update_count"]=0
            s["updated"]=False
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
