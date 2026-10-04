"""Self-contained report page. No remote assets or account actions."""

PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HFT-IBKR · Offline research</title><link rel="icon" href="data:,">
<style>
:root{--paper:#f5f3ed;--ink:#202c2a;--muted:#64716b;--line:#dcded5;--teal:#176c61;--ochre:#b28a35;--red:#9c4c39}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.6 Arial,sans-serif}
header{padding:19px 4vw;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:36px;background:#faf9f5}
.brand{font-weight:700;letter-spacing:-.5px;font-size:18px}nav{display:flex;gap:25px}a{color:inherit;text-decoration:none}a:hover{text-decoration:underline}
.badge{margin-left:auto;border:1px solid var(--line);border-radius:20px;padding:5px 14px;color:var(--teal);font-size:12px}
.layout{max-width:1440px;margin:auto;display:grid;grid-template-columns:240px minmax(0,1fr);padding:40px 4vw;gap:48px}
aside{border-right:1px solid var(--line);padding-right:26px}.side-title{font:26px/1.2 Georgia,serif;margin:0 0 12px}.muted{color:var(--muted)}
.small{font-size:12px}aside p{margin:8px 0 25px}aside dl{margin-top:25px}dt{color:var(--muted);font-size:12px}dd{margin:0 0 17px;font-family:Menlo,monospace;font-size:13px}
main{min-width:0}.title-line{display:flex;align-items:center;gap:18px;flex-wrap:wrap}h1{font:38px/1.2 Georgia,serif;letter-spacing:-1px;margin:0}
.kind{font-size:12px;color:var(--red);background:#eee2d6;padding:4px 11px;border-radius:4px}.subtitle{margin:12px 0 28px;color:var(--muted)}
.notice{border-left:3px solid var(--ochre);padding:9px 15px;background:#ede9df;font-size:13px;margin-bottom:30px}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border-top:1px solid var(--line);border-bottom:1px solid var(--line);margin-bottom:30px}
.metric{padding:19px 15px 19px 0}.metric+.metric{border-left:1px solid var(--line);padding-left:20px}.metric span{font-size:12px;color:var(--muted)}
.value{font:25px/1.4 Menlo,monospace;letter-spacing:-1px;margin:7px 0}.comparison{font-size:11px;color:var(--muted)}
.panel{padding:23px;background:#faf9f5;border:1px solid var(--line);margin-bottom:28px;border-radius:5px}.panel-head{display:flex;align-items:center;justify-content:space-between;gap:18px;flex-wrap:wrap}
h2{font:22px/1.3 Georgia,serif;margin:0 0 5px}.costs{display:flex;gap:4px;border:1px solid var(--line);border-radius:4px;padding:3px}
button{border:0;background:transparent;color:var(--muted);padding:8px 12px;cursor:pointer;border-radius:3px;font:12px Arial,sans-serif}
button[aria-pressed=true]{background:var(--ink);color:#fff}button:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid var(--ochre);outline-offset:3px}
.legend{display:flex;gap:23px;font-size:12px;margin:20px 0 5px}.dot{width:16px;height:3px;display:inline-block;background:var(--teal);margin-right:7px;vertical-align:middle}.dot.hold{background:var(--ochre)}
svg{width:100%;height:auto;display:block}.chart-caption{display:flex;justify-content:space-between;color:var(--muted);font:11px Menlo,monospace}
.holdings{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;margin:18px 0 0;border-top:1px solid var(--line);padding-top:17px}
.holding strong{display:block;font:16px Menlo,monospace;margin-top:5px}.holding span{font-size:11px;color:var(--muted)}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:15px}th{text-align:left;color:var(--muted);font-weight:400;font-size:11px;padding:9px 10px;border-bottom:1px solid var(--line)}
td{padding:12px 10px;border-bottom:1px solid var(--line)}.table-wrap{overflow:auto}.state{font:11px Menlo,monospace;color:var(--teal)}.state.halt{color:var(--red)}
details{margin-top:15px}summary{cursor:pointer;color:var(--teal);font-size:13px}.hash{font:11px/1.7 Menlo,monospace;overflow-wrap:anywhere;margin:12px 0}.source{font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere;max-height:260px;overflow:auto}
li{margin:8px 0;font-size:12px;color:var(--muted)}footer{color:var(--muted);font-size:11px;margin-top:15px;padding-bottom:25px}
@media(max-width:1050px){.layout{grid-template-columns:1fr;gap:15px}aside{border:0;border-bottom:1px solid var(--line);padding-bottom:15px}aside dl,aside p{display:none}aside .side-title{font-size:19px}.metrics .value{font-size:22px}}
@media(max-width:620px){header{gap:18px;flex-wrap:wrap}nav{gap:16px;font-size:12px}.badge{margin-left:0}.layout{padding-top:24px}h1{font-size:30px}.metrics{grid-template-columns:1fr 1fr}.metric:nth-child(3){border-left:0;padding-left:0}.metric:nth-child(n+3){border-top:1px solid var(--line)}.panel{padding:15px}.holdings{grid-template-columns:1fr 1fr}.value{font-size:22px}}
</style></head><body>
<header><div class="brand">HFT / IBKR</div><nav aria-label="Report sections"><a href="#research">Research</a><a href="#controls">Controls</a><a href="#provenance">Provenance</a></nav><span class="badge">Offline simulation</span></header>
<div class="layout"><aside><h2 class="side-title">The research ledger</h2><p class="muted small">Stored results, explicit assumptions, and an audit trail.</p><dl><dt>Instrument</dt><dd>SPY · USD</dd><dt>Hypothesis</dt><dd id="hypothesis"></dd><dt>Signal timing</dt><dd>Close → next open</dd><dt>Positioning</dt><dd>Whole shares · long / cash</dd><dt>Execution</dt><dd>Simulation only</dd></dl></aside>
<main id="research"><div class="title-line"><h1>Daily trend research</h1><span id="kind" class="kind"></span></div><p class="subtitle" id="interval"></p>
<div class="notice" id="notice"></div>
<div class="metrics"><div class="metric"><span>Trend return after modeled costs</span><div class="value" id="return"></div><div class="comparison" id="hold-return"></div></div>
<div class="metric"><span>Maximum drawdown</span><div class="value" id="drawdown"></div><div class="comparison" id="hold-drawdown"></div></div>
<div class="metric"><span>Executed trades</span><div class="value" id="trades"></div><div class="comparison" id="rejections"></div></div>
<div class="metric"><span>Modeled execution cost</span><div class="value" id="cost"></div><div class="comparison">Fees + spread + slippage + impact</div></div></div>
<section class="panel"><div class="panel-head"><div><h2>Portfolio value</h2><div class="small muted">Closing NAV across supplied sessions · USD</div></div><div class="costs" id="costs" role="group" aria-label="Execution cost scenario"></div></div>
<div class="legend"><span><i class="dot"></i>Trend</span><span><i class="dot hold"></i>Buy and hold</span><span>— Initial cash</span></div>
<svg id="chart" viewBox="0 0 850 300" role="img" aria-label="Trend and buy-and-hold portfolio values"></svg><div class="chart-caption"><span id="start"></span><span id="end"></span></div>
<div class="holdings"><div class="holding"><span>Final trend NAV</span><strong id="nav"></strong></div><div class="holding"><span>Final cash</span><strong id="cash"></strong></div><div class="holding"><span>Final shares</span><strong id="shares"></strong></div><div class="holding"><span>Unpaid distributions</span><strong id="receivables"></strong></div></div></section>
<section class="panel" id="controls"><h2>Order & recovery replay</h2><p class="small muted">Synthetic scenario snapshots. A READY state belongs to the replay, not a connected account. Rejected configurations have no final state to display.</p><div class="table-wrap"><table><thead><tr><th>Scenario</th><th>Final replay state</th><th>Orders retained</th><th>Halt reasons</th></tr></thead><tbody id="control-rows"></tbody></table></div><p id="empty-controls" class="muted small" hidden>No control reports were supplied for this snapshot.</p></section>
<section class="panel" id="provenance"><h2>Evidence & assumptions</h2><p class="small muted">Source declarations and hashes identify inputs; they do not independently verify data quality or licensing.</p><div id="hashes"></div><details><summary>Source declarations</summary><div class="source" id="source"></div></details><details><summary>Simulation assumptions</summary><ul id="assumptions"></ul></details></section>
<footer>Read-only report snapshot. No broker connection, live prices, credentials, or order submission.</footer></main></div>
<script type="application/json" id="report-data">__REPORT_DATA__</script>
<script>
'use strict';
const data=JSON.parse(document.getElementById('report-data').textContent);
const el=id=>document.getElementById(id), put=(id,value)=>el(id).textContent=value;
const money=v=>Number(v).toLocaleString('en-US',{style:'currency',currency:'USD'}), pct=v=>(Number(v)*100).toFixed(2)+'%';
put('kind',data.kind==='synthetic'?'Invented data':'Historical · declared source');
put('notice',data.kind==='synthetic'?'These prices are invented software fixtures. Returns below do not establish a market advantage.':'Exploratory historical replay. Provenance requires review and profitability remains unproven.');
put('hypothesis',data.lookback+'-session moving average');
function update(index){
 const s=data.scenarios[index], t=s.trend, h=s.hold;
 document.querySelectorAll('#costs button').forEach((b,i)=>b.setAttribute('aria-pressed',String(i===index)));
 put('interval',t.curve[0].session+' — '+t.curve.at(-1).session+' · '+t.curve.length+' evaluated sessions · '+s.cost+'× cost assumptions');
 put('return',pct(t.total_return));put('hold-return','Buy and hold: '+pct(h.total_return));put('drawdown',pct(t.maximum_drawdown));put('hold-drawdown','Buy and hold: '+pct(h.maximum_drawdown));
 put('trades',t.trade_count);put('rejections',t.rejection_count+' rejected trades');put('cost',money(t.modeled_execution_cost));
 for(const key of ['nav','cash','shares','receivables'])put(key,key==='shares'?t.final[key]:money(t.final[key]));
 put('start',t.curve[0].session);put('end',t.curve.at(-1).session);
 const all=[Number(data.initial),...t.curve.map(p=>Number(p.nav)),...h.curve.map(p=>Number(p.nav))];
 const lo=all.reduce((a,b)=>Math.min(a,b)),hi=all.reduce((a,b)=>Math.max(a,b)),pad=Math.max((hi-lo)*.12,Math.max(Math.abs(lo),Math.abs(hi))*.0001,1),min=lo-pad,max=hi+pad;
 const y=n=>270-(Number(n)-min)/(max-min)*240,x=i=>65+i/(Math.max(t.curve.length-1,1))*770;
 const path=curve=>curve.map((p,i)=>(i?'L':'M')+x(i).toFixed(2)+','+y(p.nav).toFixed(2)).join(' ');
 let svg='';for(let i=0;i<5;i++){const value=min+(max-min)*i/4,yy=y(value);svg+='<line x1="65" x2="835" y1="'+yy+'" y2="'+yy+'" stroke="#e2e4dc"/><text x="0" y="'+(yy+4)+'" fill="#64716b" font-size="10" font-family="Menlo,monospace">'+Math.round(value).toLocaleString('en-US')+'</text>';}
 svg+='<line x1="65" x2="835" y1="'+y(data.initial)+'" y2="'+y(data.initial)+'" stroke="#9fa89e" stroke-dasharray="4 5"/>';
 svg+='<path d="'+path(h.curve)+'" fill="none" stroke="#b28a35" stroke-width="2"/><path d="'+path(t.curve)+'" fill="none" stroke="#176c61" stroke-width="2.5"/>';
 el('chart').innerHTML=svg;
}
data.scenarios.forEach((s,i)=>{const b=document.createElement('button');b.type='button';b.textContent=s.cost+'× costs';b.setAttribute('aria-pressed','false');b.addEventListener('click',()=>update(i));el('costs').append(b);});
data.controls.forEach(c=>{const tr=document.createElement('tr');[c.id,c.state,c.orders,c.reasons.join(', ')||'None recorded'].forEach((v,i)=>{const td=document.createElement('td');td.textContent=v;if(i===1)td.className='state'+(c.state==='HALTED'?' halt':'');tr.append(td);});el('control-rows').append(tr);});
el('empty-controls').hidden=data.controls.length!==0;
for(const [label,value] of Object.entries({...data.hashes,report_sha256:data.report_sha256})){if(value){const line=document.createElement('div');line.className='hash';line.textContent=label.replaceAll('_',' ')+': '+value;el('hashes').append(line);}}
put('source',data.source);data.assumptions.forEach(a=>{const li=document.createElement('li');li.textContent=a;el('assumptions').append(li);});update(0);
</script></body></html>'''
