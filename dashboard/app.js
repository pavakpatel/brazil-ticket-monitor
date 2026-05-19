const money = n => n == null ? 'n/a' : '$' + Number(n).toLocaleString(undefined,{maximumFractionDigits:2,minimumFractionDigits:2});
const ET_OPTIONS = {timeZone:'America/New_York', month:'short', day:'numeric', year:'numeric', hour:'numeric', minute:'2-digit', timeZoneName:'short'};
const ET_SHORT_OPTIONS = {timeZone:'America/New_York', month:'numeric', day:'numeric', hour:'numeric', minute:'2-digit'};
function formatET(value){
  if(!value) return 'unknown';
  const d = new Date(value);
  if(Number.isNaN(d.getTime())) return value;
  return new Intl.DateTimeFormat('en-US', ET_OPTIONS).format(d).replace('EST','ET').replace('EDT','ET');
}
function formatChartET(value){
  if(!value) return '';
  const d = new Date(value);
  if(Number.isNaN(d.getTime())) return value;
  return new Intl.DateTimeFormat('en-US', ET_SHORT_OPTIONS).format(d);
}
const SOURCES = [
  {key:'fifa_cat1', label:'FIFA CAT1', color:'#8aa0ff'},
  {key:'fifa_cat2', label:'FIFA CAT2', color:'#a78bfa'},
  {key:'ticketmaster', label:'Ticketmaster', color:'#34d399'},
  {key:'seatgeek', label:'SeatGeek', color:'#fbbf24'},
  {key:'vivid', label:'Vivid Seats', color:'#fb7185'}
];
let DATA = null;
let enabled = Object.fromEntries(SOURCES.map(s => [s.key, true]));

