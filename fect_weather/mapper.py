"""Build the map page (docs/index.html, served by GitHub Pages).

Four maps in a 2x2 grid: Open-Meteo model + IQAir city data (top), OpenWeather model +
AQICN stations (bottom). A left sidebar lists past snapshots; clicking one redraws ALL maps
for that moment. All data is embedded in the page, so it stays a single static file.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import folium
import pandas as pd

from .aqi import BANDS
from .collector import TZ


def load_all(data_dir: str | Path) -> pd.DataFrame:
    files = sorted(Path(data_dir).glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV files in {data_dir}")
    return pd.concat((pd.read_csv(f) for f in files), ignore_index=True)


def latest_rows(data_dir: str | Path) -> pd.DataFrame:
    df = load_all(data_dir).sort_values("observed_at")
    return df.groupby("city", as_index=False).tail(1)


def _num(v):
    return None if pd.isna(v) else float(v)


def _rows(df: pd.DataFrame) -> list[list]:
    """[city, province, lat, lon, aqi, pm2_5, temp] for every row that has an AQI."""
    return [
        [r.city, r.province, float(r.lat), float(r.lon), round(r.us_aqi),
         _num(r.pm2_5), _num(r.temperature_2m)]
        for r in df.itertuples() if not pd.isna(r.us_aqi)
    ]


def build_snapshots(df: pd.DataFrame) -> list[dict]:
    """One snapshot per observation time, oldest first."""
    out = []
    for t, g in df.sort_values("observed_at").groupby("observed_at"):
        rows = _rows(g)
        if rows:
            out.append({"t": t, "avg": round(sum(r[4] for r in rows) / len(rows)), "d": rows})
    return out


def _load_dir(d: str | Path) -> pd.DataFrame:
    files = sorted(Path(d).glob("*.csv"))
    if not files:
        return pd.DataFrame()
    return pd.concat((pd.read_csv(f) for f in files), ignore_index=True)


def _stations(df: pd.DataFrame, key: str, name, sub, hist) -> dict:
    """{'stations': [{name, sub, lat, lon, h: [[time, aqi, ...extras], ...]}]}"""
    if df.empty:
        return {"stations": []}
    df = df.sort_values("observed_at")
    out = []
    for _, g in df.groupby(key):
        last = g.iloc[-1]
        h = [hist(r) for r in g.itertuples() if not pd.isna(r.us_aqi)]
        if h:
            out.append({"name": name(last), "sub": sub(last), "lat": float(last.lat),
                        "lon": float(last.lon), "h": h})
    return {"stations": out}


def _txt(v):
    return None if pd.isna(v) else str(v)


def build_iqair(df: pd.DataFrame) -> dict:
    """h: [time, aqi, main pollutant, temp, humidity]"""
    if df.empty:
        return {"stations": []}
    df = df.assign(_k=df["iq_city"].astype(str) + "|" + df["iq_state"].astype(str))
    return _stations(df, "_k", lambda r: r.iq_city, lambda r: r.iq_state,
                     lambda r: [r.observed_at, round(r.us_aqi), _txt(r.main_pollutant),
                                _num(r.temp_c), _num(r.humidity)])


def build_owm(df: pd.DataFrame) -> dict:
    """h: [time, us aqi, pm2.5, pm10, OpenWeather 1-5 index]"""
    return _stations(df, "city", lambda r: r.city, lambda r: r.province,
                     lambda r: [r.observed_at, round(r.us_aqi), _num(r.pm2_5), _num(r.pm10),
                                _num(r.owm_aqi)]) if not df.empty else {"stations": []}


def build_waqi(df: pd.DataFrame) -> dict:
    """h: [time, aqi]"""
    return _stations(df, "uid", lambda r: r.station, lambda r: "",
                     lambda r: [r.observed_at, round(r.us_aqi)]) if not df.empty \
        else {"stations": []}


_CSS = """
<style>
#nav{position:fixed;top:0;bottom:0;left:0;width:230px;z-index:1000;overflow:hidden;
 display:flex;flex-direction:column;
 background:linear-gradient(180deg,#0f172a 0%,#17233b 100%);color:#e2e8f0;
 font:13px/1.4 "Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif;
 box-shadow:3px 0 14px rgba(0,0,0,.35);scrollbar-width:thin;
 scrollbar-color:#3b4a66 transparent}
#navlist::-webkit-scrollbar{width:6px}
#navlist::-webkit-scrollbar-thumb{background:#3b4a66;border-radius:3px}
#nav h1{display:flex;align-items:center;gap:9px;margin:0;padding:16px 14px 12px;
 font-size:15px;font-weight:700;letter-spacing:.02em;color:#fff;
 border-bottom:1px solid rgba(255,255,255,.08)}
