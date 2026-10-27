#ifndef WEBPAGE_H
#define WEBPAGE_H

// Self-contained dashboard: phones on the hotspot have no internet, so no CDNs.
const char INDEX_HTML[] PROGMEM = R"rawliteral(
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Shakthi Hazard Monitor</title>
<style>
:root{--bg:#eef3f6;--card:#fff;--text:#10202b;--muted:#5d7180;--line:#d9e3ea;--accent:#0f9488;
--safe:#16a34a;--warn:#d97706;--danger:#dc2626;--off:#94a3b8;--ring:#e3ebf0}
@media (prefers-color-scheme:dark){:root{--bg:#071118;--card:#0e1c26;--text:#e6f0f5;--muted:#86a0b0;--line:#1b2f3c;--ring:#173040}}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--text)}
.top{background:linear-gradient(135deg,#0f9488,#0e7490);color:#fff;padding:18px 16px 54px}
.top .row{display:flex;justify-content:space-between;align-items:center;max-width:980px;margin:0 auto}
.top h1{margin:0;font-size:1.15rem}.top small{opacity:.85;font-size:.78rem}
#link{background:#ffffff2e;padding:4px 11px;border-radius:999px;font-size:.72rem;font-weight:800}
#link.lost{background:var(--danger)}
main{max-width:980px;margin:-40px auto 0;padding:0 14px 20px}
#status{background:var(--card);border-radius:18px;padding:18px;display:flex;gap:16px;align-items:center;box-shadow:0 6px 24px #0b2a3a1f;border-left:8px solid var(--safe)}
#status.l1{border-left-color:var(--warn)}#status.l2{border-left-color:var(--danger);animation:shake .5s infinite}
#status.stale{border-left-color:var(--off);animation:none}
@keyframes shake{50%{box-shadow:0 0 0 4px #dc262655}}
.dot{width:54px;height:54px;border-radius:50%;flex:none;display:grid;place-items:center;font-size:1.6rem;background:#16a34a22}
.l1 .dot{background:#d9770622}.l2 .dot{background:#dc262622}
#sTitle{font-size:1.35rem;font-weight:800}#sText{color:var(--muted);font-size:.92rem;margin-top:2px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin-top:14px}
.card{background:var(--card);border-radius:16px;padding:14px;border:1px solid var(--line)}
.head{display:flex;justify-content:space-between;align-items:flex-start}
.name{font-weight:700}.sub{color:var(--muted);font-size:.74rem}
.chip{font-size:.66rem;font-weight:800;padding:3px 9px;border-radius:999px;color:#fff;background:var(--safe)}
.l1 .chip{background:var(--warn)}.l2 .chip{background:var(--danger)}.na .chip{background:var(--off)}
.ringbox{position:relative;width:132px;height:132px;margin:10px auto 2px}
.ringbox svg{transform:rotate(-90deg)}
.ringbox .v{position:absolute;inset:0;display:grid;place-items:center;text-align:center}
.ringbox b{font-size:1.75rem;font-variant-numeric:tabular-nums;display:block;line-height:1}
.ringbox span{color:var(--muted);font-size:.75rem}
.na .ringbox b{font-size:.95rem;color:var(--muted)}
.spark{width:100%;height:30px}
.spark polyline{fill:none;stroke:var(--accent);stroke-width:1.6;vector-effect:non-scaling-stroke}
.meta{display:flex;justify-content:space-between;color:var(--muted);font-size:.72rem}
footer{text-align:center;color:var(--muted);font-size:.72rem;padding:10px 0 20px}
</style>
</head>
<body>
<div class="top"><div class="row"><div><h1>Shakthi Multi-Hazard Monitor</h1><small id="uptime">Connecting…</small></div><span id="link">LIVE</span></div></div>
<main>
  <div id="status"><div class="dot" id="sIcon">⏳</div><div><div id="sTitle">Connecting</div><div id="sText">Waiting for sensor data…</div></div></div>
  <div class="grid" id="grid"></div>
  <footer>ESP32-C3 · open hotspot "Shakthi-Hazard-Monitor" · http://192.168.4.1</footer>
</main>
<script>
const CARDS=[
 {id:'mq5',name:'LPG / cooking gas',sub:'MQ-5',unit:'mV',max:5000},
 {id:'mq3',name:'Alcohol vapour',sub:'MQ-3',unit:'mV',max:5000},
 {id:'temp',name:'Temperature',sub:'DHT11',unit:'°C',max:60},
 {id:'hum',name:'Humidity',sub:'DHT11',unit:'%',max:100},
 {id:'soil',name:'Soil moisture',sub:'Soil probe',unit:'%',max:100},
 {id:'dist',name:'Water level / proximity',sub:'Ultrasonic',unit:'cm',max:150},
];
const LBL=['SAFE','WARNING','DANGER'],ICON=['✅','⚠️','🚨'],R=56,C=2*Math.PI*R,hist={};
const $=id=>document.getElementById(id);
$('grid').innerHTML=CARDS.map(c=>`<div class="card na" id="c_${c.id}"><div class="head"><div><div class="name">${c.name}</div><div class="sub">${c.sub}</div></div><span class="chip" id="s_${c.id}">—</span></div>
<div class="ringbox"><svg width="132" height="132"><circle cx="66" cy="66" r="${R}" stroke="var(--ring)" stroke-width="12" fill="none"/><circle id="r_${c.id}" cx="66" cy="66" r="${R}" stroke="var(--safe)" stroke-width="12" fill="none" stroke-linecap="round" stroke-dasharray="0 ${C}"/></svg>
<div class="v"><div><b id="v_${c.id}">—</b><span>${c.unit}</span></div></div></div>
<svg class="spark" viewBox="0 0 59 30" preserveAspectRatio="none"><polyline id="p_${c.id}"/></svg>
<div class="meta"><span id="m_${c.id}"></span><span id="t_${c.id}"></span></div></div>`).join('');
CARDS.forEach(c=>hist[c.id]=[]);

function card(id,val,lvl,frac,meta,thr,chip){
  const c=$('c_'+id),na=val===null||val===undefined;c.className='card '+(na?'na':'l'+lvl);
  $('s_'+id).textContent=chip||(na?'NO SENSOR':LBL[lvl]);
  $('v_'+id).textContent=na?'not detected':val;
  const r=$('r_'+id),f=na?0:Math.max(0,Math.min(1,frac));
  r.setAttribute('stroke-dasharray',`${f*C} ${C}`);r.setAttribute('stroke',lvl==2?'var(--danger)':lvl==1?'var(--warn)':'var(--safe)');
  $('m_'+id).textContent=meta||'';$('t_'+id).textContent=thr||'';
  const h=hist[id];h.push(na?null:Number(val));if(h.length>60)h.shift();
  const n=h.filter(x=>x!==null),mn=Math.min(...n),mx=Math.max(...n),sp=(mx-mn)||1;
  $('p_'+id).setAttribute('points',h.map((x,i)=>x===null?'':`${i+60-h.length},${28-(x-mn)/sp*26}`).filter(Boolean).join(' '));
}
let fails=0;
async function poll(){
  try{
    const d=await (await fetch('/api/data',{cache:'no-store'})).json();fails=0;
    $('link').className='';$('link').textContent='LIVE';
    const s=d.uptime;$('uptime').textContent=`Up ${String(Math.floor(s/3600)).padStart(2,'0')}:${String(Math.floor(s%3600/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')} · ${d.clients} device${d.clients==1?'':'s'} connected`;
    $('status').className=d.hazardLevel?'l'+d.hazardLevel:'';$('sIcon').textContent=d.warmup>0&&!d.hazardLevel?'⏳':ICON[d.hazardLevel];
    $('sTitle').textContent=d.warmup>0&&!d.hazardLevel?`Warming up · ${d.warmup}s`:LBL[d.hazardLevel];$('sText').textContent=d.hazards;
    const w=d.warmup>0?'WARMING':null;
    card('mq5',d.mq5.mv,d.mq5.level,d.mq5.mv/d.mq5.alarm,'Leak ≥ '+d.mq5.alarm+' mV','Warn '+d.mq5.warn,w);
    card('mq3',d.mq3.mv,d.mq3.level,d.mq3.mv/d.mq3.alarm,'Strong ≥ '+d.mq3.alarm+' mV','Warn '+d.mq3.warn,w);
    card('temp',d.dht.temp,d.dht.level,d.dht.temp/d.dht.alarm,'Fire ≥ '+d.dht.alarm+'°C','Warn '+d.dht.warn);
    card('hum',d.dht.hum,0,d.dht.hum/100,'Relative humidity','');
    card('soil',d.soil.pct,d.soil.level,d.soil.pct/100,d.soil.mv+' mV raw',`Dry <${d.soil.dryWarn} · Flood ≥${d.soil.wetAlarm}`);
    card('dist',d.dist.cm,d.dist.level,d.dist.cm===null?0:1-Math.min(d.dist.cm,150)/150,'Danger ≤ '+d.dist.alarm+' cm','Warn ≤ '+d.dist.warn);
  }catch(e){
    if(++fails>=3){$('link').className='lost';$('link').textContent='OFFLINE';$('status').className='stale';$('sIcon').textContent='📡';
      $('sTitle').textContent='Connection lost';$('sText').textContent='Reconnect to the "Shakthi-Hazard-Monitor" WiFi. Values below are old.';}
  }
  setTimeout(poll,1000);
}
poll();
</script>
</body>
</html>
)rawliteral";

#endif
