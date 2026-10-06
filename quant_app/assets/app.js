'use strict';
const $ = id => document.getElementById(id);
let token = '', state = null, sending = false, polling = false;
const money = value => value === null || value === undefined ? '—' : new Intl.NumberFormat('en-US', {style:'currency',currency:'USD',maximumFractionDigits:2}).format(Number(value));
const text = (id,value) => { $(id).textContent = value ?? '—'; };
const el = (tag,value,cls) => { const node=document.createElement(tag); if(value!==undefined)node.textContent=value; if(cls)node.className=cls; return node; };
const labels = {runner:'Shadow runner',setup_check:'Data connection check',study:'Historical study',checks:'Local tool check'};
function notice(message,success=false){ text('notice',message); $('notice').hidden=false; $('notice').classList.toggle('success',success); }
function page(name){
  if(!['overview','setup','decisions','portfolio','activity'].includes(name)) name='overview';
  document.querySelectorAll('.page').forEach(node=>node.hidden=node.id!==name);
  document.querySelectorAll('[data-page]').forEach(node=>{node.classList.toggle('selected',node.dataset.page===name);node.setAttribute('aria-current',node.dataset.page===name?'page':'false');});
  text('page-name',name[0].toUpperCase()+name.slice(1)); location.hash=name;
}
async function request(path,body){
  const options={headers:{'X-App-Token':token},cache:'no-store'};
  if(body){options.method='POST';options.headers['Content-Type']='application/json';options.body=JSON.stringify(body);}
  const response=await fetch(path,options);
  const data=await response.json();
  if(!response.ok)throw new Error(data.error||`Local app error ${response.status}`);
  return data;
}
function tag(id,ready,label){ text(id,label); $(id).className='tag '+(ready?'good':'bad'); }
function controls(){
  if(!state)return;
  const busy=sending||state.jobs.running||state.jobs.external_runner;
  document.querySelectorAll('[data-action]').forEach(button=>{
    const action=button.dataset.action;
    button.disabled=action==='stop' ? sending||!state.jobs.running : busy;
    if(action==='runner')button.disabled ||= !state.environment.ready||!state.study.ready||!state.credentials.present||!state.portfolio.ready||!!state.history.error;
    if(action==='study')button.disabled ||= state.study.ready||!state.credentials.present||!state.environment.ready;
    if(action==='setup_check')button.disabled ||= !state.study.ready||!state.credentials.present;
    if(action==='recover_accounting'){button.hidden=!state.portfolio.accounting_pending;button.disabled ||= !state.portfolio.accounting_pending;}
    if(action==='set_halt')button.disabled ||= !state.portfolio.book||state.portfolio.book.halted;
    if(action==='settle_cash')button.disabled ||= !state.portfolio.book||(state.portfolio.book.cash===state.portfolio.book.settled_cash);
  });
  for(const id of ['keys-form','book-form','fill-form'])$(id).querySelectorAll('button,input').forEach(node=>node.disabled=busy);
}
function detail(row){ text('decision-detail',JSON.stringify(row.detail||row,null,2)); $('decision-dialog').showModal(); }
function drawChart(rows){
  const marks=rows.filter(row=>row.mark_valid&&Number.isFinite(Number(row.nav))).slice().reverse();
  const svg=$('nav-chart'); svg.replaceChildren(); svg.hidden=!marks.length; $('chart-empty').hidden=!!marks.length;
  if(!marks.length)return;
  const values=marks.map(row=>Number(row.nav)),minimum=Math.min(...values),maximum=Math.max(...values),range=maximum-minimum||Math.max(maximum*.01,1);
  const x=i=>marks.length===1?460:80+i*790/(marks.length-1),y=v=>175-(v-minimum)*140/range;
  const draw=(name,attributes,content)=>{const node=document.createElementNS('http://www.w3.org/2000/svg',name);Object.entries(attributes).forEach(([key,value])=>node.setAttribute(key,String(value)));if(content!==undefined)node.textContent=content;svg.append(node);return node;};
  for(const v of [minimum,minimum+range/2,minimum+range]){const yy=y(v);draw('line',{x1:80,x2:870,y1:yy,y2:yy,stroke:'#e1e9ee'});draw('text',{x:0,y:yy+4,fill:'#627582','font-size':11},money(v));}
  draw('polyline',{points:marks.map((row,i)=>`${x(i)},${y(Number(row.nav))}`).join(' '),fill:'none',stroke:'#176b63','stroke-width':2.5});
  if(marks.length===1)draw('circle',{cx:x(0),cy:y(values[0]),r:4,fill:'#176b63'});
  draw('text',{x:80,y:215,fill:'#627582','font-size':11},marks[0].session);
  if(marks.length>1)draw('text',{x:870,y:215,fill:'#627582','font-size':11,'text-anchor':'end'},marks.at(-1).session);
  text('chart-caption',`${marks.length} recorded marks · through ${marks.at(-1).session}`);
}
function render(next){
  state=next;
  const {jobs,study,portfolio,history,health,credentials,environment}=state,rows=history.rows,latest=rows[0];
  const heartbeat=health.status||'missing';
  let runnerTitle='Runner stopped',description='Finish setup, then start the runner. No jobs start automatically.';
  if(jobs.external_runner){runnerTitle='Runner owned by another window';description='Stop the terminal runner there before using app controls. This app will not stop it.';}
  else if(jobs.running){runnerTitle=jobs.action==='runner'?(heartbeat==='failed'?'Runner needs attention':heartbeat==='waiting'?'Waiting for the session':'Shadow runner active'):`${labels[jobs.action]} running`;description=jobs.action==='runner'?'The daily runner records proposals only. Keep this app terminal open.':'Follow progress and errors in Activity.';}
  else if(jobs.exit_code!==null&&jobs.exit_code!==0&&!jobs.stopped){runnerTitle='Last job failed';description='See Activity for its error. Your existing evidence and history have been retained.';}
  else if(study.ready&&portfolio.ready&&credentials.present){description='Your study and simulated book are ready. Start the runner when you want it to use market data.';}
  text('runner-title',runnerTitle);text('runner-description',description);
  $('runner-dot').className='status-dot '+(jobs.running&&health.healthy?'good':heartbeat==='failed'?'bad':'');
  text('next-decision',health.expected_session?`Recorded expectation: ${health.expected_session} · ${health.expected_deadline}`:'No pending decision time recorded.');
  text('study-metric',study.ready?'Verified':'Needs setup');text('feed-metric',study.feed?`${study.feed.toUpperCase()} historical feed · ${study.outcome}`:'Existing evidence checked locally');
  text('decision-metric',latest?latest.action:'None yet');text('decision-date',latest?`${latest.session} · shadow proposal`:'No recorded decision');
  text('nav-metric',money(portfolio.last_mark?.nav));text('nav-date',portfolio.last_mark?`Recorded ${portfolio.last_mark.session} · simulated`:'No recorded NAV mark');
  text('heartbeat-metric',health.healthy?'Healthy':heartbeat==='missing'?'Not started':heartbeat[0].toUpperCase()+heartbeat.slice(1));
  text('heartbeat-date',health.age_seconds!==null?`${Math.max(0,Math.round(health.age_seconds))}s since update${health.issues?.length?' · '+health.issues.join('; '):''}`:'No heartbeat file');
  tag('env-tag',environment.ready,environment.ready?'Ready':'Needs attention');text('env-info',`Python ${environment.python_version} · Bash ${environment.bash_present?'available':'missing'}. ${environment.ready?'Project scripts found.':'Check this checkout and install Python 3.11+ / Bash.'}`);
  tag('keys-tag',credentials.present,credentials.present?'File found':'Missing');text('keys-info',`Local file: ${credentials.path}. ${credentials.present?'Existing keys are reused. Their values are not read into this page.':'Save your own Alpaca keys below.'}`);
  tag('study-tag',study.ready,study.ready?'Verified':'Needs attention');text('study-info',study.ready?`Authenticated ${study.feed.toUpperCase()} study: ${study.outcome}. No rerun needed.`:study.error||'Historical evidence is not ready.');
  tag('book-tag',portfolio.ready,portfolio.ready?'Ready':'Needs attention');text('book-info',portfolio.ready?'Your existing simulated book is reused.':' '+(portfolio.error||'Choose starting simulated cash below.'));
  $('book-form').hidden=!!portfolio.book||!!history.total||!!history.error;
  text('setup-count',[environment.ready,credentials.present,study.ready,portfolio.ready].filter(Boolean).length+'/4');
  const panel=$('latest-decision');panel.replaceChildren();
  if(latest){const main=el('div',undefined,'decision-main');main.append(el('span',latest.action,'pill '+latest.action),el('h3',latest.quantity?`${latest.quantity} SPY shares`:'No proposed trade'),el('small',latest.session));const reason=el('div',undefined,'decision-reason');reason.append(el('p',latest.reason),el('small',latest.reference_price?`Reference ${money(latest.reference_price)} · ${latest.filled?'Simulated fill recorded':'No fill recorded'}`:'Verified ledger record'));const button=el('button','Inspect decision','text-button');button.addEventListener('click',()=>detail(latest));panel.append(main,reason,button);}
  else panel.append(el('p',history.error?'History could not be verified. Review the error in Decisions.':'No decisions yet. Finish Setup, then start the shadow runner.','empty'));
  text('history-count',`${history.total} decisions${history.total>rows.length?' · latest '+rows.length+' shown':''}`);$('history-error').hidden=!history.error;text('history-error',history.error||'');
  $('history-empty').hidden=!!rows.length||!!history.error;document.querySelector('#decisions .table-wrap').hidden=!rows.length;
  $('history-body').replaceChildren();
  for(const row of rows){const tr=el('tr');tr.append(el('td',row.session));const side=el('td');side.append(el('span',row.action,'pill '+row.action));if(row.filled)side.append(el('small',' · simulated fill'));tr.append(side,el('td',row.quantity||'—'),el('td',money(row.reference_price)),el('td',row.mark_valid?money(row.nav):'Invalid mark'),el('td',`${row.signal||'—'} · ${row.reason}`,'reason'));const cell=el('td'),button=el('button','View','text-button');button.setAttribute('aria-label',`View decision ${row.session}`);button.addEventListener('click',()=>detail(row));cell.append(button);tr.append(cell);$('history-body').append(tr);}
  $('portfolio-error').hidden=!portfolio.error;text('portfolio-error',portfolio.error||'');$('portfolio-empty').hidden=!!portfolio.book;$('portfolio-content').hidden=!portfolio.book;
  if(portfolio.book){const book=portfolio.book;text('book-cash',money(book.cash));text('book-settled',money(book.settled_cash));text('book-shares',book.shares);text('book-peak',money(book.peak_nav));text('halt-description',book.halted?'Manual global halt is active: BUY and SELL proposals are blocked. Reviewed recovery is required to clear it.':portfolio.entry_halted?'Drawdown entry halt is active: new BUY proposals are blocked; reducing SELL proposals remain eligible. The button below additionally halts all proposals.':'Pause all BUY and SELL proposals when the simulated book needs review.');}
  drawChart(rows);
  const eligible=latest?.fill_eligible;
  $('fill-form').hidden=!eligible;
  text('fill-description',eligible?`Explicitly record the full ${latest.action} proposal: ${latest.quantity} SPY shares from ${latest.session}. Choose a simulated fill price and fees. Nothing is submitted to a broker.`:portfolio.accounting_pending?'A pending fill needs explicit recovery. Use Recover pending accounting; settlement and halt settings stay unchanged.':'No eligible unfilled proposal. Only the latest verified BUY/SELL can be recorded against its original book.');
  if(eligible&&$('fill-form').elements.decision_id.value!==latest.decision_id){$('fill-form').elements.decision_id.value=latest.decision_id;$('fill-form').elements.price.value='';$('fill-form').elements.price.placeholder=latest.reference_price;$('fill-form').elements.fees.value=latest.detail?.proposal?.estimated_fees||'0';}
  text('job-tag',jobs.running?`${labels[jobs.action]} active`:jobs.external_runner?'External runner active':'No active job');
  $('job-list').replaceChildren();for(const job of [...jobs.recent].reverse()){const row=el('div',undefined,'job-row');row.append(el('span',labels[job.action]||job.action),el('small',`${job.started_at} · ${job.exit_code===null?'Active':job.stopped?'Stopped':job.exit_code===0?'Completed':'Exit '+job.exit_code}`));$('job-list').append(row);}
  text('job-output',jobs.logs.length?jobs.logs.join('\n'):'No jobs have run from this app yet.');text('activity-dot',jobs.running?'●':jobs.exit_code?'!':'');
  text('refreshed',`Updated ${new Date(state.generated_at).toLocaleTimeString()}`);controls();
}
async function refresh(){if(polling)return;polling=true;try{render(await request('/api/status'));}catch(error){notice(error.message);text('refreshed','Disconnected');document.querySelectorAll('[data-action],form button').forEach(button=>button.disabled=true);}finally{polling=false;}}
async function action(name,payload={}){
  if(sending)return;
  sending=true;controls();
  try{await request('/api/action',{action:name,...payload});notice(name==='record_fill'?'Simulated fill recorded. No order was sent.':name==='save_keys'?'Keys saved locally.':name==='initialize_book'?'Simulated book created.':name==='set_halt'?'Manual global halt set. All proposals are blocked; risk memory is preserved.':name==='recover_accounting'?'Pending accounting recovered. Settlement and halt settings were preserved.':name==='settle_cash'?'Cash settlement confirmed.':'Action accepted. Follow progress in Activity.',true);if(['runner','study','checks','setup_check'].includes(name))page('activity');}
  catch(error){notice(error.message);}
  finally{sending=false;await refresh();controls();}
}
document.querySelectorAll('[data-page],[data-go]').forEach(button=>button.addEventListener('click',()=>page(button.dataset.page||button.dataset.go)));
document.querySelectorAll('[data-action]').forEach(button=>button.addEventListener('click',()=>{const name=button.dataset.action;if(name==='study'&&!confirm('Download Alpaca historical data and run the study? Existing evidence and the original registry will be retained.'))return;if(name==='set_halt'&&!confirm('Set a manual global halt on all BUY and SELL proposals? This app does not clear risk halts.'))return;if(name==='settle_cash'&&!confirm('Confirm that the simulated sale proceeds have settled? Use the recovery control first if accounting is pending.'))return;action(name);}));
for(const [id,name] of [['keys-form','save_keys'],['book-form','initialize_book'],['fill-form','record_fill']])$(id).addEventListener('submit',event=>{event.preventDefault();const data=Object.fromEntries(new FormData(event.currentTarget));if(name==='save_keys')event.currentTarget.reset();if(name==='record_fill'&&!confirm('Record this full simulated fill exactly once? No broker order will be sent.'))return;action(name,data);});
$('refresh').addEventListener('click',refresh);$('close-dialog').addEventListener('click',()=>$('decision-dialog').close());window.addEventListener('hashchange',()=>page(location.hash.slice(1)));
(async()=>{page(location.hash.slice(1));try{token=(await request('/api/session')).token;await refresh();setInterval(refresh,5000);}catch(error){notice(error.message);}})();
