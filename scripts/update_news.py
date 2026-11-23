#!/usr/bin/env python3
from __future__ import annotations
import hashlib, html, json, math, re, sys
from collections import defaultdict
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
SET=CFG["settings"]; NOW=datetime.now(timezone.utc); MAXAGE=timedelta(hours=SET["max_age_hours"])
SESSION=requests.Session(); SESSION.headers.update({"User-Agent":"AI-News-Desk/1.0 headline-metadata-only"})

CATEGORY={
"Stavanger/Rogaland":["stavanger","rogaland","sandnes","jæren","jaeren","karmøy","karmoy","haugesund","jåttå","jatta"],
"Norway":["norway","norwegian","oslo","storting","regjeringen","norges bank","equinor"],
"Tech":["artificial intelligence"," ai ","cyber","ransomware","hack","software","cloud","semiconductor","chip","openai","google","microsoft","apple","meta","nvidia","data center","datacentre","quantum"],
"Middle East":["israel","israeli","gaza","palestin","iran","iranian","iraq","syria","lebanon","saudi","yemen","houthi","qatar","uae","emirates","jordan","oman","hormuz"],
"US/Canada":["united states","u.s.","american","white house","congress","canada","canadian","alberta","ontario","quebec","ottawa"],
"Europe/UK":["europe","european","britain","british","england","france","french","germany","german","italy","italian","albania","albanian","spain","poland","ukraine","russia","romania","romanian","nato"]
}
IMPACT=[
(20,["earthquake","tsunami","hurricane","cyclone","typhoon","wildfire","flood","flooding","landslide","eruption","state of emergency"]),
(20,["war","invasion","missile","airstrike","drone strike","ceasefire","nuclear","military attack","sanctions"]),
(20,["cyberattack","cyber attack","ransomware","power grid","critical infrastructure","hospital outage","airport outage","telecom outage","water system"]),
(18,["election","referendum","parliament","presidential","prime minister","government collapses","resigns","impeachment","constitutional"]),
(18,["outbreak","epidemic","pandemic","ebola","cholera","public health emergency"]),
(16,["central bank","interest rate","inflation","recession","oil prices","stock market","financial crisis","bank failure"]),
(15,["protest","protests","riot","riots","unrest","clashes","mass demonstration"]),
(13,["shipping","strait","pipeline","refinery","electricity","blackout","railway","airport"]),
(11,["science","spacecraft","mission","climate","breakthrough"])
]
ANCHORS=[
"large natural disaster deaths evacuations infrastructure damage",
"war military escalation missile attack ceasefire sanctions major diplomacy",
"national election referendum constitutional crisis coup political transition",
"large protest civil unrest riots nationwide demonstrations",
"major cyberattack ransomware cyber physical critical infrastructure",
"power grid transport food water hospital telecom essential service disruption",
"public health emergency epidemic outbreak international significance",
"central bank inflation recession financial crisis major market disruption",
"important artificial intelligence semiconductor cybersecurity science technology",
"important Norway national policy economy security public services",
"important Stavanger Rogaland transport healthcare energy industry security"
]
PAY=set(CFG.get("paywall_sources",[]))
CAS=re.compile(r"\b(?:(\d{1,5})\s+(?:people\s+)?(?:killed|dead|deaths|died)|(?:kills|killed)\s+(\d{1,5})|death toll (?:rises? to|at|of)?\s*(\d{1,5}))\b",re.I)

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
def grss(q):
    return "https://news.google.com/rss/search?q="+quote_plus(q+" when:1d")+"&hl=en-US&gl=US&ceid=US:en"
def fetch(url,source,weight):
    out=[]
    try:
        r=SESSION.get(url,timeout=20); r.raise_for_status(); f=feedparser.parse(r.content)
    except Exception as e:
        print("[warn]",source,e,file=sys.stderr); return out
    for e in f.entries[:100]:
        t=title(getattr(e,"title","")); u=getattr(e,"link","")
        if not t or not u: continue
        d=when(e)
        if NOW-d>MAXAGE: continue
        s=clean(getattr(e,"summary","") or getattr(e,"description",""))[:500]
        actual=source
        try: actual=clean(e.source.get("title")) or source
        except: pass
        out.append({"title":t,"url":u,"source":actual,"published_at":d.isoformat(),"summary":s,"weight":weight,"paywalled":actual in PAY or source in PAY})
    return out
