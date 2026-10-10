"""Build the map page (docs/index.html, served by GitHub Pages).

Split screen: the Open-Meteo model map (left) and the IQAir monitoring map (right).
A left sidebar lists past snapshots; clicking one redraws BOTH maps for that moment.
All data is embedded in the page, so it stays a single static file.
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


def load_iqair(iqair_dir: str | Path) -> pd.DataFrame:
    files = sorted(Path(iqair_dir).glob("*.csv"))
    if not files:
        return pd.DataFrame()
    return pd.concat((pd.read_csv(f) for f in files), ignore_index=True)


def build_iqair(df: pd.DataFrame) -> dict:
    """{'stations': [{city, state, lat, lon, h: [[time, aqi, main, temp, humidity], ...]}]}"""
    if df.empty:
        return {"stations": []}
    df = df.sort_values("observed_at")
    stations = []
    for (city, state), g in df.groupby(["iq_city", "iq_state"]):
        last = g.iloc[-1]
        hist = [
            [r.observed_at, round(r.us_aqi),
             None if pd.isna(r.main_pollutant) else str(r.main_pollutant),
             _num(r.temp_c), _num(r.humidity)]
            for r in g.itertuples() if not pd.isna(r.us_aqi)
        ]
        if hist:
            stations.append({"city": city, "state": state, "lat": float(last.lat),
                             "lon": float(last.lon), "h": hist})
    return {"stations": stations}


_CSS = """
<style>
#nav{position:fixed;top:0;bottom:0;left:0;width:230px;background:#fff;z-index:1000;
 border-right:1px solid #d0d0d0;overflow-y:auto;font:13px Arial,sans-serif;color:#222}
#nav h1{font-size:15px;margin:0;padding:12px 12px 8px}
#nav h2{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#777;
 margin:14px 12px 4px}
#nav button{display:flex;justify-content:space-between;align-items:center;width:100%;
 border:0;background:none;padding:6px 12px;font:inherit;cursor:pointer;text-align:left}
#nav button:hover{background:#f0f3f7}
#nav button.active{background:#e3eefc;font-weight:bold}
#nav .live{font-size:14px;padding:10px 12px;color:#0a7a2f}
#nav .chip{min-width:26px;text-align:center;border-radius:10px;padding:1px 6px;
 font-size:11px;font-weight:bold;border:1px solid #888}
#views{display:flex;gap:4px;padding:0 12px 6px}
#views button{justify-content:center;border:1px solid #bbb;border-radius:6px;padding:4px 0}
#views button.active{background:#0b5ed7;color:#fff;border-color:#0b5ed7}
#syncrow{padding:0 12px 6px;font-size:12px;color:#555}
#map2{position:fixed;z-index:0;top:0;bottom:0}
.maptag{background:#fff;padding:4px 8px;border-radius:6px;font:12px Arial;
 box-shadow:0 1px 4px rgba(0,0,0,.3)}
#stamp{position:fixed;bottom:8px;left:238px;z-index:9999;background:#fff;padding:6px 10px;
 font:12px Arial;border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.3)}
#navtoggle{display:none;position:fixed;top:10px;left:10px;z-index:1100;border:0;
 background:#fff;border-radius:6px;padding:6px 10px;font-size:18px;
 box-shadow:0 1px 4px rgba(0,0,0,.4)}