#nav h1::before{content:"";flex:none;width:14px;height:14px;border-radius:50%;
 background:conic-gradient(#00e400,#ffff00,#ff7e00,#ff0000,#8f3f97,#00e400);
 box-shadow:0 0 8px rgba(255,255,255,.35)}
#nav button{display:flex;justify-content:space-between;align-items:center;width:100%;
 border:0;background:none;color:inherit;padding:7px 14px;font:inherit;cursor:pointer;
 text-align:left;transition:background .15s,transform .15s,box-shadow .15s}
#views{display:flex;flex-wrap:wrap;gap:5px;margin:12px 12px 8px;padding:5px;
 background:rgba(255,255,255,.06);border-radius:12px}
#views button{width:auto;flex:1 1 30%;justify-content:center;padding:6px 2px;
 border-radius:8px;font-size:12px;font-weight:600;color:#b6c2dc}
#views button:hover{background:rgba(255,255,255,.1);color:#fff}
#views button.active{background:linear-gradient(135deg,#3b82f6,#6366f1);color:#fff;
 box-shadow:0 2px 8px rgba(59,130,246,.45)}
#syncrow{padding:0 14px 10px;font-size:12px;color:#94a3c4}
#syncrow input{accent-color:#3b82f6;vertical-align:-2px;margin-right:4px}
#nav .live{width:calc(100% - 24px);margin:2px 12px 6px;padding:11px 14px;border-radius:12px;
 font-size:14px;font-weight:700;color:#4ade80;background:rgba(34,197,94,.1);
 border:1px solid rgba(74,222,128,.35);animation:livepulse 2.4s ease-in-out infinite}
#nav .live:hover{background:rgba(34,197,94,.2)}
#nav .live.active{color:#052e16;background:linear-gradient(135deg,#4ade80,#22c55e);
 border-color:transparent}
@keyframes livepulse{0%,100%{box-shadow:0 0 0 0 rgba(74,222,128,.35)}
 50%{box-shadow:0 0 0 6px rgba(74,222,128,0)}}
#navlist{flex:1 1 auto;min-height:0;overflow-y:auto;margin:0 6px 8px 16px;padding:0 6px 0 14px;
 background:linear-gradient(rgba(255,255,255,.12),rgba(255,255,255,.12)) 7px 0/2px 100% no-repeat;
 background-attachment:local;scrollbar-width:thin;scrollbar-color:#3b4a66 transparent}
#navlist details{margin:6px 0 4px}
#navlist summary{display:flex;align-items:center;gap:8px;list-style:none;cursor:pointer;
 margin-left:4px;padding:7px 10px 7px 12px;border-radius:8px;font-size:11px;font-weight:700;
 letter-spacing:.08em;text-transform:uppercase;color:#9fb0d0;
 transition:background .15s,color .15s}
#navlist summary::-webkit-details-marker{display:none}
#navlist summary::before{content:"\\25B8";font-size:12px;transition:transform .15s}
#navlist details[open]>summary::before{transform:rotate(90deg)}
#navlist summary:hover{background:rgba(255,255,255,.08);color:#fff}
#navlist summary .cnt{margin-left:auto;min-width:18px;text-align:center;border-radius:999px;
 padding:0 6px;font-size:10px;background:rgba(255,255,255,.1);color:#cbd5e1}
#navlist button{position:relative;width:calc(100% - 4px);margin:2px 0 2px 4px;
 padding:6px 10px 6px 14px;border-radius:8px;color:#cbd5e1}
#navlist button::before{content:"";position:absolute;left:-16px;top:50%;width:8px;height:8px;
 margin-top:-4px;border-radius:50%;background:#475569;border:2px solid #17233b;
 transition:background .15s,transform .15s}
#navlist button:hover{background:rgba(255,255,255,.08);color:#fff;transform:translateX(2px)}
#navlist button:hover::before{background:#94a3b8}
#navlist button.active{background:rgba(59,130,246,.22);color:#fff;font-weight:700;
 box-shadow:inset 3px 0 0 #60a5fa}
#navlist button.active::before{background:#60a5fa;transform:scale(1.4);
 box-shadow:0 0 8px #60a5fa}
#navfoot{flex:none;padding:10px 14px 12px;font-size:11px;line-height:1.5;color:#8fa0c2;
 border-top:1px solid rgba(255,255,255,.08);background:rgba(0,0,0,.18)}