def collect():
    a=[]
    for f in CFG["direct_feeds"]: a+=fetch(f["url"],f["name"],f["weight"])
    for s in CFG["trusted_sources"]: a+=fetch(grss("site:"+s["domain"]),s["name"],s["weight"])
    for q in CFG["global_sweeps"]: a+=fetch(grss(q),"Global sweep",5)
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
    for i in range(len(a)):
        for j in range(i+1,len(a)):
            if S[i,j]>=th or (S[i,j]>=th-.08 and overlap(a[i]["title"],a[j]["title"])>=.52): d.u(i,j)
    g=defaultdict(list)
    for i in range(len(a)):g[d.f(i)].append(i)
    return list(g.values())
def category(text):
    t=" "+text.lower()+" "
    for c in ["Stavanger/Rogaland","Norway","Tech","Middle East","US/Canada","Europe/UK"]:
        if any(k in t for k in CATEGORY[c]):return c
    return "World"
def score(text,weight,semantic):
    t=text.lower(); s=float(weight)+semantic*16; reasons=[]
    for pts,terms in IMPACT:
        if any(k in t for k in terms):s+=pts; reasons.append("high-impact event" if pts>=18 else "significant public impact");break
    m=CAS.search(t)
    if m:
        nums=[int(x) for x in m.groups() if x]
        if nums:s+=min(22,5+math.log10(max(nums))*7); reasons.append("reported fatalities")
    if any(k in t for k in ["nationwide","state of emergency","hundreds of thousands","millions"]):s+=10; reasons.append("large scale")
    if any(k in t for k in ["norway","norwegian","stavanger","rogaland","sandnes"]):s+=9; reasons.append("Norway/local relevance")
    if any(k in t for k in ["celebrity","horoscope","recipe","movie review","football transfer","lottery"]):s-=30
    return s,reasons
def sid(t): return hashlib.sha1(" ".join(sorted(toks(t))[:12]).encode()).hexdigest()[:12]
def build(a):
    if not a:return {"generated_at":NOW.isoformat(),"model_mode":"none","stories":[],"watchlist":WATCH.get("events",[])}
    texts=[x["title"]+". "+x["summary"] for x in a]; E,A,mode=embeddings(texts)
    anchor=cosine_similarity(E,A).max(axis=1); out=[]
    for ids in cluster(a,E,mode):
        group=[a[i] for i in ids]; lead=max(group,key=lambda x:(x["weight"],x["published_at"]))
        alltext=" ".join(x["title"]+" "+x["summary"] for x in group)
        sc,reasons=score(alltext,max(x["weight"] for x in group),max(float(anchor[i]) for i in ids))
        names={x["source"].lower() for x in group}
        if len(names)>=2:sc+=min(12,4+(len(names)-2)*2); reasons.append(str(len(names))+" sources")
        cat=category(alltext); floor=28 if cat in ["Norway","Stavanger/Rogaland"] else SET["minimum_score"]
        if sc<floor:continue
        src=[]; seen=set()
        for x in sorted(group,key=lambda q:(q["weight"],q["published_at"]),reverse=True):
            if x["url"] in seen:continue
            seen.add(x["url"]);src.append({"name":x["source"],"url":x["url"],"published_at":x["published_at"],"paywalled":x["paywalled"]})
        out.append({"id":sid(lead["title"]),"title":lead["title"],"category":cat,"importance":"Critical" if sc>=72 else "Major" if sc>=52 else "Notable","score":round(sc,1),"published_at":max(x["published_at"] for x in group),"source_count":len(names),"reasons":list(dict.fromkeys(reasons))[:4],"sources":src[:8],"lead_url":lead["url"]})
    out.sort(key=lambda x:(x["score"],x["published_at"]),reverse=True)
    return {"generated_at":NOW.isoformat(),"model_mode":mode,"stories":out[:SET["top_story_limit"]],"watchlist":WATCH.get("events",[])}
def main():
    a=collect(); print("Collected",len(a),"items"); p=build(a)
    out=ROOT/"docs"/"data"/"news.json"; out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Published",len(p["stories"]),"stories; mode",p["model_mode"])
if __name__=="__main__":main()