body.split .folium-map{left:230px!important;width:calc((100% - 230px)/2)!important}
body.split #map2{left:calc(230px + (100% - 230px)/2);right:0}
body.only1 .folium-map{left:230px!important;width:calc(100% - 230px)!important}
body.only1 #map2{display:none}
body.only2 .folium-map{display:none!important}
body.only2 #map2{left:230px;right:0}
@media(max-width:700px){
 body.split .folium-map{left:0!important;width:100%!important;height:50%!important}
 body.split #map2{left:0;right:0;top:50%}
 body.only1 .folium-map{left:0!important;width:100%!important}
 body.only2 #map2{left:0}
 #nav{transform:translateX(-100%);transition:transform .2s}
 #nav.open{transform:none}
 #navtoggle{display:block}
 #stamp{left:8px}
}
</style>
"""

_HTML = """
<button id="navtoggle" aria-label="Toggle menu">&#9776;</button>
<div id="nav">
 <h1>FECT Sri Lanka AQI</h1>
 <div id="views">
  <button data-mode="split" class="active">Split</button>
  <button data-mode="only1">Model</button>
  <button data-mode="only2">IQAir</button>
 </div>
 <div id="syncrow"><label><input type="checkbox" id="sync" checked> Sync zoom &amp; pan</label></div>
 <button class="live" id="livebtn">&#9679; Live map</button>
 <div id="navlist"></div>