#navfoot a{color:#93c5fd;text-decoration:none}
#navfoot a:hover{text-decoration:underline}
#nav .chip{min-width:28px;text-align:center;border-radius:999px;padding:1px 7px;
 font-size:11px;font-weight:700;border:1px solid rgba(0,0,0,.25);
 box-shadow:0 1px 3px rgba(0,0,0,.35)}
#map2,#map3,#map4{position:fixed;z-index:0;box-sizing:border-box;border:1px solid #777}
.folium-map{box-sizing:border-box;border:1px solid #777}
.maptag{background:#fff;padding:4px 8px;border-radius:6px;font:12px Arial;
 box-shadow:0 1px 4px rgba(0,0,0,.3)}
#stamp{position:fixed;bottom:8px;left:238px;z-index:9999;background:#fff;padding:6px 10px;
 font:12px Arial;border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.3);max-width:420px}
#navtoggle{display:none;position:fixed;top:10px;left:10px;z-index:1100;border:0;
 background:#fff;border-radius:6px;padding:6px 10px;font-size:18px;
 box-shadow:0 1px 4px rgba(0,0,0,.4)}
/* all: 2 x 2 grid */
body.all .folium-map{left:230px!important;width:calc((100% - 230px)/2)!important;height:50%!important}
body.all #map2{left:calc(230px + (100% - 230px)/2);right:0;top:0;bottom:50%}
body.all #map3{left:230px;width:calc((100% - 230px)/2);top:50%;bottom:0}
body.all #map4{left:calc(230px + (100% - 230px)/2);right:0;top:50%;bottom:0}
/* one map full size */
body.m1 .folium-map{left:230px!important;width:calc(100% - 230px)!important;height:100%!important}
body.m1 #map2,body.m1 #map3,body.m1 #map4{display:none}
body.m2 .folium-map,body.m2 #map3,body.m2 #map4{display:none!important}
body.m2 #map2{left:230px;right:0;top:0;bottom:0}
body.m3 .folium-map,body.m3 #map2,body.m3 #map4{display:none!important}
body.m3 #map3{left:230px;right:0;top:0;bottom:0}
body.m4 .folium-map,body.m4 #map2,body.m4 #map3{display:none!important}
body.m4 #map4{left:230px;right:0;top:0;bottom:0}
@media(max-width:700px){
 #views [data-mode=all]{display:none}
 body.m1 .folium-map{left:0!important;width:100%!important}
 body.m2 #map2,body.m3 #map3,body.m4 #map4{left:0}
 #nav{transform:translateX(-100%);transition:transform .2s}
 #nav.open{transform:none}
 #navtoggle{display:block}
 #stamp{left:8px;max-width:calc(100% - 16px)}
}
</style>
"""

_HTML = """
<button id="navtoggle" aria-label="Toggle menu">&#9776;</button>
<div id="nav">
 <h1>FECT Sri Lanka AQI</h1>
 <div id="views">
  <button data-mode="all" class="active">All 4</button>
  <button data-mode="m1">Model</button>
  <button data-mode="m2">IQAir</button>
  <button data-mode="m3">OpenWeather</button>
  <button data-mode="m4">AQICN</button>
 </div>
 <div id="syncrow"><label><input type="checkbox" id="sync" checked> Sync zoom &amp; pan</label></div>
 <button class="live" id="livebtn">&#9679; Live maps</button>
 <div id="navlist"></div>
 <div id="navfoot"></div>
