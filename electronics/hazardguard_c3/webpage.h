#ifndef WEBPAGE_H
#define WEBPAGE_H

// Self-contained page: phones on the hotspot have no internet.
const char INDEX_HTML[] PROGMEM = R"rawliteral(
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HazardGuard C3</title>
<style>
:root{--bg:#0f0d0b;--panel:#1a1714;--line:#2e2924;--text:#f3eee8;--muted:#a39a8f;--accent:#f97316;
--safe:#22c55e;--warn:#eab308;--danger:#ef4444;--off:#52493f}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--text)}
header{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid var(--line)}
.brand{display:flex;align-items:center;gap:10px}
.logo{width:34px;height:34px;border-radius:9px;background:var(--accent);display:grid;place-items:center;font-weight:900;color:#1a0d00}
h1{font-size:1.05rem;margin:0}
.sub{color:var(--muted);font-size:.75rem}
.pill{font-size:.7rem;font-weight:800;padding:4px 10px;border-radius:999px;background:var(--safe);color:#04130a}
.pill.lost{background:var(--danger);color:#fff}
main{max-width:1000px;margin:0 auto;padding:14px;display:grid;gap:12px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px}
#banner{display:flex;align-items:center;gap:14px;border-radius:14px;padding:16px;background:var(--safe);color:#04130a}
#banner.l1{background:var(--warn);color:#1a1400}
#banner.l2{background:var(--danger);color:#fff;animation:pulse .7s infinite}
#banner.stale{background:var(--off);color:var(--text);animation:none}
#banner b{font-size:1.5rem;display:block}
@keyframes pulse{50%{filter:brightness(1.3)}}
.lights{display:flex;gap:8px;margin-left:auto}
.lamp{width:22px;height:22px;border-radius:50%;background:#0006;border:2px solid #0004}
.lamp.on.g{background:#4ade80;box-shadow:0 0 12px #4ade80}.lamp.on.y{background:#fde047;box-shadow:0 0 12px #fde047}
.lamp.on.r{background:#f87171;box-shadow:0 0 14px #f87171}
.gauges{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}
.gauge{text-align:center;position:relative}
.gauge h3{margin:0 0 4px;font-size:.85rem;color:var(--muted);font-weight:600;text-align:left}
.gauge svg{width:100%;max-width:220px}
.gauge .num{font-size:2rem;font-weight:800;font-variant-numeric:tabular-nums;margin-top:-62px}
.gauge .unit{color:var(--muted);font-size:.8rem}
.gauge .state{display:inline-block;margin-top:8px;font-size:.7rem;font-weight:800;padding:3px 10px;border-radius:999px;background:var(--safe);color:#04130a}
.gauge.l1 .state{background:var(--warn);color:#1a1400}.gauge.l2 .state{background:var(--danger);color:#fff}
.gauge.na .state{background:var(--off);color:var(--text)}.gauge.na .num{color:var(--muted);font-size:1.1rem}
.spark{display:block;width:100%;height:34px;margin-top:8px}
.spark polyline{fill:none;stroke:var(--accent);stroke-width:1.6;vector-effect:non-scaling-stroke}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.row+.row{margin-top:10px}
.label{color:var(--muted);font-size:.8rem;min-width:70px}
.seg{display:flex;background:#0003;border:1px solid var(--line);border-radius:10px;overflow:hidden}
.seg button{background:none;border:0;color:var(--text);padding:9px 14px;font-weight:600;cursor:pointer}
.seg button.on{background:var(--accent);color:#1a0d00}
button.big{background:var(--line);color:var(--text);border:0;border-radius:10px;padding:10px 14px;font-weight:700;cursor:pointer}
button.big.alert{background:var(--danger);color:#fff}
.th{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.th label{font-size:.75rem;color:var(--muted);display:block}
.th input{width:100%;background:#0003;border:1px solid var(--line);color:var(--text);border-radius:8px;padding:8px;font-size:1rem}
.meta{display:flex;justify-content:space-between;color:var(--muted);font-size:.75rem;margin-top:8px}
footer{text-align:center;color:var(--muted);font-size:.72rem;padding:16px}
</style>
</head>
<body>
<header>
  <div class="brand"><div class="logo">HG</div><div><h1>HazardGuard C3</h1><div class="sub" id="uptime">Connecting…</div></div></div>
  <span class="pill" id="link">LIVE</span>
</header>
<main>
  <div id="banner"><div><b id="bTitle">CONNECTING</b><span id="bText">Waiting for the controller…</span></div>
    <div class="lights"><span class="lamp g" id="lg"></span><span class="lamp y" id="ly"></span><span class="lamp r" id="lr"></span></div></div>

  <div class="gauges" id="gauges">
  </div>
  <div class="panel sub" id="faults" hidden></div>

  <div class="panel">
    <div class="row"><span class="label">Profile</span><div class="seg" id="profiles"><button data-p="0">Household</button><button data-p="1">Hotel kitchen</button><button data-p="2">Industrial</button></div></div>
    <div class="row"><span class="label">Alarm</span><button class="big" id="siren">Phone siren: off</button></div>
  </div>

  <div class="panel">
    <div class="row"><span class="label">LED test</span><div class="seg" id="ledtest"><button data-l="1">Green</button><button data-l="2">Yellow</button><button data-l="4">Red</button><button data-l="7">All on</button><button data-l="8">Cycle</button></div><button class="big" id="ledstop">Stop test</button></div>
    <div class="row"><span class="sub" id="ledState">Tap a colour to light that LED on the box. The test ends by itself after 60 s.</span></div>
  </div>

  <div class="panel">
    <div class="th">
      <div><label>LPG MQ-5 warning (ADC)</label><input id="tMq5Warn" type="number"></div>
      <div><label>LPG MQ-5 danger (ADC)</label><input id="tMq5Alarm" type="number"></div>
      <div><label>Alcohol MQ-3 warning (ADC)</label><input id="tMq3Warn" type="number"></div>
      <div><label>Alcohol MQ-3 danger (ADC)</label><input id="tMq3Alarm" type="number"></div>
      <div><label>Temp warning (°C)</label><input id="tTempWarn" type="number" step="0.5"></div>
      <div><label>Temp danger (°C)</label><input id="tTempAlarm" type="number" step="0.5"></div>
      <div><label>Moisture warning (%)</label><input id="tSoilWarn" type="number"></div>
      <div><label>Moisture danger (%)</label><input id="tSoilAlarm" type="number"></div>
    </div>
    <div class="row"><button class="big" id="save" style="background:var(--accent);color:#1a0d00">Save thresholds</button><span class="sub" id="saved"></span></div>
  </div>
</main>
<footer>ESP32-C3 · Hotspot "HazardGuard-C3" · http://192.168.4.1</footer>
<script>
const $=id=>document.getElementById(id);
const LBL=['SAFE','WARNING','DANGER'];
const GAUGES=[['Mq5','LPG / gas (MQ-5)','ADC (0-4095)'],['Mq3','Alcohol / solvent (MQ-3)','ADC (0-4095)'],
  ['Temp','Temperature (DHT11)','°C'],['Soil','Water / moisture (soil probe)','% wet']];
const hist={};
GAUGES.forEach(([id,title,unit])=>{hist[id]=[];$('gauges').insertAdjacentHTML('beforeend',
  `<div class="panel gauge" id="g${id}"><h3>${title}</h3><svg viewBox="0 0 200 120"><path d="M20 110 A80 80 0 0 1 180 110" stroke="#2e2924" stroke-width="16" fill="none" stroke-linecap="round"/><path id="a${id}" d="M20 110 A80 80 0 0 1 180 110" stroke="#22c55e" stroke-width="16" fill="none" stroke-linecap="round" pathLength="100" stroke-dasharray="0 100"/></svg><div class="num" id="v${id}">—</div><div class="unit" id="u${id}">${unit}</div><span class="state" id="s${id}">—</span><svg class="spark" viewBox="0 0 59 34" preserveAspectRatio="none"><polyline id="p${id}"/></svg></div>`);});
let editing=false,siren=false,audio=null,osc=null,last=null,fails=0;
document.querySelectorAll('.th input').forEach(i=>{i.onfocus=()=>editing=true;});

function arc(id,frac,lvl){const a=$('a'+id);a.setAttribute('stroke-dasharray',`${Math.max(0,Math.min(100,frac*100))} 100`);
  a.setAttribute('stroke',lvl==2?'#ef4444':lvl==1?'#eab308':'#22c55e');}
function spark(id,v){const h=hist[id];h.push(v);if(h.length>60)h.shift();const n=h.filter(x=>x!==null);
  const mn=Math.min(...n),mx=Math.max(...n),sp=(mx-mn)||1;
  $('p'+id).setAttribute('points',h.map((x,i)=>x===null?'':`${i+60-h.length},${32-(x-mn)/sp*30}`).filter(Boolean).join(' '));}
function gauge(id,val,frac,lvl,label){const g=$('g'+id),na=val===null;g.className='panel gauge '+(na?'na':'l'+lvl);
  $('v'+id).textContent=na?'Sensor fault':val;$('s'+id).textContent=label||(na?'NO SIGNAL':LBL[lvl]);arc(id,na?0:frac,lvl);spark(id,na?null:Number(val));}

function render(d){
  last=d;const s=d.uptime;
  $('uptime').textContent=`${d.profileName} · up ${Math.floor(s/3600)}h ${Math.floor(s%3600/60)}m · ${d.clients} connected`;
  const b=$('banner');b.className=d.level?'l'+d.level:'';
  $('bTitle').textContent=d.warmup>0&&!d.level?`WARMING UP · ${d.warmup}s`:LBL[d.level];$('bText').textContent=d.hazards;
  $('lg').className='lamp g'+(d.leds.g?' on':'');$('ly').className='lamp y'+(d.leds.y?' on':'');$('lr').className='lamp r'+(d.leds.r?' on':'');
  const f=d.flags,t=d.th;
  const wl=d.warmup>0?'WARMING':null;
  gauge('Mq5',d.mq5,d.mq5/4095,f.mq5Alarm?2:f.mq5Warn?1:0,wl);
  gauge('Mq3',d.mq3,d.mq3/4095,f.mq3Alarm?2:f.mq3Warn?1:0,wl);
  gauge('Temp',d.temp,d.temp===null?0:d.temp/80,f.tempAlarm?2:f.tempWarn?1:0);
  $('uTemp').textContent=d.hum===null?'°C':`°C · humidity ${d.hum}%`;
  gauge('Soil',d.soil,d.soil===null?0:d.soil/100,f.soilAlarm?2:f.soilWarn?1:0);
  $('uSoil').textContent=`% wet · raw ${d.soilRaw}`;
  $('faults').hidden=!d.faults;$('faults').textContent=d.faults?'Not connected or not answering: '+d.faults:'';
  document.querySelectorAll('#profiles button').forEach(x=>x.classList.toggle('on',+x.dataset.p===d.profile));
  document.querySelectorAll('#ledtest button').forEach(x=>x.classList.toggle('on',+x.dataset.l===d.ledTest));
  $('ledstop').className='big'+(d.ledTest?' alert':'');
  $('ledState').textContent=d.ledTest?'LED test running: the lights above show what the box should show.':'Tap a colour to light that LED on the box. The test ends by itself after 60 s.';
  if(!editing){$('tMq5Warn').value=t.mq5Warn;$('tMq5Alarm').value=t.mq5Alarm;$('tMq3Warn').value=t.mq3Warn;$('tMq3Alarm').value=t.mq3Alarm;
    $('tTempWarn').value=t.tempWarn;$('tTempAlarm').value=t.tempAlarm;$('tSoilWarn').value=t.soilWarn;$('tSoilAlarm').value=t.soilAlarm;}
  sound(d.level==2&&siren);
}
function sound(on){
  if(on&&!osc){osc=audio.createOscillator();const g=audio.createGain();g.gain.value=.15;osc.type='square';osc.connect(g).connect(audio.destination);
    osc.start();let hi=true;osc._t=setInterval(()=>{osc.frequency.value=(hi=!hi)?1400:900},350);}
  if(!on&&osc){clearInterval(osc._t);osc.stop();osc=null;}
}
async function api(url){try{const r=await fetch(url,{cache:'no-store'});render(await r.json());}catch(e){}}
async function poll(){
  try{const r=await fetch('/api/data',{cache:'no-store'});render(await r.json());fails=0;$('link').className='pill';$('link').textContent='LIVE';}
  catch(e){if(++fails>=3){$('link').className='pill lost';$('link').textContent='OFFLINE';$('banner').className='stale';
    $('bTitle').textContent='CONNECTION LOST';$('bText').textContent='Reconnect to the "HazardGuard-C3" WiFi. Values shown are old.';sound(false);}}
  setTimeout(poll,800);
}
document.querySelectorAll('#profiles button').forEach(b=>b.onclick=()=>{editing=false;api('/api/profile?p='+b.dataset.p)});
document.querySelectorAll('#ledtest button').forEach(b=>b.onclick=()=>api('/api/ledtest?leds='+b.dataset.l));
$('ledstop').onclick=()=>api('/api/ledtest?leds=0');
$('siren').onclick=()=>{audio=audio||new (window.AudioContext||window.webkitAudioContext)();siren=!siren;
  $('siren').textContent='Phone siren: '+(siren?'on':'off');$('siren').className='big'+(siren?' alert':'');if(!siren)sound(false);};
$('save').onclick=async()=>{editing=false;const q=['Mq5Warn','Mq5Alarm','Mq3Warn','Mq3Alarm','TempWarn','TempAlarm','SoilWarn','SoilAlarm']
    .map(k=>k[0].toLowerCase()+k.slice(1)+'='+encodeURIComponent($('t'+k).value)).join('&');
  await api('/api/thresholds?'+q);
  $('saved').textContent='Saved to the controller ✓';setTimeout(()=>$('saved').textContent='',2500);};
poll();
</script>
</body>
</html>
)rawliteral";

#endif