</div>
<div id="map2"></div>
<div id="stamp"></div>
"""

_JS = """
<script>
(function(){
const LIVE=__LIVE__, SNAPS=__SNAPS__, BANDS=__BANDS__, IQ=__IQ__, STAMP="__STAMP__";
const POLL={p2:"PM2.5",p1:"PM10",o3:"Ozone",n2:"NO&#8322;",s2:"SO&#8322;",co:"CO"};
function cat(a){for(const b of BANDS){if(a<=b[0])return b;}
 return [null,"Hazardous","#7e0023","Emergency conditions."];}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function fmt(t){return t.replace("T"," ");}
function dot(aqi,radius){
 const c=cat(aqi), text=aqi>200?"#fff":"#000";
 return "<div style='background:"+c[2]+";color:"+text+";width:32px;height:32px;border-radius:"+
  radius+";text-align:center;line-height:32px;font-weight:800;border:1px solid #555'>"+aqi+"</div>";}
function icon(aqi,radius){
 return L.divIcon({className:"",iconSize:[32,32],iconAnchor:[16,16],html:dot(aqi,radius)});}
function tag(m,html){
 const c=L.control({position:"topright"});
 c.onAdd=function(){const d=L.DomUtil.create("div","maptag");d.innerHTML=html;return d;};
 c.addTo(m);}
window.addEventListener("load",function(){
 const map=window["__MAP__"];
 const map2=L.map("map2",{center:[7.8731,80.7718],zoom:8});
 L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  {attribution:"&copy; OpenStreetMap contributors",maxZoom:19}).addTo(map2);
 tag(map,"Model estimates &middot; Open-Meteo");
 tag(map2,IQ.stations.length?"Monitoring data &middot; IQAir":"IQAir: no data yet");
 const layer=L.layerGroup().addTo(map), layer2=L.layerGroup().addTo(map2);
 const stamp=document.getElementById("stamp"), nav=document.getElementById("nav");
 const buttons=[];

 function draw(rows){
  layer.clearLayers();
  rows.forEach(function(r){
   const aqi=r[4], c=cat(aqi);
   const tip="<div style='font-family:Arial;width:220px'><b>"+esc(r[0])+"</b> <small>("+esc(r[1])+
    ")</small><br><span style='font-size:28px;font-weight:bold'>"+aqi+"</span> US AQI<br>"+
    esc(c[1])+"<br><small>"+esc(c[3])+"</small><br><small>PM2.5: "+(r[5]==null?"n/a":r[5])+
    " &micro;g/m&sup3; &middot; "+(r[6]==null?"n/a":r[6])+"&deg;C<br>Model estimate</small></div>";
   L.marker([r[2],r[3]],{icon:icon(aqi,"50%")}).bindTooltip(tip).addTo(layer);
  });
 }
 // IQAir: latest reading at or before time t (null = newest); past snapshots skip >6h old
 function drawIQ(t){
  layer2.clearLayers();
  IQ.stations.forEach(function(s){
   let e=null;
   for(const h of s.h){if(t===null||h[0]<=t)e=h;}
   if(!e)return;
   if(t!==null&&new Date(t)-new Date(e[0])>6*3600*1000)return;
   const c=cat(e[1]);
   const tip="<div style='font-family:Arial;width:220px'><b>"+esc(s.city)+"</b> <small>("+
    esc(s.state)+")</small><br><span style='font-size:28px;font-weight:bold'>"+e[1]+
    "</span> US AQI<br>"+esc(c[1])+"<br><small>Main pollutant: "+
    (e[2]?(POLL[e[2]]||esc(e[2])):"n/a")+" &middot; "+(e[3]==null?"n/a":e[3])+"&deg;C &middot; "+
    (e[4]==null?"n/a":e[4])+"%<br>Observed "+esc(fmt(e[0]))+" &middot; IQAir</small></div>";
   L.marker([s.lat,s.lon],{icon:icon(e[1],"8px")}).bindTooltip(tip).addTo(layer2);
  });
 }
 function select(btn,rows,t,label){
  buttons.forEach(function(b){b.classList.remove("active");});
  btn.classList.add("active");
  draw(rows);drawIQ(t);
  stamp.innerHTML=label;
  nav.classList.remove("open");
 }
 function showLive(){
  select(document.getElementById("livebtn"),LIVE.d,null,
   "FECT Sri Lanka AQI &middot; updated "+STAMP+" (SLST) &middot; Data: "+
   "<a href='https://open-meteo.com/'>Open-Meteo</a> (CC BY 4.0) &middot; "+
   "<a href='https://www.iqair.com/'>IQAir</a>");
 }
 const live=document.getElementById("livebtn");
 buttons.push(live);
 live.addEventListener("click",showLive);

 const list=document.getElementById("navlist");
 const days={};
 SNAPS.slice().reverse().forEach(function(s){(days[s.t.slice(0,10)]=days[s.t.slice(0,10)]||[]).push(s);});
 Object.keys(days).forEach(function(day){
  const h=document.createElement("h2");
  h.textContent=new Date(day+"T00:00:00").toLocaleDateString("en-GB",
   {weekday:"short",day:"numeric",month:"short"});
  list.appendChild(h);
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
   buttons.push(b); list.appendChild(b);
  });
 });

 // view switch: split / model only / IQAir only
 function setMode(mode){
  document.body.classList.remove("split","only1","only2");
  document.body.classList.add(mode);
  document.querySelectorAll("#views button").forEach(function(b){
   b.classList.toggle("active",b.dataset.mode===mode);});
  setTimeout(function(){map.invalidateSize();map2.invalidateSize();},60);
 }
 document.querySelectorAll("#views button").forEach(function(b){
  b.addEventListener("click",function(){setMode(b.dataset.mode);});});

 // keep both maps on the same view
 const sync=document.getElementById("sync");
 let busy=false;
 function link(a,b){
  a.on("move",function(){
   if(busy||!sync.checked||!document.body.classList.contains("split"))return;
   busy=true;b.setView(a.getCenter(),a.getZoom(),{animate:false});busy=false;});}
 link(map,map2);link(map2,map);

 document.getElementById("navtoggle").addEventListener("click",function(){
  nav.classList.toggle("open");});
 document.body.classList.add("split");
 setTimeout(function(){map.invalidateSize();map2.invalidateSize();},60);
 showLive();
});
})();
</script>
"""


def build_map(data_dir="data", out_file="docs/index.html", iqair_dir=None) -> Path:
    df = load_all(data_dir)
    latest = latest_rows(data_dir)
    snaps = build_snapshots(df)
    live = {"t": str(latest["observed_at"].max()), "d": _rows(latest)}
    iq = build_iqair(load_iqair(iqair_dir or Path(data_dir) / "iqair"))

    m = folium.Map(location=[7.8731, 80.7718], zoom_start=8)
    stamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")

    def dump(obj):
        return json.dumps(obj, separators=(",", ":")).replace("</", "<\\/")

    js = (_JS.replace("__LIVE__", dump(live))
             .replace("__SNAPS__", dump(snaps))
             .replace("__BANDS__", dump(BANDS))
             .replace("__IQ__", dump(iq))
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
