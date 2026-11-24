const state={data:null,category:"Top",hours:24,importance:"all",query:"",savedOnly:false};
const categories=["Top","World","US/Canada","Europe/UK","Middle East","Tech","Norway","Stavanger/Rogaland"];
const saved=new Set(JSON.parse(localStorage.getItem("ai-news-saved")||"[]"));

function rel(iso){
  const m=Math.max(0,Math.floor((Date.now()-new Date(iso).getTime())/60000));
  if(m<60)return m+"m ago";
  const h=Math.floor(m/60);
  return h<48?h+"h ago":Math.floor(h/24)+"d ago";
}
function esc(s){return String(s||"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function timeOk(s){return (Date.now()-new Date(s.published_at).getTime())/36e5<=state.hours}
function categoryOk(s){return state.category==="Top"||s.category===state.category}
function ok(s){
  if(!timeOk(s)||!categoryOk(s))return false;
  if(state.importance==="Critical"&&s.importance!=="Critical")return false;
  if(state.importance==="Major"&&!["Major","Critical"].includes(s.importance))return false;
  if(state.savedOnly&&!saved.has(s.id))return false;
  const hay=(s.title+" "+(s.summary||"")+" "+(s.category||"")).toLowerCase();
  if(state.query&&!hay.includes(state.query.toLowerCase()))return false;
  return true;
}
function tabs(){
  const r=document.getElementById("categoryTabs");
  r.innerHTML=categories.map(c=>'<button class="tab '+(state.category===c?"active":"")+'" data-c="'+esc(c)+'">'+esc(c)+'</button>').join("");
  r.querySelectorAll(".tab").forEach(b=>b.onclick=()=>{
    state.category=b.dataset.c;state.savedOnly=false;setNav("news");tabs();stories();
  });
}
function meaningfulSummary(s){
  let x=(s.summary||"").trim();
  if(x&&x.length>45&&!x.toLowerCase().includes("google news"))return x;
  const rs=(s.reasons||[]).filter(Boolean);
  if(rs.length)return "Selected because this development shows "+rs.join(", ")+".";
  return "A significant development selected from trusted reporting.";
}
function mediaHtml(s){
  if(!s.image)return "";
  return '<div class="card-media has-image"><img src="'+esc(s.image)+'" alt="" loading="lazy" referrerpolicy="no-referrer"><div class="card-media-overlay"></div><div class="card-overlay-row"><div class="badges"><span class="badge '+esc(s.importance)+'">'+esc(s.importance)+'</span><span class="badge category">'+esc(s.category)+'</span>'+(s.updated?'<span class="badge Updated">Updated</span>':'')+'</div><span class="age">'+rel(s.published_at)+'</span></div></div>';
}
function noMediaTop(s){
  if(s.image)return "";
  return '<div class="card-no-media"><div class="card-top"><div class="badges"><span class="badge '+esc(s.importance)+'">'+esc(s.importance)+'</span><span class="badge category">'+esc(s.category)+'</span>'+(s.updated?'<span class="badge Updated">Updated</span>':'')+'</div><span class="age">'+rel(s.published_at)+'</span></div></div>';
}
function contextHtml(s){
  const context=s.context||{},reports=Array.isArray(context.earlier_reporting)?context.earlier_reporting:[];
  if(!reports.length&&!s.updated&&!["Major","Critical"].includes(s.importance))return "";
  const safeUrl=u=>{try{const x=new URL(u);return ["https:","http:"].includes(x.protocol)?esc(x.href):""}catch(e){return ""}};
  const dateLabel=d=>{const x=new Date(d);return Number.isNaN(x.getTime())?"Date unavailable":x.toLocaleDateString("en-GB",{day:"numeric",month:"short",year:"numeric",timeZone:"UTC"})};
  const items=reports.filter(x=>safeUrl(x.url)).map(x=>'<li><time datetime="'+esc(x.published_at)+'">'+esc(dateLabel(x.published_at))+' · '+esc(x.source)+'</time><a href="'+safeUrl(x.url)+'" target="_blank" rel="noopener noreferrer">'+esc(x.title)+'</a></li>').join("");
  const lead=safeUrl(s.lead_url);
  return '<details class="story-context"><summary>Understand the story</summary><div class="context-body">'+
    '<h4>Latest reported development</h4><p>'+ (lead?'<a href="'+lead+'" target="_blank" rel="noopener noreferrer">'+esc(s.title)+'</a>':esc(s.title))+'</p>'+
    '<h4>Earlier reporting &amp; background</h4>'+
    (items?'<ol class="context-timeline">'+items+'</ol>':'<p>Earlier reporting has not been matched reliably yet. Use the background search below to explore the story.</p>')+
    '<p class="context-note">Dates refer to publication, not necessarily when events occurred. Related headlines are not a verified explanation of causes or a complete event timeline.</p>'+
    '<a class="context-search" target="_blank" rel="noopener noreferrer" href="https://news.google.com/search?q='+esc(encodeURIComponent((context.search_query||s.title)+" when:30d"))+'">Search for further background reporting ↗</a>'+
    '</div></details>';
}
function storyCard(s){
  const preview=s.sources.slice(0,3).map(x=>esc(x.name)+(x.paywalled?" 🔒":"")).join('<span class="dot">·</span>');
  const links=s.sources.map(x=>'<a class="source-link" href="'+esc(x.url)+'" target="_blank" rel="noopener">'+esc(x.name)+(x.paywalled?" 🔒":"")+'</a>').join("");
  const tags=(s.reasons||[]).slice(0,3).map(x=>'<span class="reason">'+esc(x)+'</span>').join("");
  const savedClass=saved.has(s.id)?" saved":"";
  return '<article class="card '+esc(s.importance)+'" data-id="'+esc(s.id)+'">'+
    mediaHtml(s)+noMediaTop(s)+
    '<div class="card-body"><div class="story-rule"><span class="accent-line"></span><div><h3><a href="'+esc(s.lead_url)+'" target="_blank" rel="noopener">'+esc(s.title)+'</a></h3><p class="summary">'+esc(meaningfulSummary(s))+'</p></div></div>'+
    '<div class="meta-row"><div class="source-preview">'+preview+'</div><button class="coverage-btn" data-coverage="'+esc(s.id)+'">Coverage · '+s.source_count+' source'+(s.source_count===1?"":"s")+'</button></div>'+
    '<div class="tag-row"><div class="tags">'+tags+'</div><div class="card-actions"><button class="save-btn'+savedClass+'" data-save="'+esc(s.id)+'" aria-label="Save story">♡</button><button class="share-btn" data-share="'+esc(s.id)+'" aria-label="Share story">↗</button></div></div>'+
    '<div class="coverage-panel" id="coverage-'+esc(s.id)+'"><div class="coverage-links">'+links+'</div></div>'+
    contextHtml(s)+
    '</div></article>';
}
function updateStats(){
  if(!state.data)return;
  const current=state.data.stories.filter(s=>timeOk(s));
  document.getElementById("criticalCount").textContent=current.filter(s=>s.importance==="Critical").length;
  document.getElementById("majorCount").textContent=current.filter(s=>s.importance==="Major").length;
  document.getElementById("localCount").textContent=current.filter(s=>s.category==="Stavanger/Rogaland").length;
  document.getElementById("watchCount").textContent=(state.data.watchlist||[]).length;
}
function bindCards(){
  document.querySelectorAll("[data-coverage]").forEach(b=>b.onclick=()=>{
    const p=document.getElementById("coverage-"+b.dataset.coverage);
    p.classList.toggle("open");
    b.textContent=(p.classList.contains("open")?"Hide coverage":"Coverage · "+(state.data.stories.find(s=>s.id===b.dataset.coverage)?.source_count||0)+" sources");
  });
  document.querySelectorAll("[data-save]").forEach(b=>b.onclick=()=>{
    const id=b.dataset.save;
    if(saved.has(id)){saved.delete(id);b.classList.remove("saved")}else{saved.add(id);b.classList.add("saved")}
    localStorage.setItem("ai-news-saved",JSON.stringify([...saved]));
    if(state.savedOnly)stories();
  });
  document.querySelectorAll("[data-share]").forEach(b=>b.onclick=async()=>{
    const s=state.data.stories.find(x=>x.id===b.dataset.share);if(!s)return;
    if(navigator.share){try{await navigator.share({title:s.title,url:s.lead_url})}catch(e){}}
    else{navigator.clipboard?.writeText(s.lead_url);b.textContent="✓";setTimeout(()=>b.textContent="↗",1200)}
  });
}
function stories(){
  if(!state.data)return;
  updateStats();
  const arr=state.data.stories.filter(ok);
  document.getElementById("storyCount").textContent=arr.length;
  document.getElementById("feedTitle").textContent=state.savedOnly?"Saved stories":state.category==="Top"?"Top developments":state.category;
  const r=document.getElementById("stories");
  if(!arr.length){r.innerHTML='<div class="empty">'+(state.savedOnly?"No saved stories match these filters.":"No stories match these filters.")+'</div>';return}
  r.innerHTML=arr.map(storyCard).join("");
  bindCards();
}
function watch(){
  const r=document.getElementById("watchlistItems"),a=state.data&&state.data.watchlist||[];
  document.getElementById("watchCount").textContent=a.length;
  if(!a.length){r.innerHTML='<div class="empty">Automatic upcoming-event discovery is the next feature to add.</div>';return}
  r.innerHTML=a.map(x=>'<article class="watch-item"><time>'+esc(x.date)+'</time><h3>'+esc(x.title)+'</h3><p>'+esc(x.why||"")+'</p></article>').join("");
}
function setNav(action){
  document.querySelectorAll(".nav-item").forEach(x=>x.classList.toggle("active",x.dataset.action===action));
}
async function load(){
  document.getElementById("refreshBtn").disabled=true;
  try{
    const x=await fetch("data/news.json?t="+Date.now(),{cache:"no-store"});
    state.data=await x.json();
    document.getElementById("updatedText").textContent="Updated "+rel(state.data.generated_at);
    document.getElementById("modelMode").textContent=state.data.model_mode==="sentence-transformers"?"Semantic AI":"Fallback";
    stories();watch();
  }catch(e){
    document.getElementById("updatedText").textContent="Update unavailable";
    document.getElementById("stories").innerHTML='<div class="empty">Could not load news data.</div>';
  }finally{document.getElementById("refreshBtn").disabled=false}
}
document.getElementById("timeFilter").onchange=e=>{state.hours=+e.target.value;stories()};
document.getElementById("importanceFilter").onchange=e=>{state.importance=e.target.value;stories()};
document.getElementById("searchInput").oninput=e=>{state.query=e.target.value.trim();stories()};
document.getElementById("refreshBtn").onclick=load;
document.querySelectorAll(".summary-item[data-filter]").forEach(b=>b.onclick=()=>{state.importance=b.dataset.filter;document.getElementById("importanceFilter").value=state.importance;stories()});
document.querySelectorAll(".summary-item[data-category]").forEach(b=>b.onclick=()=>{state.category=b.dataset.category;state.savedOnly=false;tabs();stories()});
document.querySelectorAll(".summary-item[data-jump]").forEach(b=>b.onclick=()=>document.getElementById(b.dataset.jump)?.scrollIntoView({behavior:"smooth"}));
document.querySelectorAll(".nav-item").forEach(b=>b.onclick=()=>{
  const a=b.dataset.action;setNav(a);
  if(a==="news"){state.savedOnly=false;stories();document.getElementById("news").scrollIntoView({behavior:"smooth"})}
  if(a==="watchlist")document.getElementById("watchlist").scrollIntoView({behavior:"smooth"});
  if(a==="saved"){state.savedOnly=true;stories();document.getElementById("news").scrollIntoView({behavior:"smooth"})}
  if(a==="search"){document.getElementById("searchInput").scrollIntoView({behavior:"smooth",block:"center"});setTimeout(()=>document.getElementById("searchInput").focus(),350)}
});
tabs();load();
if("serviceWorker"in navigator)window.addEventListener("load",()=>navigator.serviceWorker.register("sw.js"));