</div>
<div id="map2"></div><div id="map3"></div><div id="map4"></div>
<div id="stamp"></div>
"""

_JS = """
<script>
(function(){
const LIVE=__LIVE__, SNAPS=__SNAPS__, BANDS=__BANDS__, STAMP="__STAMP__";
const IQ=__IQ__, OWM=__OWM__, WAQI=__WAQI__;
const POLL={p2:"PM2.5",p1:"PM10",o3:"Ozone",n2:"NO&#8322;",s2:"SO&#8322;",co:"CO"};
const CENTER=[7.8731,80.7718];
function cat(a){for(const b of BANDS){if(a<=b[0])return b;}
 return [null,"Hazardous","#7e0023","Emergency conditions."];}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function fmt(t){return t.replace("T"," ");}
function n(v,u){return v==null?"n/a":v+(u||"");}
function icon(aqi,radius){
 const c=cat(aqi), text=aqi>200?"#fff":"#000";
 return L.divIcon({className:"",iconSize:[32,32],iconAnchor:[16,16],
  html:"<div style='background:"+c[2]+";color:"+text+";width:32px;height:32px;border-radius:"+
  radius+";text-align:center;line-height:32px;font-weight:800;border:1px solid #555'>"+aqi+"</div>"});}
function card(title,sub,aqi,body){
 const c=cat(aqi);
 return "<div style='font-family:Arial;width:230px'><b>"+esc(title)+"</b>"+
  (sub?" <small>("+esc(sub)+")</small>":"")+"<br><span style='font-size:28px;font-weight:bold'>"+aqi+
  "</span> US AQI<br>"+esc(c[1])+"<br><small>"+body+"</small></div>";}
function tag(m,html){
 const c=L.control({position:"topright"});
 c.onAdd=function(){const d=L.DomUtil.create("div","maptag");d.innerHTML=html;return d;};
 c.addTo(m);}
function osm(m){L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
 {attribution:"&copy; OpenStreetMap contributors",maxZoom:19}).addTo(m);}

const TIPS={
 iq:function(s,e){return card(s.name,s.sub,e[1],"Main pollutant: "+(e[2]?(POLL[e[2]]||esc(e[2])):"n/a")+
  " &middot; "+n(e[3],"&deg;C")+" &middot; "+n(e[4],"%")+"<br>Observed "+esc(fmt(e[0]))+" &middot; IQAir city data");},
 owm:function(s,e){return card(s.name,s.sub,e[1],"PM2.5: "+n(e[2]," &micro;g/m&sup3;")+" &middot; PM10: "+
  n(e[3]," &micro;g/m&sup3;")+"<br>AQI from PM2.5/PM10 &middot; OpenWeather index "+n(e[4])+
  "<br>Observed "+esc(fmt(e[0]))+" &middot; modelled");},
 waqi:function(s,e){return card(s.name,"",e[1],"Observed "+esc(fmt(e[0]))+" &middot; AQICN station");}
};

window.addEventListener("load",function(){
 const map=window["__MAP__"];
 const map2=L.map("map2",{center:CENTER,zoom:7}), map3=L.map("map3",{center:CENTER,zoom:7}),
  map4=L.map("map4",{center:CENTER,zoom:7});
 [map2,map3,map4].forEach(osm);
 const maps=[map,map2,map3,map4];
 tag(map,"Model estimates &middot; Open-Meteo");
 tag(map2,IQ.stations.length?"City data &middot; IQAir":"IQAir: no data yet");
 tag(map3,OWM.stations.length?"Model data &middot; OpenWeather":"OpenWeather: no data yet");
 tag(map4,WAQI.stations.length?"Stations &middot; AQICN":"AQICN: no data yet");
 const layer=L.layerGroup().addTo(map);
 const SRC=[
  {layer:L.layerGroup().addTo(map2),data:IQ,tip:TIPS.iq,radius:"8px"},
  {layer:L.layerGroup().addTo(map3),data:OWM,tip:TIPS.owm,radius:"6px 16px"},
  {layer:L.layerGroup().addTo(map4),data:WAQI,tip:TIPS.waqi,radius:"50%"}];
 const stamp=document.getElementById("stamp"), nav=document.getElementById("nav");
 const buttons=[];

 function draw(rows){
  layer.clearLayers();
  rows.forEach(function(r){
   L.marker([r[2],r[3]],{icon:icon(r[4],"50%")}).bindTooltip(card(r[0],r[1],r[4],
    "PM2.5: "+n(r[5]," &micro;g/m&sup3;")+" &middot; "+n(r[6],"&deg;C")+"<br>Model estimate")).addTo(layer);
  });
 }
 // latest reading at or before time t (null = newest); past snapshots skip readings >6h old
 function drawStations(src,t){
  src.layer.clearLayers();
  src.data.stations.forEach(function(s){
   let e=null;
   for(const h of s.h){if(t===null||h[0]<=t)e=h;}
   if(!e)return;
   if(t!==null&&new Date(t)-new Date(e[0])>6*3600*1000)return;
   L.marker([s.lat,s.lon],{icon:icon(e[1],src.radius)}).bindTooltip(src.tip(s,e)).addTo(src.layer);
  });
 }
 function select(btn,rows,t,label){
  buttons.forEach(function(b){b.classList.remove("active");});
  btn.classList.add("active");
  draw(rows);
  SRC.forEach(function(src){drawStations(src,t);});
  stamp.innerHTML=label;
  stamp.style.display=label?"block":"none";
  nav.classList.remove("open");
 }
 function showLive(){select(document.getElementById("livebtn"),LIVE.d,null,"");}
 document.getElementById("navfoot").innerHTML=
  "FECT Sri Lanka AQI &middot; updated "+STAMP+" (SLST) &middot; Data: "+
  "<a href='https://open-meteo.com/'>Open-Meteo</a> (CC BY 4.0), "+
  "<a href='https://www.iqair.com/'>IQAir</a>, "+
  "<a href='https://openweathermap.org/'>OpenWeather</a>, "+
  "<a href='https://aqicn.org/'>World Air Quality Index project</a>";
 const live=document.getElementById("livebtn");
 buttons.push(live);
 live.addEventListener("click",showLive);

 const list=document.getElementById("navlist");
 const days={};
 SNAPS.slice().reverse().forEach(function(s){(days[s.t.slice(0,10)]=days[s.t.slice(0,10)]||[]).push(s);});
 Object.keys(days).forEach(function(day,i){
  const det=document.createElement("details");
  det.open=(i===0);
  const sum=document.createElement("summary");
  const name=document.createElement("span");
  name.textContent=new Date(day+"T00:00:00").toLocaleDateString("en-GB",
   {weekday:"short",day:"numeric",month:"short"});
  const cnt=document.createElement("span");
  cnt.className="cnt"; cnt.textContent=days[day].length;
  sum.appendChild(name); sum.appendChild(cnt); det.appendChild(sum);
  list.appendChild(det);
  days[day].forEach(function(s){
   const b=document.createElement("button");
   const chip=document.createElement("span");
   const c=cat(s.avg);
   chip.className="chip"; chip.textContent=s.avg; chip.style.background=c[2];
   chip.style.color=s.avg>200?"#fff":"#000";
   const t=document.createElement("span"); t.textContent=s.t.slice(11,16);
   b.appendChild(t); b.appendChild(chip);
   b.title="Average US AQI across cities (model)";
   b.addEventListener("click",function(){
    select(b,s.d,s.t,"Past snapshot &middot; "+esc(fmt(s.t))+" (SLST) &middot; "+
     "<a href='#' id='backlive'>Back to live</a>");
    document.getElementById("backlive").addEventListener("click",function(e){
     e.preventDefault();showLive();});
   });
   buttons.push(b); det.appendChild(b);
  });
 });

 // view switch: all four / one map full size
 function setMode(mode){
  document.body.classList.remove("all","m1","m2","m3","m4");
  document.body.classList.add(mode);
  document.querySelectorAll("#views button").forEach(function(b){
   b.classList.toggle("active",b.dataset.mode===mode);});
  setTimeout(function(){
   maps.forEach(function(m){m.invalidateSize();});
   maps.forEach(function(m){m.setView(CENTER,mode==="all"?7:8,{animate:false});});
  },60);
 }
 document.querySelectorAll("#views button").forEach(function(b){
  b.addEventListener("click",function(){setMode(b.dataset.mode);});});

 // keep the maps on the same view
 const sync=document.getElementById("sync");
 let busy=false;
 maps.forEach(function(a){
  a.on("move",function(){
   if(busy||!sync.checked||!document.body.classList.contains("all"))return;
   busy=true;
   maps.forEach(function(b){if(b!==a)b.setView(a.getCenter(),a.getZoom(),{animate:false});});
   busy=false;});});

 document.getElementById("navtoggle").addEventListener("click",function(){
  nav.classList.toggle("open");});
 const small=window.matchMedia&&window.matchMedia("(max-width:700px)").matches;
 setMode(small?"m1":"all");
 showLive();
});
})();
</script>
"""


def build_map(data_dir="data", out_file="docs/index.html", iqair_dir=None, owm_dir=None,
              waqi_dir=None) -> Path:
    df = load_all(data_dir)
    latest = latest_rows(data_dir)
    snaps = build_snapshots(df)
    live = {"t": str(latest["observed_at"].max()), "d": _rows(latest)}
    base = Path(data_dir)
    iq = build_iqair(_load_dir(iqair_dir or base / "iqair"))
    owm = build_owm(_load_dir(owm_dir or base / "openweather"))
    waqi = build_waqi(_load_dir(waqi_dir or base / "waqi"))

    m = folium.Map(location=[7.8731, 80.7718], zoom_start=8)
    stamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")

    def dump(obj):
        return json.dumps(obj, separators=(",", ":")).replace("</", "<\\/")

    js = (_JS.replace("__LIVE__", dump(live))
             .replace("__SNAPS__", dump(snaps))
             .replace("__BANDS__", dump(BANDS))
             .replace("__IQ__", dump(iq))
             .replace("__OWM__", dump(owm))
             .replace("__WAQI__", dump(waqi))
             .replace("__STAMP__", stamp)
             .replace("__MAP__", m.get_name()))
    root = m.get_root()
    root.header.add_child(folium.Element(_CSS))
    root.html.add_child(folium.Element(_HTML))
    root.html.add_child(folium.Element(js))

    out = Path(out_file)
    out.parent.mkdir(parents=True, exist_ok=True)
    m.save(out)
    return out