async function load(){
  const res = await fetch('../data/dashboard.json?ts=' + Date.now());
  DATA = await res.json();
  const cur = DATA.current || {};
  document.getElementById('checked').textContent = 'Last checked: ' + formatET(cur.scraped_at_utc) + ' (East Coast)';
  const fifa = cur.fifa_haiti || [];
  const cat1 = fifa.find(x=>x.category==='CAT1') || fifa[0] || {};
  const cat2 = fifa.find(x=>x.category==='CAT2') || fifa[1] || {};
  const tm = cur.ticketmaster || {};
  const sg = cur.seatgeek || {};
  const vs = cur.vivid_seats || {};
  document.getElementById('cards').innerHTML = [
    card('FIFA CAT1 starting', cat1.starting_at || money(cat1.price), `Face ${cat1.face_value || 'n/a'}`),
    card('FIFA CAT2 starting', cat2.starting_at || money(cat2.price), `Face ${cat2.face_value || 'n/a'}`),
    card('Ticketmaster lowest', money(tm.lowest_price), `${tm.cheapest_seen?.section_row || ''} ${tm.url ? `· <a href="${tm.url}">event</a>` : ''}`),
    card('SeatGeek lowest', money(sg.lowest_price), `${(sg.notes || [])[0] || ''} ${sg.url ? `· <a href="${sg.url}">event</a>` : ''}`),
    card('Vivid Seats all-in', money(vs.lowest_price), `${vs.listing_count ? vs.listing_count + ' listings' : ''}${vs.average_price ? ' · avg ' + money(vs.average_price) : ''} ${vs.url ? `· <a href="${vs.url}">event</a>` : ''}`)
  ].join('');
  renderFilters();
  renderChart();
  renderGames(cur.all_brazil_fifa || []);
  renderRuns(DATA.runs || []);
}
function card(label,value,small){return `<article class="card"><div class="label">${label}</div><div class="value">${value || 'n/a'}</div><div class="small">${small || ''}</div></article>`}
function renderFilters(){
  document.getElementById('sourceFilters').innerHTML = SOURCES.map(s => `<label><input type="checkbox" data-source="${s.key}" ${enabled[s.key]?'checked':''}> ${s.label}</label>`).join('');
  document.querySelectorAll('[data-source]').forEach(cb => cb.onchange = e => { enabled[e.target.dataset.source] = e.target.checked; renderChart(); });
}
function getPrice(run, key){
  const f = run.fifa_haiti || [];
  if(key === 'fifa_cat1') return f.find(x=>x.category==='CAT1')?.price ?? null;
  if(key === 'fifa_cat2') return f.find(x=>x.category==='CAT2')?.price ?? null;
  if(key === 'ticketmaster') return run.ticketmaster?.lowest_price ?? null;
  if(key === 'seatgeek') return run.seatgeek?.lowest_price ?? null;
  if(key === 'vivid') return run.vivid_seats?.lowest_price ?? null;
  return null;
}
function renderChart(){
  if(!DATA) return;
  const canvas = document.getElementById('timelineChart');
  const ctx = canvas.getContext('2d');
  const ratio = window.devicePixelRatio || 1;
  const W = canvas.clientWidth, H = 320;
  canvas.width = W * ratio; canvas.height = H * ratio; ctx.setTransform(ratio,0,0,ratio,0,0);
  ctx.clearRect(0,0,W,H);
  const runs = (DATA.runs || []).filter(r => r.scraped_at_utc).sort((a,b)=>(a.scraped_at_utc||'').localeCompare(b.scraped_at_utc||''));
  const active = SOURCES.filter(s => enabled[s.key]);
  const values = [];
  active.forEach(s => runs.forEach(r => { const v = getPrice(r,s.key); if(v != null) values.push(v); }));
  if(!runs.length || !values.length){
    ctx.fillStyle = '#9aa4b2'; ctx.font = '14px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif';
    ctx.fillText('No chartable prices yet for the selected sources.', 24, 42);
    document.getElementById('chartLegend').innerHTML = '';
    return;
  }
  const pad = {l:58,r:18,t:20,b:42};
  const min = Math.floor(Math.min(...values) * .94 / 50) * 50;
  const max = Math.ceil(Math.max(...values) * 1.04 / 50) * 50;
  const x = i => pad.l + (W-pad.l-pad.r) * (runs.length === 1 ? .5 : i/(runs.length-1));
  const y = v => H-pad.b - ((v-min)/(max-min || 1))*(H-pad.t-pad.b);
  ctx.strokeStyle = '#242a33'; ctx.lineWidth = 1; ctx.fillStyle = '#9aa4b2'; ctx.font = '12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif';
  for(let i=0;i<5;i++){
    const yy = pad.t + (H-pad.t-pad.b)*i/4;
    const val = max - (max-min)*i/4;
    ctx.beginPath(); ctx.moveTo(pad.l,yy); ctx.lineTo(W-pad.r,yy); ctx.stroke();
    ctx.fillText('$' + Math.round(val).toLocaleString(), 8, yy+4);
  }
  runs.forEach((r,i)=>{
    if(i % Math.ceil(runs.length/6 || 1) !== 0 && i !== runs.length-1) return;
    const label = formatChartET(r.scraped_at_utc);
    ctx.fillStyle = '#7f8896'; ctx.fillText(label, x(i)-28, H-14);
  });
  active.forEach(s => {
    ctx.strokeStyle = s.color; ctx.lineWidth = 2.5; ctx.beginPath(); let started=false;
    runs.forEach((r,i)=>{ const v=getPrice(r,s.key); if(v==null) return; const xx=x(i), yy=y(v); if(!started){ctx.moveTo(xx,yy); started=true;} else ctx.lineTo(xx,yy); });
    if(started) ctx.stroke();
    runs.forEach((r,i)=>{ const v=getPrice(r,s.key); if(v==null) return; ctx.fillStyle = '#0d1117'; ctx.strokeStyle = s.color; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x(i), y(v), 4, 0, Math.PI*2); ctx.fill(); ctx.stroke(); });
  });
  document.getElementById('chartLegend').innerHTML = active.map(s => `<span><i class="dot" style="background:${s.color}"></i>${s.label}</span>`).join('');
}
function renderGames(rows){
  const by={}; rows.forEach(x=>{ const k=x.match+'|'+x.date; if(!by[k] || (x.price && x.price < by[k].price)) by[k]=x; });
  const vals=Object.values(by);
  document.getElementById('games').innerHTML = '<thead><tr><th>Match</th><th>Date</th><th>Venue</th><th>Cheapest</th></tr></thead><tbody>' + vals.map(x=>`<tr><td>${x.match||''}</td><td>${x.date||''}</td><td>${x.location||''}</td><td>${x.category||''} ${x.starting_at||''}</td></tr>`).join('') + '</tbody>';
}
function renderRuns(runs){
  const recent=[...runs].reverse().slice(0,12);
  document.getElementById('runs').innerHTML = '<thead><tr><th>Checked (East Coast)</th><th>FIFA CAT1</th><th>FIFA CAT2</th><th>Ticketmaster</th><th>SeatGeek</th><th>Vivid</th><th>Issues</th></tr></thead><tbody>' + recent.map(r=>{ const f=r.fifa_haiti||[]; const c1=f.find(x=>x.category==='CAT1')||{}; const c2=f.find(x=>x.category==='CAT2')||{}; return `<tr><td>${formatET(r.scraped_at_utc)}</td><td>${c1.starting_at||''}</td><td>${c2.starting_at||''}</td><td>${money(r.ticketmaster?.lowest_price)}</td><td>${money(r.seatgeek?.lowest_price)}</td><td>${money(r.vivid_seats?.lowest_price)}</td><td class="warn">${(r.errors||[]).join('; ')}</td></tr>` }).join('') + '</tbody>';
}
window.addEventListener('resize', () => renderChart());
load().catch(e=>{document.body.insertAdjacentHTML('afterbegin',`<pre class="warn">${e}</pre>`)});
