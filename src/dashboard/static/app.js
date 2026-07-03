const CVD_TREND_WINDOW_MS=15*60*1000;
const PRICE_REFRESH_MS=5000;
const CRON_REFRESH_SEC=15*60;
let lastDashboardState=null;
let latestJobStatus=null;
const cvdUiHistory={};

function fmtNum(v, digits=2){
  if(v===null||v===undefined||Number.isNaN(Number(v))) return '--';
  return Number(v).toLocaleString(undefined,{maximumFractionDigits:digits});
}


function fmtSignedNum(v, digits=0){
  if(v===null||v===undefined||Number.isNaN(Number(v))) return '--';
  const n=Number(v);
  return (n>0?'+':'') + n.toLocaleString(undefined,{maximumFractionDigits:digits});
}

function rememberCvdPoint(symbol, value){
  const key=String(symbol||'UNKNOWN').toUpperCase();
  if(value===null||value===undefined||Number.isNaN(Number(value))) return;
  const now=Date.now();
  const arr=cvdUiHistory[key] || (cvdUiHistory[key]=[]);
  const cvd=Number(value);
  if(!arr.length || arr[arr.length-1].value!==cvd){
    arr.push({ts:now,value:cvd});
  }
  const cutoff=now-(CVD_TREND_WINDOW_MS*4);
  while(arr.length && arr[0].ts<cutoff) arr.shift();
}

function cvdUiDelta15m(symbol, current){
  const key=String(symbol||'UNKNOWN').toUpperCase();
  const arr=cvdUiHistory[key] || [];
  const now=Date.now();
  const target=now-CVD_TREND_WINDOW_MS;
  let previous=null;
  for(const p of arr){
    if(p.ts<=target) previous=p.value;
    else break;
  }
  if(previous===null || current===null || current===undefined || Number.isNaN(Number(current))) return null;
  return Number(current)-previous;
}

function cvdTrendInfo(row, symbol){
  const current=row ? row.cvd : null;
  rememberCvdPoint(symbol, current);

  const trend=String((row&&row.cvd_trend)||'').toUpperCase();
  const deltaRaw=row ? row.cvd_delta_15m : null;
  let delta=(deltaRaw===null||deltaRaw===undefined||Number.isNaN(Number(deltaRaw))) ? null : Number(deltaRaw);
  if(delta===null){
    delta=cvdUiDelta15m(symbol, current);
  }

  let dir=trend;
  if(!dir && delta!==null){
    dir = delta>0 ? 'RISING' : (delta<0 ? 'FALLING' : 'FLAT');
  }
  if(dir==='RISING') return {label:'↗ Rising 15m', cls:'long', delta};
  if(dir==='FALLING') return {label:'↘ Falling 15m', cls:'short', delta};
  if(dir==='FLAT') return {label:'→ Flat 15m', cls:'muted', delta};
  return {label:'Waiting 15m', cls:'muted', delta:null};
}

function cvdDisplay(row, symbol){
  const value=row ? row.cvd : null;
  const info=cvdTrendInfo(row||{}, symbol);
  return `
    <span class="cvd-stack">
      <span class="${Number(value)>=0?'long':'short'}">${fmtNum(value,0)}</span>
      <span class="cvd-trend ${info.cls}">${info.label}</span>
      <span class="cvd-delta ${info.cls}">Δ ${info.delta===null?'--':fmtSignedNum(info.delta,0)}</span>
    </span>
  `;
}

function fmtPrice(v){
  if(v===null||v===undefined) return '--';
  let n=Number(v);
  let d=n<1?6:2;
  return '$'+n.toLocaleString(undefined,{maximumFractionDigits:d});
}

function fmtPct(v){
  if(v===null||v===undefined) return '--';
  return Number(v).toFixed(1)+'%';
}

function fmtFunding(v){
  if(v===null||v===undefined) return '--';
  return (Number(v)*100).toFixed(4)+'%';
}

function fmtOI(v){
  if(v===null||v===undefined) return '--';
  let n=Number(v);
  if(n>=1e9) return '$'+(n/1e9).toFixed(2)+'B';
  if(n>=1e6) return '$'+(n/1e6).toFixed(2)+'M';
  return '$'+fmtNum(n,0);
}

function lsPair(l,s){
  return `<span class="ls-pair"><span class="long">L ${fmtPct(l)}</span> <span class="short">S ${fmtPct(s)}</span></span>`;
}

function age(sec){
  if(sec===null||sec===undefined) return '--';
  if(sec<60) return sec+' sec ago';
  let m=Math.floor(sec/60), s=sec%60;
  return `${m}m ${s}s ago`;
}

function countdown(sec){
  sec=Math.max(0,sec||0);
  let m=Math.floor(sec/60), s=sec%60;
  return String(m).padStart(2,'0')+':'+String(s).padStart(2,'0');
}

function parseIsoTs(value){
  if(!value) return null;
  const t=Date.parse(value);
  return Number.isNaN(t) ? null : Math.floor(t/1000);
}

function ageFromIso(value){
  const ts=parseIsoTs(value);
  if(!ts) return null;
  return Math.max(0, Math.floor(Date.now()/1000)-ts);
}

function cronCountdownFromJob(job){
  const finished=job ? parseIsoTs(job.finished_at) : null;
  if(!finished) return null;
  const next=finished+CRON_REFRESH_SEC;
  return Math.max(0, next-Math.floor(Date.now()/1000));
}

function mergePriceFallback(data){
  if(!lastDashboardState) return data;
  if(data && data.btc && lastDashboardState.btc){
    if(data.btc.price===null || data.btc.price===undefined) data.btc.price=lastDashboardState.btc.price;
    if(!data.btc.price_updated_at) data.btc.price_updated_at=lastDashboardState.btc.price_updated_at;
  }
  const prevBySymbol={};
  for(const r of (lastDashboardState.followers||[])){
    prevBySymbol[String(r.symbol||'').toUpperCase()]=r;
  }
  for(const r of (data.followers||[])){
    const prev=prevBySymbol[String(r.symbol||'').toUpperCase()];
    if(prev && (r.price===null || r.price===undefined)) r.price=prev.price;
  }
  return data;
}

function setText(id, value){
  const el=document.getElementById(id);
  if(el) el.textContent=value;
}

function setClass(id, cls){
  const el=document.getElementById(id);
  if(el) el.className=cls;
}

function clsPnl(v){
  return Number(v)>=0?'pos':'neg';
}

function scoreClass(v){
  const n=Number(v||0);
  if(n>=80) return 'score-strong';
  if(n>=70) return 'score-good';
  if(n>=60) return 'score-watch';
  return 'score-weak';
}

function clearStateClasses(el){
  if(!el) return;
  el.classList.remove(
    'state-safe','state-warning','state-danger','state-neutral',
    'state-low','state-normal','state-high','state-extreme'
  );
}

function statusBadgeClass(kind, label){
  const v=String(label||'').toUpperCase();

  if(kind==='exit'){
    if(v.includes('SAFE')) return 'state-badge state-safe';
    if(v.includes('WARNING')) return 'state-badge state-warning';
    if(v.includes('EXIT')) return 'state-badge state-danger';
    return 'state-badge state-neutral';
  }

  if(kind==='spread'){
    if(v.includes('EXTREME')) return 'state-badge state-extreme';
    if(v.includes('HIGH')) return 'state-badge state-high';
    if(v.includes('NORMAL')) return 'state-badge state-normal';
    if(v.includes('LOW')) return 'state-badge state-low';
    return 'state-badge state-neutral';
  }

  return 'state-badge state-neutral';
}

function setInsightState(card, state){
  clearStateClasses(card);
  if(card && state) card.classList.add(state);
}


function shortSym(s){
  return (s||'').replace('USDT','');
}

function coinIcon(symbol){
  const s=shortSym(symbol).toUpperCase();

  if(s === 'SOL'){
    return `
      <svg class="coin-svg solana-svg" viewBox="0 0 128 128" aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id="solanaGradient" x1="16" y1="16" x2="112" y2="112" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stop-color="#00FFA3"/>
            <stop offset="50%" stop-color="#DC1FFF"/>
            <stop offset="100%" stop-color="#00D1FF"/>
          </linearGradient>
        </defs>
        <path d="M30 31h70c2.4 0 3.6 2.9 1.9 4.6L89.8 47.7c-1 .9-2.2 1.4-3.5 1.4H16.2c-2.4 0-3.6-2.9-1.9-4.6l12.1-12.1c1-.9 2.2-1.4 3.6-1.4Z" fill="url(#solanaGradient)"/>
        <path d="M98 55.4H28c-2.4 0-3.6 2.9-1.9 4.6l12.1 12.1c1 .9 2.2 1.4 3.5 1.4h70.1c2.4 0 3.6-2.9 1.9-4.6l-12.1-12.1c-1-.9-2.2-1.4-3.6-1.4Z" fill="url(#solanaGradient)"/>
        <path d="M30 80h70c2.4 0 3.6 2.9 1.9 4.6L89.8 96.7c-1 .9-2.2 1.4-3.5 1.4H16.2c-2.4 0-3.6-2.9-1.9-4.6l12.1-12.1c1-.9 2.2-1.4 3.6-1.4Z" fill="url(#solanaGradient)"/>
      </svg>
    `;
  }

  const icons={
    BTC:'₿',
    ETH:'◇',
    DOGE:'Ð',
    XRP:'✕'
  };

  return icons[s] || '✦';
}

function lsCompact(l,s){
  return `<span class="ls-compact"><span class="long">L: ${fmtPct(l)}</span><i>|</i><span class="short">S: ${fmtPct(s)}</span></span>`;
}


function appBasePath(){
  const parts=window.location.pathname.split('/').filter(Boolean);
  if(parts.length>=2 && parts[0].toLowerCase()==='sniper') return '/' + parts.slice(0,2).join('/');
  return '';
}

function apiUrl(path){
  if(!path) return appBasePath();
  if(/^https?:/i.test(path)) return path;
  if(path.startsWith('/api/')) return appBasePath() + path;
  return path;
}

async function api(url, options={}){
  const r=await fetch(apiUrl(url),{headers:{'Content-Type':'application/json'},...options});
  if(!r.ok){throw new Error(await r.text())}
  return r.json();
}

function fmtMoney(v){
  if(v===null||v===undefined||Number.isNaN(Number(v))) return '--';
  const n=Number(v);
  const sign=n>0?'+':'';
  return sign+'$'+Math.abs(n).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
}

function fmtEquity(v){
  if(v===null||v===undefined) return '--';
  return '$'+Number(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
}

function fmtSize(v){
  if(v===null||v===undefined) return '--';
  return '$'+Number(v).toLocaleString(undefined,{maximumFractionDigits:2});
}

function fmtJudgment(v){
  if(!v){
    return {
      icon:'⚪',
      title:'Legacy trade'
    };
  }

  if(v.includes('BTC_LONG_CROWDED')){
    return {
      icon:'🔴',
      title:v
    };
  }

  if(v.includes('BTC_SHORT_CROWDED')){
    return {
      icon:'🟢',
      title:v
    };
  }

  return {
    icon:'🟡',
    title:v
  };
}

function fmtMonitorAlert(alert){
  if(!alert){
    return {
      cls:'muted',
      text:'WAITING',
      title:'Monitor data is not available yet.'
    };
  }

  const status=String(alert.status||'WAITING').toUpperCase();
  let cls='muted';

  if(status.includes('HOLD')) cls='pos';
  else if(status.includes('EXIT')) cls='neg';
  else if(status.includes('WARNING') || status.includes('WATCH')) cls='warning';

  const btc=alert.btc_status || '--';
  const sym=alert.symbol_status || '--';
  const reason=alert.reason || '';

  return {
    cls,
    text:status,
    title:`BTC: ${btc} | Symbol: ${sym}${reason ? ' | '+reason : ''}`
  };
}


function healthTier(score, status){
  const n=Number(score||0);
  const s=String(status||'').toUpperCase();

  if(s.includes('EXIT') || n<50){
    return {label:'EXIT', cls:'health-exit'};
  }

  if(s.includes('WARNING') || n<70){
    return {label:'WARNING', cls:'health-warning'};
  }

  if(n>=90){
    return {label:'SAFE+', cls:'health-safe-plus'};
  }

  return {label:'SAFE', cls:'health-safe'};
}

function renderHealthBadge(state){
  if(!state){
    return `
      <div class="f-row follower-health-row health-neutral">
        <b>--</b>
        <strong>--</strong>
      </div>
    `;
  }

  const score=Number(state.health_score||0);
  const tier=healthTier(score, state.status);

  return `
    <div class="f-row follower-health-row ${tier.cls}" title="Risk ${fmtNum(state.reversal_risk,0)}">
      <b>${tier.label}</b>
      <strong>${fmtNum(score,0)}</strong>
    </div>
  `;
}

function renderBTCHealth(symbolStates){
  const state=symbolStates ? symbolStates.BTCUSDT : null;
  const box=document.getElementById('btc-health-box');
  const label=document.getElementById('btc-health-label');
  const score=document.getElementById('btc-health-score');
  const risk=document.getElementById('btc-risk-score');

  if(!box || !label || !score || !risk) return;

  if(!state){
    box.className='btc-health-box health-neutral';
    label.textContent='--';
    score.textContent='--';
    risk.textContent='--';
    return;
  }

  const tier=healthTier(state.health_score, state.status);
  box.className=`btc-health-box ${tier.cls}`;
  label.textContent=tier.label;
  score.textContent=fmtNum(state.health_score,0);
  risk.textContent=fmtNum(state.reversal_risk,0);
}

function renderPerformance(p){
  if(!p) return;

  const eqPct=document.getElementById('perf-equity-pct');
  const realized=document.getElementById('perf-realized');
  const openPnl=document.getElementById('perf-open-pnl');

  document.getElementById('perf-equity').textContent=fmtEquity(p.equity);

  eqPct.textContent=(Number(p.equity_pct)>=0?'+':'')+Number(p.equity_pct).toFixed(2)+'%';
  eqPct.className=Number(p.equity_pct)>=0?'pos':'neg';

  realized.textContent=fmtMoney(p.realized_pnl);
  realized.className=Number(p.realized_pnl)>=0?'pos':'neg';

  document.getElementById('perf-trades').textContent=`${p.total_trades||0} trades`;
  document.getElementById('perf-winrate').textContent=Number(p.win_rate||0).toFixed(1)+'%';
  document.getElementById('perf-wins').textContent=`${p.wins||0}/${p.total_trades||0} wins`;
  document.getElementById('perf-open-count').textContent=p.open_positions||0;

  openPnl.textContent='Open P/L '+fmtMoney(p.open_pnl);
  openPnl.className=Number(p.open_pnl)>=0?'pos':'neg';
}

function renderBTC(btc){
  if(!btc) return;

  document.getElementById('btc-price').textContent=fmtPrice(btc.price);
  document.getElementById('btc-source').textContent='Live';

  document.getElementById('btc-ls-posit').innerHTML=lsPair(btc.ls_posit_long, btc.ls_posit_short);
  document.getElementById('btc-ls-ratio').innerHTML=lsPair(btc.ls_ratio_long, btc.ls_ratio_short);
  document.getElementById('btc-ls-account').innerHTML=lsPair(btc.ls_account_long, btc.ls_account_short);

  document.getElementById('btc-funding').innerHTML=`<span class="${Number(btc.funding)>=0?'long':'short'}">${fmtFunding(btc.funding)}</span>`;
  document.getElementById('btc-oi').innerHTML=`<span class="long">${fmtOI(btc.oi)}</span>`;
  document.getElementById('btc-vwap').innerHTML=`<span class="long">${fmtPrice(btc.vwap)}</span>`;
  document.getElementById('btc-cvd').innerHTML=cvdDisplay(btc,'BTCUSDT');
}

function renderSignal(sig){
  if(!sig) return;

  const state=document.getElementById('signal-state');
  const rec=document.getElementById('signal-rec');
  const radar=document.getElementById('radar');
  const signalPanel=document.getElementById('signal-panel');

  radar.className='radar neutral';

  if(signalPanel){
    signalPanel.classList.remove('short-panel','long-panel');
  }

  let icon='⚪ ';

  if(sig.state==='BTC_LONG_CROWDED'){
    radar.classList.add('short-signal');

    if(signalPanel){
      signalPanel.classList.add('short-panel');
    }

    icon='🔴 ';
  }
  else if(sig.state==='BTC_SHORT_CROWDED'){
    radar.classList.add('long-signal');

    if(signalPanel){
      signalPanel.classList.add('long-panel');
    }

    icon='🟢 ';
  }

  state.textContent=icon+sig.state;
  rec.textContent=sig.recommendation;

  document.getElementById('sig-score').textContent=fmtNum(sig.score,1)+'%';
  document.getElementById('sig-spread').textContent=fmtNum(sig.spread,1)+'%';
  document.getElementById('sig-votes').innerHTML=`<span class="long">L ${sig.long_votes}</span> / <span class="short">S ${sig.short_votes}</span>`;
}

function renderFollowers(rows, symbolStates={}){
  const body=document.getElementById('followers-body');
  body.innerHTML='';
  (rows||[]).forEach((r,idx)=>{
    const symbol=shortSym(r.symbol);
    const icon=coinIcon(r.symbol);
    const monitorState=symbolStates ? symbolStates[String(r.symbol||'').toUpperCase()] : null;
    const card=document.createElement('div');
    card.className='follower-card';
    if(idx>=2) card.classList.add('second-row');
    card.innerHTML=`
      <div class="follower-head">
        <div><span class="coin-icon coin-${symbol.toLowerCase()}">${icon}</span> <span class="follower-symbol">${symbol}</span></div>
        <div class="follower-price">${fmtPrice(r.price)}</div>
      </div>
      <div class="f-row"><span>Score</span><span class="score-pill ${scoreClass(r.follow_score)}">${fmtNum(r.follow_score,1)}</span></div>
      <div class="f-row"><span>LS_POS</span>${lsCompact(r.ls_posit_long,r.ls_posit_short)}</div>
      <div class="f-row"><span>LS_RAT</span>${lsCompact(r.ls_ratio_long,r.ls_ratio_short)}</div>
      <div class="f-row"><span>LS_ACC</span>${lsCompact(r.ls_account_long,r.ls_account_short)}</div>
      <div class="f-row"><span>Funding</span><span class="${Number(r.funding)>=0?'long':'short'}">${fmtFunding(r.funding)}</span></div>
      <div class="f-row"><span>OI</span><span>${fmtOI(r.oi)}</span></div>
      <div class="f-row cvd-row"><span>CVD</span>${cvdDisplay(r,r.symbol)}</div>
      ${renderHealthBadge(monitorState)}`;
    body.appendChild(card);
  });
}


function nextFundingValue(row){
  if(!row) return null;
  const keys=['next_funding','next_funding_rate','predicted_funding','predicted_funding_rate','funding_next','funding_predicted'];
  for(const k of keys){
    if(row[k]!==null && row[k]!==undefined && !Number.isNaN(Number(row[k]))) return Number(row[k]);
  }
  return null;
}

function consensusState(score){
  const n=Number(score||0);
  if(n>=100) return 'EXTREME';
  if(n>=75) return 'HIGH';
  if(n>=50) return 'MODERATE';
  if(n>=25) return 'LOW';
  return 'NONE';
}

function consensusClass(state){
  const s=String(state||'').toUpperCase();
  if(s==='EXTREME') return 'consensus-extreme';
  if(s==='HIGH') return 'consensus-high';
  if(s==='MODERATE') return 'consensus-moderate';
  if(s==='LOW') return 'consensus-low';
  return 'consensus-none';
}

function fundingAgreement(current,next){
  if(current===null||current===undefined||Number.isNaN(Number(current))||next===null||next===undefined||Number.isNaN(Number(next))) return 'UNKNOWN';
  const cur=Number(current), nxt=Number(next);
  const thr=0.00005;
  if(cur>=thr && nxt>=thr) return 'POSITIVE_STRONG';
  if(cur<=-thr && nxt<=-thr) return 'NEGATIVE_STRONG';
  if(cur>0 && nxt>0) return 'POSITIVE_WEAK';
  if(cur<0 && nxt<0) return 'NEGATIVE_WEAK';
  if(cur>0 && nxt<0) return 'POS_TO_NEG';
  if(cur<0 && nxt>0) return 'NEG_TO_POS';
  return 'MIXED';
}

function buildFollowersConsensus(rows){
  const symbols=(rows||[]).map(r=>{
    const curFunding=(r&&r.funding!==null&&r.funding!==undefined&&!Number.isNaN(Number(r.funding)))?Number(r.funding):null;
    const nxtFunding=nextFundingValue(r);
    const lsLong=(r&&r.ls_posit_long!==null&&r.ls_posit_long!==undefined&&!Number.isNaN(Number(r.ls_posit_long)))?Number(r.ls_posit_long):null;
    const lsShort=(r&&r.ls_posit_short!==null&&r.ls_posit_short!==undefined&&!Number.isNaN(Number(r.ls_posit_short)))?Number(r.ls_posit_short):null;
    const shortOk=lsLong!==null && lsLong>=65 && curFunding!==null && curFunding>=0.00005 && nxtFunding!==null && nxtFunding>=0.00005;
    const longOk=lsShort!==null && lsShort>=65 && curFunding!==null && curFunding<=-0.00005 && nxtFunding!==null && nxtFunding<=-0.00005;
    return {
      symbol:r.symbol,
      short_score:shortOk?25:0,
      long_score:longOk?25:0,
      short_ok:shortOk,
      long_ok:longOk,
      ls_posit_long:lsLong,
      ls_posit_short:lsShort,
      current_funding:curFunding,
      next_funding:nxtFunding,
      funding_agreement:fundingAgreement(curFunding,nxtFunding),
    };
  });
  const shortScore=symbols.reduce((a,r)=>a+Number(r.short_score||0),0);
  const longScore=symbols.reduce((a,r)=>a+Number(r.long_score||0),0);
  const summary={
    positive_agreements:symbols.filter(r=>String(r.funding_agreement).startsWith('POSITIVE')).length,
    negative_agreements:symbols.filter(r=>String(r.funding_agreement).startsWith('NEGATIVE')).length,
    strong_agreements:symbols.filter(r=>['POSITIVE_STRONG','NEGATIVE_STRONG'].includes(String(r.funding_agreement))).length,
    transitions:symbols.filter(r=>['POS_TO_NEG','NEG_TO_POS'].includes(String(r.funding_agreement))).length,
    unknown:symbols.filter(r=>String(r.funding_agreement)==='UNKNOWN').length,
  };
  return {
    short:{score:shortScore,state:consensusState(shortScore)},
    long:{score:longScore,state:consensusState(longScore)},
    funding_summary:summary,
    symbols,
  };
}

function consensusBar(score){
  const n=Math.max(0,Math.min(100,Number(score||0)));
  return `<div class="consensus-bar"><span style="width:${n}%"></span></div>`;
}

function fundingAgreementLabel(v){
  const s=String(v||'UNKNOWN').toUpperCase();
  const map={
    POSITIVE_STRONG:'POS STRONG',
    POSITIVE_WEAK:'POS WEAK',
    NEGATIVE_STRONG:'NEG STRONG',
    NEGATIVE_WEAK:'NEG WEAK',
    POS_TO_NEG:'POS→NEG',
    NEG_TO_POS:'NEG→POS',
    MIXED:'MIXED',
    UNKNOWN:'UNKNOWN',
  };
  return map[s] || s;
}

function fundingAgreementClass(v){
  const s=String(v||'UNKNOWN').toUpperCase();
  if(s==='POSITIVE_STRONG') return 'funding-pos-strong';
  if(s==='NEGATIVE_STRONG') return 'funding-neg-strong';
  if(s.includes('WEAK')) return 'funding-weak';
  if(s.includes('_TO_')) return 'funding-transition';
  return 'funding-unknown';
}

function renderConsensusSide(title, data, key){
  const score=Number((data&&data.score)||0);
  const state=(data&&data.state)||consensusState(score);
  const cls=consensusClass(state);
  return `
    <div class="consensus-side ${cls}">
      <div class="consensus-side-head">
        <span>${title}</span>
        <b>${score} / 100</b>
      </div>
      <strong>${state}</strong>
      ${consensusBar(score)}
    </div>
  `;
}

function renderFollowersConsensus(consensus, fallbackRows){
  const box=document.getElementById('followers-consensus-panel');
  if(!box) return;
  const data=consensus || buildFollowersConsensus(fallbackRows||[]);
  const rows=data.symbols || [];
  const summary=data.funding_summary || {};

  const symbolRows=rows.map(r=>`
    <tr>
      <td>${shortSym(r.symbol)}</td>
      <td class="${Number(r.short_score)>0?'short':'muted'}">${Number(r.short_score||0)}</td>
      <td class="${Number(r.long_score)>0?'long':'muted'}">${Number(r.long_score||0)}</td>
      <td class="long">L ${fmtPct(r.ls_posit_long)}</td>
      <td class="short">S ${fmtPct(r.ls_posit_short)}</td>
      <td>${fmtFunding(r.current_funding)}</td>
      <td>${fmtFunding(r.next_funding)}</td>
      <td><span class="funding-agreement ${fundingAgreementClass(r.funding_agreement)}">${fundingAgreementLabel(r.funding_agreement)}</span></td>
    </tr>
  `).join('');

  box.innerHTML=`
    <div class="consensus-header"><h2>🧠 Followers Consensus</h2></div>
    <div class="consensus-top">
      ${renderConsensusSide('SHORT', data.short, 'short')}
      ${renderConsensusSide('LONG', data.long, 'long')}
      <div class="consensus-summary">
        <div><small>Positive</small><b>${summary.positive_agreements ?? 0}</b></div>
        <div><small>Negative</small><b>${summary.negative_agreements ?? 0}</b></div>
        <div><small>Strong</small><b>${summary.strong_agreements ?? 0}</b></div>
        <div><small>Transition</small><b>${summary.transitions ?? 0}</b></div>
      </div>
    </div>
    <div class="consensus-table-wrap">
      <table class="consensus-table">
        <thead>
          <tr><th>Symbol</th><th>Short</th><th>Long</th><th>LS Long</th><th>LS Short</th><th>Current F</th><th>Next F</th><th>Agreement</th></tr>
        </thead>
        <tbody>${symbolRows || '<tr><td colspan="8" class="muted">Waiting for followers data</td></tr>'}</tbody>
      </table>
    </div>
  `;
}

function renderTrades(openRows, closedRows){
  const ob=document.getElementById('open-trades');
  ob.innerHTML='';

  if(!openRows || openRows.length===0){
    ob.innerHTML='<tr class="empty-row"><td colspan="10">No open trades</td></tr>';
  }
  else {
    for(const t of openRows){
      const tr=document.createElement('tr');
      const j=fmtJudgment(t.decision_judgment);
      const monitor=fmtMonitorAlert(t.monitor_alert);

      tr.innerHTML=`
        <td data-label="Symbol">${shortSym(t.symbol)}</td>
        <td data-label="Direction" class="${t.direction==='LONG'?'long':'short'}">${t.direction}</td>
        <td data-label="Size">${fmtSize(t.size_usd)}</td>
        <td data-label="Judgment">
          <span class="judgment-pill" title="${j.title}">
            ${j.icon}
          </span>
        </td>
        <td data-label="Monitor">
          <span class="judgment-pill ${monitor.cls}" title="${monitor.title}">
            ${monitor.text}
          </span>
        </td>
        <td data-label="Entry">${fmtPrice(t.entry_price)}</td>
        <td data-label="Current">${fmtPrice(t.current_price)}</td>
        <td data-label="PnL $" class="${clsPnl(t.pnl_usd)}">${fmtNum(t.pnl_usd,2)}</td>
        <td data-label="PnL %" class="${clsPnl(t.pnl_pct)}">${fmtNum(t.pnl_pct,2)}%</td>
        <td data-label="Action"><button class="close-btn" onclick="closeTrade(${t.id})">Close</button></td>
      `;

      ob.appendChild(tr);
    }
  }

  const cb=document.getElementById('closed-trades');
  cb.innerHTML='';

  if(!closedRows || closedRows.length===0){
    cb.innerHTML='<tr class="empty-row"><td colspan="8">No closed trades</td></tr>';
  }
  else {
    for(const t of closedRows){
      const tr=document.createElement('tr');
      const j=fmtJudgment(t.decision_judgment);

      tr.innerHTML=`
        <td data-label="Symbol">${shortSym(t.symbol)}</td>
        <td data-label="Direction" class="${t.direction==='LONG'?'long':'short'}">${t.direction}</td>
        <td data-label="Size">${fmtSize(t.size_usd)}</td>
        <td data-label="Judgment">
          <span class="judgment-pill" title="${j.title}">
            ${j.icon}
          </span>
        </td>
        <td data-label="Entry">${fmtPrice(t.entry_price)}</td>
        <td data-label="Exit">${fmtPrice(t.exit_price)}</td>
        <td data-label="PnL $" class="${clsPnl(t.pnl_usd)}">${fmtNum(t.pnl_usd,2)}</td>
        <td data-label="PnL %" class="${clsPnl(t.pnl_pct)}">${fmtNum(t.pnl_pct,2)}%</td>
      `;

      cb.appendChild(tr);
    }
  }
}

function renderStatus(st, jobs){
  if(!st) return;

  const latest=jobs && jobs.latest ? jobs.latest : null;
  const hosting=!!latest;

  setText('st-main-label', hosting ? 'Cron Worker' : 'MarketService');
  setText('st-price-label', hosting ? 'Price Overlay' : 'Price Feed');
  setText('st-heavy-label', hosting ? 'SQLite Snapshot' : 'LS Feed');
  setText('st-db-label', hosting ? 'SQLite' : 'Database');

  const cronOk=latest && String(latest.status||'').toLowerCase()==='success';
  const cronAge=latest ? ageFromIso(latest.finished_at) : null;

  setText('st-binance', hosting ? (cronOk ? 'Live' : 'Check') : (st.binance || 'Live'));
  setClass('st-binance', hosting ? (cronOk ? 'ok' : 'warn') : 'ok');

  setText('st-price', st.price_feed || 'Live');
  setClass('st-price', 'ok');

  setText('st-ls', hosting ? (cronAge!==null && cronAge<CRON_REFRESH_SEC*2 ? 'Live' : 'Delayed') : (st.ls_feed || 'Live'));
  setClass('st-ls', hosting ? (cronAge!==null && cronAge<CRON_REFRESH_SEC*2 ? 'ok' : 'warn') : 'ok');

  setText('last-price-age', age(st.last_price_age_sec));
  setText('last-ls-age', hosting && latest ? age(cronAge) : age(st.last_ls_age_sec));
  setText('data-mode', hosting ? 'Hosting' : (st.mock_data?'Mock':'Local'));

  const priceTop=document.getElementById('price-age-top');
  if(priceTop) priceTop.textContent=countdown(Math.min(Number(st.last_price_age_sec||0), 599));

  const cronTop=document.getElementById('cron-countdown');
  if(cronTop) cronTop.textContent=latest ? countdown(cronCountdownFromJob(latest)) : countdown(st.ls_countdown_sec);

  const oldLs=document.getElementById('ls-countdown');
  if(oldLs) oldLs.textContent=latest ? countdown(cronCountdownFromJob(latest)) : countdown(st.ls_countdown_sec);
}
function renderSpreadTrend(data){
  if(!data) return;

  const now=document.getElementById('spread-now');
  const history=document.getElementById('spread-history');
  const status=document.getElementById('spread-direction');
  const card=status ? status.closest('.insight-card') : null;

  const spread = Number(data.now || 0);
  let label='LOW';
  let cardState='state-low';

  if(spread >= 30){
    label='EXTREME';
    cardState='state-extreme';
  }
  else if(spread >= 20){
    label='HIGH';
    cardState='state-high';
  }
  else if(spread >= 10){
    label='NORMAL';
    cardState='state-normal';
  }

  setInsightState(card, cardState);

  if(now){
    now.textContent =
      data.now !== null && data.now !== undefined
        ? Number(data.now).toFixed(1) + '%'
        : '--';
    now.className = `insight-main-value ${cardState}`;
  }

  if(history){
    const h1 = data.one_hour !== null && data.one_hour !== undefined
      ? Number(data.one_hour).toFixed(1) + '%'
      : '--';
    const h4 = data.four_hour !== null && data.four_hour !== undefined
      ? Number(data.four_hour).toFixed(1) + '%'
      : '--';
    history.textContent = `1H ${h1} / 4H ${h4}`;
    history.className = 'muted insight-sub-value';
  }

  if(status){
    status.textContent = label;
    status.className = statusBadgeClass('spread', label);
  }
}

function renderExitMonitor(data){
  if(!data) return;

  const ls=document.getElementById('exit-ls-posit');
  const distance=document.getElementById('exit-distance');
  const status=document.getElementById('exit-status');
  const card=status ? status.closest('.insight-card') : null;
  const label=String(data.status || '--').toUpperCase();

  let cardState='state-neutral';
  if(label.includes('SAFE')) cardState='state-safe';
  else if(label.includes('WARNING')) cardState='state-warning';
  else if(label.includes('EXIT')) cardState='state-danger';

  setInsightState(card, cardState);

  if(ls){
    ls.textContent =
      data.btc_ls_posit !== null && data.btc_ls_posit !== undefined
        ? Number(data.btc_ls_posit).toFixed(1) + '%'
        : '--';
  }

  if(distance){
    if(data.health_score !== null && data.health_score !== undefined){
      const health=Number(data.health_score).toFixed(0);
      const risk=data.reversal_risk !== null && data.reversal_risk !== undefined
        ? Number(data.reversal_risk).toFixed(0)
        : '--';
      distance.textContent = 'Health ' + health + ' / Risk ' + risk;
    }
    else{
      distance.textContent =
        data.distance !== null && data.distance !== undefined
          ? 'Buffer ' + Number(data.distance).toFixed(1) + '%'
          : '--';
    }
    distance.className = 'muted insight-sub-value';
  }

  if(status){
    status.textContent = label;
    status.className = statusBadgeClass('exit', label);
  }
}

function renderJobsStatus(data){
  if(!data) return;
  const latest=data.latest || null;
  const jobs=Array.isArray(data.jobs) ? data.jobs : [];

  setText('logs-job-status', latest ? String(latest.status||'--').toUpperCase() : '--');
  setText('logs-job-rows', latest ? String(latest.rows_saved ?? '--') : '--');
  setText('logs-job-duration', latest && latest.duration_ms!==null && latest.duration_ms!==undefined ? (Number(latest.duration_ms)/1000).toFixed(2)+'s' : '--');
  setText('logs-job-finished', latest && latest.finished_at ? new Date(latest.finished_at).toLocaleString() : '--');

  const body=document.getElementById('jobs-log-body');
  if(!body) return;

  if(!jobs.length){
    body.innerHTML='<tr class="empty-row"><td colspan="5">No Cron history yet.</td></tr>';
    return;
  }

  body.innerHTML=jobs.map(j=>{
    const status=String(j.status||'--').toUpperCase();
    const cls=status==='SUCCESS'?'ok':(status==='FAILED'?'bad':'warn');
    const started=j.started_at ? new Date(j.started_at).toLocaleString() : '--';
    const dur=j.duration_ms!==null && j.duration_ms!==undefined ? (Number(j.duration_ms)/1000).toFixed(2)+'s' : '--';
    return `<tr>
      <td>${started}</td>
      <td><span class="${cls}">${status}</span></td>
      <td>${j.rows_saved ?? '--'}</td>
      <td>${dur}</td>
      <td>${j.error || 'None'}</td>
    </tr>`;
  }).join('');
}

async function refresh(){
  try{
    const [stateData, jobsData]=await Promise.all([
      api('/api/state'),
      api('/api/jobs/status').catch(()=>null)
    ]);
    const data=mergePriceFallback(stateData);
    latestJobStatus=jobsData;

    renderBTC(data.btc);
    renderSignal(data.signal);
    renderBTCHealth(data.symbol_states);
    renderFollowers(data.followers, data.symbol_states);
    renderFollowersConsensus(data.followers_consensus, data.followers);
    renderPerformance(data.performance);
    renderTrades(data.open_trades,data.closed_trades);
    renderStatus(data.status, jobsData);
    renderJobsStatus(jobsData);

    lastDashboardState=data;
  }
  catch(e){
    console.error(e);
  }
}

async function openTrade(direction){
  const symbol=document.getElementById('trade-symbol').value;
  const size_usd=document.getElementById('trade-size').value;

  await api('/api/trades/open',{
    method:'POST',
    body:JSON.stringify({symbol,direction,size_usd})
  });

  refresh();
}

async function closeTrade(id){
  await api(`/api/trades/${id}/close`,{
    method:'POST',
    body:'{}'
  });

  refresh();
}

function setupMobileMenu(){
  const btn=document.getElementById('mobile-menu-btn');
  const sidebar=document.getElementById('sidebar');
  const closeBtn=document.getElementById('sidebar-close');
  const backdrop=document.getElementById('sidebar-backdrop');

  if(!sidebar) return;

  const open=()=>{
    sidebar.classList.add('open');

    if(backdrop) backdrop.classList.add('show');

    document.body.classList.add('menu-open');
  };

  const close=()=>{
    sidebar.classList.remove('open');

    if(backdrop) backdrop.classList.remove('show');

    document.body.classList.remove('menu-open');
  };

  if(btn) btn.addEventListener('click', open);
  if(closeBtn) closeBtn.addEventListener('click', close);
  if(backdrop) backdrop.addEventListener('click', close);

  window.addEventListener('keydown', (e)=>{
    if(e.key==='Escape') close();
  });

  window.addEventListener('resize', ()=>{
    if(window.innerWidth>992) close();
  });
}

function setupDesktopSidebar(){
  const btn=document.getElementById('desktop-sidebar-toggle');

  if(!btn) return;

  const key='btcradar_sidebar_collapsed';

  if(localStorage.getItem(key)==='1'){
    document.body.classList.add('sidebar-collapsed');
  }

  btn.addEventListener('click',()=>{
    document.body.classList.toggle('sidebar-collapsed');

    localStorage.setItem(
      key,
      document.body.classList.contains('sidebar-collapsed') ? '1' : '0'
    );
  });
}


let latestReport = null;

function setupNavigation(){
  const links=[...document.querySelectorAll('nav a[data-view]')];
  const views=[...document.querySelectorAll('.view-section')];
  const titleEl=document.querySelector('.topbar h1');

  function showView(viewName){
    const target=document.getElementById(`${viewName}-view`);

    if(!target) return;

    views.forEach(view=>{
      view.classList.remove('active-view');
      view.style.display='none';
    });

    target.classList.add('active-view');
    target.style.display='block';

    links.forEach(link=>{
      link.classList.toggle('active', link.dataset.view===viewName);
    });

    const activeLink=links.find(link=>link.dataset.view===viewName);

    if(titleEl && activeLink && activeLink.dataset.title){
      titleEl.innerHTML=`<span class="btc-title-icon">₿</span> ${activeLink.dataset.title.replace('₿ ','')}`;
    }

    if(window.innerWidth<=900){
      const sidebar=document.getElementById('sidebar');
      const backdrop=document.getElementById('sidebar-backdrop');
      if(sidebar) sidebar.classList.remove('open');
      if(backdrop) backdrop.classList.remove('show');
      document.body.classList.remove('menu-open');
    }

    window.scrollTo({top:0, behavior:'smooth'});
  }

  links.forEach(link=>{
    link.addEventListener('click', (e)=>{
      e.preventDefault();
      const viewName=link.dataset.view;
      if(location.hash.replace('#','')!==viewName){
        location.hash=viewName;
      }
      else{
        showView(viewName);
      }
    });
  });

  const initial=location.hash ? location.hash.replace('#','') : 'dashboard';
  showView(document.getElementById(`${initial}-view`) ? initial : 'dashboard');

  window.addEventListener('hashchange', ()=>{
    const view=location.hash.replace('#','') || 'dashboard';
    showView(document.getElementById(`${view}-view`) ? view : 'dashboard');
  });
}

function setupReportsCenter(){
  const generateBtn=document.getElementById('report-generate');
  const printBtn=document.getElementById('report-print');
  const csvBtn=document.getElementById('report-csv');
  const jsonBtn=document.getElementById('report-json');

  if(generateBtn) generateBtn.addEventListener('click', generateReport);
  if(printBtn) printBtn.addEventListener('click', () => window.print());
  if(csvBtn) csvBtn.addEventListener('click', downloadReportCsv);
  if(jsonBtn) jsonBtn.addEventListener('click', downloadReportJson);

  const allSymbol=document.querySelector('.report-symbol[value="ALL"]');
  const symbolBoxes=[...document.querySelectorAll('.report-symbol')].filter(x=>x.value!=='ALL');

  if(allSymbol){
    allSymbol.addEventListener('change',()=>{
      if(allSymbol.checked){
        symbolBoxes.forEach(x=>x.checked=false);
      }
    });
  }

  symbolBoxes.forEach(box=>{
    box.addEventListener('change',()=>{
      if(box.checked && allSymbol) allSymbol.checked=false;
      if(!symbolBoxes.some(x=>x.checked) && allSymbol) allSymbol.checked=true;
    });
  });
}

function getReportOptions(){
  const period=document.querySelector('input[name="report-period"]:checked')?.value || '30d';
  const sections=[...document.querySelectorAll('.report-section:checked')].map(x=>x.value);
  const symbols=[...document.querySelectorAll('.report-symbol:checked')].map(x=>x.value);

  return {
    period,
    sections: sections.length ? sections : ['performance','spread','judgment','symbol','equity'],
    symbols: symbols.length ? symbols : ['ALL']
  };
}

async function generateReport(){
  const output=document.getElementById('report-output');
  if(output){
    output.innerHTML='<div class="report-empty">Generating report...</div>';
  }

  try{
    latestReport=await api('/api/reports/generate',{
      method:'POST',
      body:JSON.stringify(getReportOptions())
    });
    renderReport(latestReport);
  }
  catch(e){
    console.error(e);
    if(output){
      output.innerHTML='<div class="report-empty">Failed to generate report. Check console/logs.</div>';
    }
  }
}

function fmtReportMoney(v){
  return fmtMoney(v||0);
}

function fmtReportPct(v){
  if(v===null||v===undefined||Number.isNaN(Number(v))) return '--';
  return Number(v).toFixed(2)+'%';
}

function renderReport(report){
  const output=document.getElementById('report-output');
  if(!output || !report) return;

  const p=report.performance || {};
  let html=`
    <div class="report-title-row">
      <div>
        <h2>BTCRadar Validation Report</h2>
        <p>Period: <b>${report.period}</b> · Trades: <b>${report.trade_count || 0}</b> · Generated: ${new Date(report.generated_at).toLocaleString()}</p>
      </div>
    </div>
  `;

  html += `
    <section class="report-section-card">
      <h3>Performance Summary</h3>
      <div class="report-kpi-grid">
        <div><small>Trades</small><strong>${p.trades||0}</strong></div>
        <div><small>Win Rate</small><strong>${fmtReportPct(p.win_rate)}</strong></div>
        <div><small>Net P/L</small><strong class="${Number(p.net_pnl||0)>=0?'pos':'neg'}">${fmtReportMoney(p.net_pnl)}</strong></div>
        <div><small>Profit Factor</small><strong>${fmtNum(p.profit_factor,2)}</strong></div>
        <div><small>Avg Winner</small><strong class="pos">${fmtReportPct(p.avg_winner_pct)}</strong></div>
        <div><small>Avg Loser</small><strong class="neg">${fmtReportPct(p.avg_loser_pct)}</strong></div>
      </div>
    </section>
  `;

  if(report.spread_analysis){
    html += renderReportTable(
      'Spread Analysis',
      ['Spread Zone','Trades','Win Rate','Net P/L','Avg P/L %'],
      report.spread_analysis.map(r=>[r.label,r.trades,fmtReportPct(r.win_rate),fmtReportMoney(r.net_pnl),fmtReportPct(r.avg_pnl_pct)])
    );
  }

  if(report.judgment_analysis){
    html += renderReportTable(
      'Judgment Analysis',
      ['Judgment','Trades','Win Rate','Net P/L','Avg P/L %'],
      report.judgment_analysis.map(r=>[r.label,r.trades,fmtReportPct(r.win_rate),fmtReportMoney(r.net_pnl),fmtReportPct(r.avg_pnl_pct)])
    );
  }

  if(report.symbol_analysis){
    html += renderReportTable(
      'Symbol Analysis',
      ['Symbol','Trades','Win Rate','Net P/L','Avg P/L %'],
      report.symbol_analysis.map(r=>[shortSym(r.label),r.trades,fmtReportPct(r.win_rate),fmtReportMoney(r.net_pnl),fmtReportPct(r.avg_pnl_pct)])
    );
  }

  if(report.equity_curve){
    html += `
      <section class="report-section-card">
        <h3>Equity Curve</h3>
        ${renderEquitySvg(report.equity_curve)}
      </section>
    `;
  }

  if(report.conclusions && report.conclusions.length){
    html += `
      <section class="report-section-card">
        <h3>Conclusions</h3>
        <ul class="report-conclusions">
          ${report.conclusions.map(x=>`<li>${x}</li>`).join('')}
        </ul>
      </section>
    `;
  }

  output.innerHTML=html;
}

function renderReportTable(title, headers, rows){
  return `
    <section class="report-section-card">
      <h3>${title}</h3>
      <div class="report-table-wrap">
        <table class="report-table">
          <thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead>
          <tbody>
            ${rows.length ? rows.map(r=>`<tr>${r.map(c=>`<td>${c}</td>`).join('')}</tr>`).join('') : `<tr><td colspan="${headers.length}">No data</td></tr>`}
          </tbody>
        </table>
      </div>
    </section>
  `;
}

function renderEquitySvg(points){
  if(!points || points.length===0) return '<div class="report-empty">No equity data.</div>';

  const width=760, height=220, pad=26;
  const values=points.map(p=>Number(p.equity||0));
  const min=Math.min(...values), max=Math.max(...values);
  const span=(max-min)||1;

  const coords=points.map((p,i)=>{
    const x=pad + (points.length===1 ? 0 : i*(width-pad*2)/(points.length-1));
    const y=height-pad - ((Number(p.equity||0)-min)/span)*(height-pad*2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');

  return `
    <svg class="equity-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Equity Curve">
      <line x1="${pad}" y1="${height-pad}" x2="${width-pad}" y2="${height-pad}" />
      <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${height-pad}" />
      <polyline points="${coords}" />
      <text x="${pad}" y="18">High: $${max.toFixed(2)}</text>
      <text x="${pad}" y="${height-6}">Low: $${min.toFixed(2)}</text>
    </svg>
  `;
}

function downloadReportJson(){
  if(!latestReport) return;
  downloadBlob(JSON.stringify(latestReport,null,2),'btcradar_report.json','application/json');
}

function downloadReportCsv(){
  if(!latestReport) return;
  const rows=[];
  rows.push(['Section','Label','Trades','Win Rate','Net PnL','Avg PnL %']);

  for(const section of ['spread_analysis','judgment_analysis','symbol_analysis']){
    for(const r of latestReport[section] || []){
      rows.push([section,r.label,r.trades,r.win_rate,r.net_pnl,r.avg_pnl_pct]);
    }
  }

  const csv=rows.map(r=>r.map(c=>`"${String(c??'').replaceAll('"','""')}"`).join(',')).join('\n');
  downloadBlob(csv,'btcradar_report.csv','text/csv');
}

function downloadBlob(content, filename, type){
  const blob=new Blob([content],{type});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');
  a.href=url;
  a.download=filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function fmtDelta(v, digits=2){
  if(v===null||v===undefined||Number.isNaN(Number(v))) return '--';
  const n=Number(v);
  const sign=n>0?'+':'';
  return sign+n.toFixed(digits);
}

function fmtCompact(v){
  if(v===null||v===undefined||Number.isNaN(Number(v))) return '--';
  const n=Number(v);
  const abs=Math.abs(n);
  if(abs>=1e9) return (n/1e9).toFixed(2)+'B';
  if(abs>=1e6) return (n/1e6).toFixed(2)+'M';
  if(abs>=1e3) return (n/1e3).toFixed(2)+'K';
  return n.toFixed(2);
}

function fmtUnix(ts){
  if(!ts) return '--';
  try{
    return new Date(Number(ts)*1000).toLocaleString();
  }
  catch(e){
    return '--';
  }
}

function fmtFundingPct(v){
  if(v===null||v===undefined||Number.isNaN(Number(v))) return '--';
  return Number(v).toFixed(5)+'%';
}

function fmtPctDelta(v){
  if(v===null||v===undefined||Number.isNaN(Number(v))) return '--';
  const n=Number(v);
  const sign=n>0?'+':'';
  return sign+n.toFixed(2)+'%';
}

function safeText(v, fallback='--'){
  if(v===null||v===undefined||v==='') return fallback;
  return String(v);
}

function trendClass(label){
  const v=String(label||'').toUpperCase();
  if(v.includes('RISING') || v.includes('BUILDING') || v.includes('EARLY') || v.includes('DEVELOPING') || v.includes('ACTIVE')) return 'pos';
  if(v.includes('FALLING') || v.includes('LATE') || v.includes('AFTER') || v.includes('SPIKE') || v.includes('COOLING') || v.includes('HAPPENED')) return 'neg';
  if(v.includes('ELEVATED') || v.includes('PRESSURE')) return 'warning';
  return 'muted';
}

function timingClass(label){
  const v=String(label||'').toUpperCase();
  if(v==='EARLY' || v==='DEVELOPING') return 'timing-good';
  if(v==='LATE' || v==='WAIT') return 'timing-warn';
  if(v==='AFTER FLUSH') return 'timing-bad';
  return 'timing-neutral';
}

function painClass(score){
  const n=Number(score||0);
  if(n>=75) return 'pain-high';
  if(n>=50) return 'pain-mid';
  if(n>=25) return 'pain-low';
  return 'pain-none';
}

function renderCoinalyzeState(data){
  const status=data?.status||{};
  const rows=Array.isArray(data?.rows) ? data.rows : [];

  const set=(id,val,cls)=>{
    const el=document.getElementById(id);
    if(!el) return;
    el.textContent=val;
    if(cls) el.className=cls;
  };

  set('coinalyze-enabled', status.enabled?'Live':'Off', status.enabled?'ok':'bad');
  set('coinalyze-configured', status.configured?'Configured':'Missing', status.configured?'ok':'bad');
  set('coinalyze-refresh-min', `${status.refresh_minutes||'--'} min`);
  set('coinalyze-last-refresh', status.last_refresh_at ? new Date(status.last_refresh_at).toLocaleString() : '--');
  set('coinalyze-rows-saved', status.last_rows_saved ?? '--');
  set('coinalyze-error', status.last_error || 'None', status.last_error?'bad':'ok');

  const body=document.getElementById('coinalyze-body');
  if(!body) return;

  body.innerHTML='';

  if(!rows.length){
    body.innerHTML='<tr class="empty-row"><td colspan="12">No Coinalyze data yet. Wait for the Cron refresh cycle.</td></tr>';
    return;
  }

  for(const row of rows){
    try{
      const latest=row?.latest||{};
      const trend=row?.trend||{};
      const analysis=row?.analysis||{};
      const tr=document.createElement('tr');

      const notes=Array.isArray(analysis.notes) ? analysis.notes.join(' | ') : '';
      tr.title=notes || (latest.ts ? `Last point: ${fmtUnix(latest.ts)}` : 'No data yet');

      const pain=Number(analysis.pain_score||0);
      const entry=safeText(analysis.entry_timing,'WAIT');
      const verdict=safeText(analysis.verdict,'NO CLEAR EDGE');
      const fundingTrend=safeText(analysis.funding_trend,'--');
      const oiTrend=safeText(analysis.oi_trend,'--');
      const liqTrend=safeText(analysis.liquidation_trend,'--');
      const dominant=safeText(analysis.dominant_liquidation,'--');

      tr.innerHTML=`
        <td data-label="Symbol">${shortSym(row.symbol)}</td>
        <td data-label="Funding"><span class="${Number(latest.funding_rate)>=0?'long':'short'}">${fmtFundingPct(latest.funding_rate)}</span></td>
        <td data-label="Funding Trend"><span class="trend-pill ${trendClass(fundingTrend)}">${fundingTrend}</span></td>
        <td data-label="OI">${fmtCompact(latest.oi)}</td>
        <td data-label="OI Trend"><span class="trend-pill ${trendClass(oiTrend)}">${oiTrend} <small>${fmtPctDelta(trend.oi_1h_pct)}</small></span></td>
        <td data-label="Long Liq" class="short">${fmtCompact(latest.long_liquidations)}</td>
        <td data-label="Short Liq" class="long">${fmtCompact(latest.short_liquidations)}</td>
        <td data-label="Dominant"><span class="trend-pill ${trendClass(dominant)}">${dominant}</span></td>
        <td data-label="Liq Trend"><span class="trend-pill ${trendClass(liqTrend)}">${liqTrend}</span></td>
        <td data-label="Pain"><span class="pain-pill ${painClass(pain)}">${pain}</span></td>
        <td data-label="Entry Timing"><span class="timing-pill ${timingClass(entry)}">${entry}</span></td>
        <td data-label="Verdict" class="verdict-cell ${trendClass(verdict)}">${verdict}</td>
      `;

      body.appendChild(tr);
    }
    catch(e){
      console.error('Coinalyze row render failed:', e, row);
    }
  }

  if(!body.children.length){
    body.innerHTML='<tr class="empty-row"><td colspan="12">Coinalyze rows received, but render failed. Check browser console.</td></tr>';
  }
}

async function loadCoinalyzeState(){
  const body=document.getElementById('coinalyze-body');

  try{
    const data=await api('/api/coinalyze/state');
    renderCoinalyzeState(data);
  }
  catch(e){
    console.error('Coinalyze state load failed:', e);
    if(body){
      body.innerHTML='<tr class="empty-row"><td colspan="12">Failed to load Coinalyze data. Check /api/coinalyze/state and server logs.</td></tr>';
    }
  }
}


function fmtMiPct(v){
  if(v===null||v===undefined||Number.isNaN(Number(v))) return '--';
  const n=Number(v);
  return (n>0?'+':'')+n.toFixed(2)+'%';
}

function miCrowdingClass(v){
  const s=String(v||'UNKNOWN').toUpperCase();
  if(s.includes('LONG')) return 'long';
  if(s.includes('SHORT')) return 'short';
  return 'muted';
}

function miLinkClass(v){
  const s=String(v||'').toUpperCase();
  if(s==='STRONG') return 'long';
  if(s==='MEDIUM') return 'pos';
  if(s==='WEAK') return 'warning';
  if(s==='INVERSE') return 'short';
  return 'muted';
}

function fmtRatio(v){
  if(v===null||v===undefined||Number.isNaN(Number(v))) return 'Collecting';
  return fmtNum(v,2)+'x';
}

function miShortSymbol(symbol){
  return shortSym(symbol || '').toUpperCase();
}

function renderMarketMonitor(data){
  if(!data) return;
  const summary=data.summary || {};
  const set=(id,val,cls)=>{
    const el=document.getElementById(id);
    if(!el) return;
    el.textContent=val;
    if(cls) el.className=cls;
  };

  set('mi-session', data.session || '--');
  set('mi-generated', data.generated_at ? new Date(data.generated_at).toLocaleString() : '--');
  set('mi-long-index', fmtNum(summary.market_long_crowding_index,0)+' / 100', 'long');
  set('mi-short-index', fmtNum(summary.market_short_crowding_index,0)+' / 100', 'short');
  set('mi-long-count', `${summary.long_crowded_count||0} crowded / ${summary.long_like_count||0} long-like / ${summary.neutral_count||0} neutral`);
  set('mi-short-count', `${summary.short_crowded_count||0} crowded / ${summary.short_like_count||0} short-like / ${summary.neutral_count||0} neutral`);
  set('mi-funding-now', `${summary.current_funding_positive||0} / ${summary.current_funding_negative||0}`);
  set('mi-funding-next', `${summary.next_funding_positive||0} / ${summary.next_funding_negative||0}`);
  set('mi-story', data.story || '--');

  const body=document.getElementById('mi-table-body');
  if(body){
    const rows=data.rows || [];
    body.innerHTML=rows.length ? rows.map(r=>`
      <tr class="${r.is_driver?'mi-driver-row':''}">
        <td data-label="Symbol"><b>${miShortSymbol(r.symbol)}</b></td>
        <td data-label="Price">${fmtPrice(r.price)}</td>
        <td data-label="1H %" class="${Number(r.price_change_1h_pct)>=0?'pos':'neg'}">${fmtMiPct(r.price_change_1h_pct)}</td>
        <td data-label="4H %" class="${Number(r.price_change_4h_pct)>=0?'pos':'neg'}">${fmtMiPct(r.price_change_4h_pct)}</td>
        <td data-label="24H %" class="${Number(r.price_change_24h_pct)>=0?'pos':'neg'}">${fmtMiPct(r.price_change_24h_pct)}</td>
        <td data-label="BTC React 1H">${r.is_driver?'Driver':fmtRatio(r.reaction_ratio_1h)}</td>
        <td data-label="BTC Link" class="${miLinkClass(r.btc_link_strength)}">${r.btc_link_strength||'--'}</td>
        <td data-label="LS Long" class="long">${fmtPct(r.ls_posit_long)}</td>
        <td data-label="LS Short" class="short">${fmtPct(r.ls_posit_short)}</td>
        <td data-label="Funding" class="${Number(r.funding)>=0?'long':'short'}">${fmtFunding(r.funding)}</td>
        <td data-label="Next F" class="${Number(r.next_funding)>=0?'long':'short'}">${fmtFunding(r.next_funding)}</td>
        <td data-label="OI">${fmtOI(r.oi)}</td>
        <td data-label="CVD 15m" class="${String(r.cvd_trend).toUpperCase()==='RISING'?'long':(String(r.cvd_trend).toUpperCase()==='FALLING'?'short':'muted')}">${r.cvd_trend||'--'} ${r.cvd_delta_15m!==null&&r.cvd_delta_15m!==undefined?'Δ '+fmtSignedNum(r.cvd_delta_15m,0):''}</td>
        <td data-label="Crowding" class="${miCrowdingClass(r.crowding_side)}">${String(r.crowding_side||'UNKNOWN').replaceAll('_',' ')}</td>
        <td data-label="Session Phase">${r.session_phase||'--'}</td>
      </tr>
    `).join('') : '<tr class="empty-row"><td colspan="15">Waiting for market data...</td></tr>';
  }

  const hbox=document.getElementById('mi-hypotheses');
  if(hbox){
    const hs=data.hypotheses || [];
    hbox.innerHTML=hs.length ? hs.map(h=>`
      <div class="mi-hypothesis-card ${String(h.status).toUpperCase()==='ACTIVE'?'active':''}">
        <small>${h.id}</small>
        <strong>${h.name}</strong>
        <b>${h.status}</b>
        <span>${h.evidence||''}</span>
        <em>Triggered: ${h.triggered ?? h.observed ?? 0} · Confirmed: ${h.confirmed ?? 0} · Rejected: ${h.rejected ?? 0}${h.accuracy!==null&&h.accuracy!==undefined ? ' · Accuracy: '+fmtNum(h.accuracy,1)+'%' : ''}${h.last_seen ? ' · Last: '+new Date(h.last_seen).toLocaleString() : ''}</em>
      </div>
    `).join('') : '<div class="muted">Waiting for hypotheses...</div>';
  }

  renderMarketTimeline(data.timeline || []);
  renderSnapshotGroups(data.snapshot_groups || []);
  renderDailyCards(data.daily_cards || []);
}

function renderMarketTimeline(rows){
  const box=document.getElementById('mi-timeline');
  if(!box) return;
  box.innerHTML=rows.length ? rows.map(item=>{
    const fastest=(item.fastest||[]).map(x=>`${miShortSymbol(x.symbol)} ${fmtRatio(x.ratio)}`).join(' · ') || '--';
    const btcCls=Number(item.btc_change_1h_pct)>=0?'pos':'neg';
    return `
      <div class="mi-timeline-item">
        <div>
          <strong>${item.hour ? new Date(item.hour).toLocaleString() : '--'}</strong>
          <small>${item.session||'--'}</small>
        </div>
        <div><small>BTC 1H</small><b class="${btcCls}">${fmtMiPct(item.btc_change_1h_pct)}</b></div>
        <div><small>Bias</small><b>${item.long_like||0}L / ${item.short_like||0}S</b></div>
        <div><small>Fastest</small><b>${fastest}</b></div>
      </div>`;
  }).join('') : '<div class="muted">Waiting for timeline...</div>';
}


function renderDailyCards(cards){
  const box=document.getElementById('mi-daily-cards');
  if(!box) return;
  if(!cards || !cards.length){
    box.innerHTML='<div class="muted">No daily cards yet.</div>';
    return;
  }

  box.innerHTML=cards.map((card)=>{
    const fastest=(card.fastest_1h||[]).map(x=>`${miShortSymbol(x.symbol)} ${fmtRatio(x.ratio)}`).join(' · ') || 'Collecting';
    const sessions=(card.sessions||[]).join(' / ') || 'Collecting';
    const tags=Object.entries(card.hypothesis_tags||{})
      .sort((a,b)=>Number(b[1]||0)-Number(a[1]||0))
      .slice(0,4)
      .map(([k,v])=>`${k} ${v}`)
      .join(' · ') || 'None';
    const timeline=(card.timeline||[]).slice(-24).map(t=>{
      const fastestT=(t.fastest||[]).map(x=>`${miShortSymbol(x.symbol)} ${fmtRatio(x.ratio)}`).join(' · ') || 'Collecting';
      return `<div class="mi-daily-timeline-row">
        <span>${t.hour ? new Date(t.hour).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) : '--'}</span>
        <b class="${Number(t.btc_change_1h_pct)>=0?'pos':'neg'}">BTC ${fmtMiPct(t.btc_change_1h_pct)}</b>
        <span>${t.long_like||0}L / ${t.short_like||0}S</span>
        <span>${fastestT}</span>
      </div>`;
    }).join('');
    const rows=(card.rows||[]).map(r=>`
      <tr>
        <td>${r.snapshot_hour ? new Date(r.snapshot_hour).toLocaleString() : '--'}</td>
        <td>${r.session||'--'}</td>
        <td><b>${miShortSymbol(r.symbol)}</b></td>
        <td>${fmtPrice(r.price)}</td>
        <td class="${Number(r.price_change_1h_pct)>=0?'pos':'neg'}">${fmtMiPct(r.price_change_1h_pct)}</td>
        <td>${fmtRatio(r.reaction_ratio_1h)}</td>
        <td class="${miLinkClass(r.btc_link_strength)}">${r.btc_link_strength||'Collecting'}</td>
        <td class="${miCrowdingClass(r.crowding_side)}">${String(r.crowding_side||'UNKNOWN').replaceAll('_',' ')}</td>
        <td>${r.agreement_with_btc||'--'}</td>
      </tr>
    `).join('');

    return `
      <div class="mi-daily-card" data-day="${card.day||''}">
        <button class="mi-daily-head" type="button" aria-expanded="false">
          <div>
            <strong>${card.day||'--'}</strong>
            <small>${card.snapshot_hours||0} hours · ${sessions}</small>
          </div>
          <div><small>BTC Day</small><b class="${Number(card.btc_day_change_pct)>=0?'pos':'neg'}">${fmtMiPct(card.btc_day_change_pct)}</b></div>
          <div><small>Bias</small><b>${card.long_like_count||0}L / ${card.short_like_count||0}S</b></div>
          <div><small>Funding</small><b>${card.funding_now_positive||0}+ / ${card.funding_now_negative||0}-</b></div>
          <div><small>Fastest</small><b>${fastest}</b></div>
          <div><small>Hypothesis</small><b>${tags}</b></div>
          <span class="mi-daily-toggle">Expand</span>
        </button>
        <div class="mi-daily-body">
          <div class="mi-daily-story">${card.story||'Daily story is collecting more snapshots.'}</div>
          <div class="mi-daily-summary-grid">
            <div><small>Long Crowded</small><b>${card.long_crowded_count||0}</b></div>
            <div><small>Short Crowded</small><b>${card.short_crowded_count||0}</b></div>
            <div><small>Funding Now</small><b>${card.funding_now_positive||0}+ / ${card.funding_now_negative||0}-</b></div>
            <div><small>Funding Next</small><b>${card.funding_next_positive||0}+ / ${card.funding_next_negative||0}-</b></div>
          </div>
          <div class="mi-daily-timeline">
            <h3>Daily Timeline</h3>
            ${timeline || '<div class="muted">Timeline is collecting hourly rows.</div>'}
          </div>
          <div class="mi-table-wrap">
            <table class="mi-table mi-daily-table">
              <thead>
                <tr><th>Hour</th><th>Session</th><th>Symbol</th><th>Price</th><th>1H %</th><th>Reaction</th><th>Link</th><th>Crowding</th><th>Agreement</th></tr>
              </thead>
              <tbody>${rows || '<tr class="empty-row"><td colspan="9">No rows for this day.</td></tr>'}</tbody>
            </table>
          </div>
        </div>
      </div>`;
  }).join('');

  [...box.querySelectorAll('.mi-daily-head')].forEach(btn=>{
    btn.addEventListener('click',()=>{
      const card=btn.closest('.mi-daily-card');
      if(!card) return;
      const isOpen=card.classList.toggle('open');
      btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      const toggle=btn.querySelector('.mi-daily-toggle');
      if(toggle) toggle.textContent=isOpen ? 'Collapse' : 'Expand';
    });
  });
}

function renderSnapshotGroups(groups){
  const logs=document.getElementById('mi-logs-body');
  const detail=document.getElementById('mi-snapshot-detail');
  if(!logs) return;

  const rows=[];
  for(const group of groups){
    for(const r of (group.rows||[])){
      rows.push({...r, _groupHour:group.hour, _groupSession:group.session});
    }
  }

  logs.innerHTML=rows.length ? rows.map((r,idx)=>`
    <tr class="mi-log-row" data-idx="${idx}">
      <td>${r.snapshot_hour ? new Date(r.snapshot_hour).toLocaleString() : '--'}</td>
      <td>${r.session||'--'}</td>
      <td><b>${miShortSymbol(r.symbol)}</b></td>
      <td>${fmtPrice(r.price)}</td>
      <td class="${Number(r.price_change_1h_pct)>=0?'pos':'neg'}">${fmtMiPct(r.price_change_1h_pct)}</td>
      <td>${fmtRatio(r.reaction_ratio_1h)}</td>
      <td class="${miLinkClass(r.btc_link_strength)}">${r.btc_link_strength||'Collecting'}</td>
      <td class="${miCrowdingClass(r.crowding_side)}">${String(r.crowding_side||'UNKNOWN').replaceAll('_',' ')}</td>
      <td>${r.agreement_with_btc||'Collecting'}</td>
    </tr>
  `).join('') : '<tr class="empty-row"><td colspan="9">No hourly snapshots yet.</td></tr>';

  function sameHourRows(selected){
    const h=selected && selected.snapshot_hour;
    if(!h) return [selected].filter(Boolean);
    return rows.filter(x=>x.snapshot_hour===h);
  }

  function findDriver(list){
    return list.find(x=>x.is_driver) || list.find(x=>String(x.symbol||'').toUpperCase().includes('BTC')) || list[0] || {};
  }

  function kv(label, value, cls){
    return `<div><small>${label}</small><b class="${cls||''}">${value}</b></div>`;
  }

  function snapshotStory(selected, driver, peers){
    const sym=miShortSymbol(selected.symbol);
    const btcMove=fmtMiPct(driver.price_change_1h_pct);
    const selectedMove=fmtMiPct(selected.price_change_1h_pct);
    const longLike=peers.filter(x=>String(x.crowding_side||'').includes('LONG')).length;
    const shortLike=peers.filter(x=>String(x.crowding_side||'').includes('SHORT')).length;
    const fastest=peers
      .filter(x=>!x.is_driver && x.reaction_ratio_1h!==null && x.reaction_ratio_1h!==undefined && !Number.isNaN(Number(x.reaction_ratio_1h)))
      .sort((a,b)=>Math.abs(Number(b.reaction_ratio_1h))-Math.abs(Number(a.reaction_ratio_1h)))
      .slice(0,3)
      .map(x=>`${miShortSymbol(x.symbol)} ${fmtRatio(x.reaction_ratio_1h)}`)
      .join(' · ') || 'Collecting';
    return `${sym} snapshot selected. BTC moved ${btcMove} during this hour, while ${sym} moved ${selectedMove}. Followers show ${longLike} long-like vs ${shortLike} short-like. Fastest reactions: ${fastest}.`;
  }

  function rawJsonBlock(row){
    let raw={};
    try{ raw=JSON.parse(row.raw_json || '{}'); }catch(e){ raw=row; }
    return `
      <details class="mi-raw-json">
        <summary>Show Raw JSON</summary>
        <pre>${JSON.stringify(raw,null,2)}</pre>
      </details>`;
  }

  function renderSelectedSnapshot(row){
    if(!detail || !row) return;
    const peers=sameHourRows(row);
    const driver=findDriver(peers);
    const followers=peers.filter(x=>x!==driver && !x.is_driver);
    const selectedIsDriver = row===driver || row.is_driver;
    const selectedTitle = selectedIsDriver ? 'BTC Driver Snapshot' : `${miShortSymbol(row.symbol)} Follower Snapshot`;

    const btcCards = [
      kv('Price', fmtPrice(driver.price)),
      kv('1H', fmtMiPct(driver.price_change_1h_pct), Number(driver.price_change_1h_pct)>=0?'pos':'neg'),
      kv('4H', fmtMiPct(driver.price_change_4h_pct), Number(driver.price_change_4h_pct)>=0?'pos':'neg'),
      kv('24H', fmtMiPct(driver.price_change_24h_pct), Number(driver.price_change_24h_pct)>=0?'pos':'neg'),
      kv('LS Long', fmtPct(driver.ls_posit_long), 'long'),
      kv('LS Short', fmtPct(driver.ls_posit_short), 'short'),
      kv('Funding', fmtFunding(driver.funding), Number(driver.funding)>=0?'long':'short'),
      kv('Next F', fmtFunding(driver.next_funding), Number(driver.next_funding)>=0?'long':'short'),
      kv('OI', fmtOI(driver.oi)),
      kv('Crowding', String(driver.crowding_side||'Collecting').replaceAll('_',' '), miCrowdingClass(driver.crowding_side)),
    ].join('');

    const selectedCards = [
      kv('Price', fmtPrice(row.price)),
      kv('1H', fmtMiPct(row.price_change_1h_pct), Number(row.price_change_1h_pct)>=0?'pos':'neg'),
      kv('BTC React', row.is_driver ? 'Driver' : fmtRatio(row.reaction_ratio_1h)),
      kv('BTC Link', row.is_driver ? 'DRIVER' : (row.btc_link_strength||'Collecting'), miLinkClass(row.btc_link_strength)),
      kv('LS Long', fmtPct(row.ls_posit_long), 'long'),
      kv('LS Short', fmtPct(row.ls_posit_short), 'short'),
      kv('Funding', fmtFunding(row.funding), Number(row.funding)>=0?'long':'short'),
      kv('Next F', fmtFunding(row.next_funding), Number(row.next_funding)>=0?'long':'short'),
      kv('OI', fmtOI(row.oi)),
      kv('Agreement', row.is_driver ? 'DRIVER' : (row.agreement_with_btc||'Collecting')),
    ].join('');

    const followerRows = followers.length ? followers.map(f=>`
      <tr class="${String(f.symbol)===String(row.symbol)?'selected':''}">
        <td><b>${miShortSymbol(f.symbol)}</b></td>
        <td>${fmtPrice(f.price)}</td>
        <td class="${Number(f.price_change_1h_pct)>=0?'pos':'neg'}">${fmtMiPct(f.price_change_1h_pct)}</td>
        <td>${fmtRatio(f.reaction_ratio_1h)}</td>
        <td class="${miLinkClass(f.btc_link_strength)}">${f.btc_link_strength||'Collecting'}</td>
        <td class="long">${fmtPct(f.ls_posit_long)}</td>
        <td class="short">${fmtPct(f.ls_posit_short)}</td>
        <td class="${Number(f.funding)>=0?'long':'short'}">${fmtFunding(f.funding)}</td>
        <td class="${Number(f.next_funding)>=0?'long':'short'}">${fmtFunding(f.next_funding)}</td>
        <td class="${miCrowdingClass(f.crowding_side)}">${String(f.crowding_side||'UNKNOWN').replaceAll('_',' ')}</td>
        <td>${f.agreement_with_btc||'Collecting'}</td>
      </tr>`).join('') : '<tr class="empty-row"><td colspan="11">Followers are collecting for this hour.</td></tr>';

    const hypotheses = [];
    const longLike=followers.filter(x=>String(x.crowding_side||'').includes('LONG')).length;
    const shortLike=followers.filter(x=>String(x.crowding_side||'').includes('SHORT')).length;
    if(longLike>=Math.max(3, shortLike+2)) hypotheses.push(['H001','ACTIVE','Followers long crowding dominates']);
    if(String(driver.crowding_side||'').includes('LONG') && followers.some(x=>String(x.crowding_side||'').includes('LONG_CROWDED'))) hypotheses.push(['H002','ACTIVE','BTC driver / followers stronger crowding']);
    if(followers.some(x=>String(x.crowding_side||'').includes('LONG') && Number(x.funding)<0)) hypotheses.push(['H003','ACTIVE','Long crowding with negative funding divergence']);
    if(followers.some(x=>Number(x.reaction_ratio_1h)>=1.75)) hypotheses.push(['H004','ACTIVE','Fast follower reaction to BTC move']);
    const hypothesisRows = hypotheses.length ? hypotheses.map(h=>`<tr><td>${h[0]}</td><td class="long">${h[1]}</td><td>${h[2]}</td></tr>`).join('') : '<tr><td colspan="3">No active hypothesis detected for this snapshot.</td></tr>';

    detail.classList.remove('muted');
    detail.innerHTML=`
      <div class="mi-snapshot-title">
        <strong>${selectedTitle}</strong>
        <span>${row.snapshot_hour ? new Date(row.snapshot_hour).toLocaleString() : '--'} · ${row.session||'--'}</span>
      </div>

      <div class="mi-snapshot-story">${snapshotStory(row, driver, followers)}</div>

      <h3>BTC State</h3>
      <div class="mi-snapshot-grid">${btcCards}</div>

      <h3>Selected Symbol</h3>
      <div class="mi-snapshot-grid">${selectedCards}</div>

      <h3>Followers at Same Hour</h3>
      <div class="mi-table-wrap">
        <table class="mi-table mi-snapshot-table">
          <thead><tr><th>Symbol</th><th>Price</th><th>1H %</th><th>React</th><th>Link</th><th>LS Long</th><th>LS Short</th><th>Funding</th><th>Next F</th><th>Crowding</th><th>Agreement</th></tr></thead>
          <tbody>${followerRows}</tbody>
        </table>
      </div>

      <h3>Hypotheses</h3>
      <div class="mi-table-wrap">
        <table class="mi-table mi-snapshot-hyp-table">
          <thead><tr><th>ID</th><th>Status</th><th>Reason</th></tr></thead>
          <tbody>${hypothesisRows}</tbody>
        </table>
      </div>

      ${rawJsonBlock(row)}
    `;
  }

  [...logs.querySelectorAll('.mi-log-row')].forEach(tr=>{
    tr.addEventListener('click',()=>{
      const row=rows[Number(tr.dataset.idx)];
      renderSelectedSnapshot(row);
    });
  });
}

async function loadMarketMonitor(){
  const body=document.getElementById('mi-table-body');
  if(!body) return;
  try{
    const data=await api('/api/market-monitor');
    renderMarketMonitor(data);
  }
  catch(e){
    console.error('Market monitor load failed:', e);
    body.innerHTML='<tr class="empty-row"><td colspan="15">Failed to load Market Monitor data. Check /api/market-monitor and server logs.</td></tr>';
  }
}

function setupMarketMonitor(){
  loadMarketMonitor();
  setInterval(loadMarketMonitor, 60000);
}

function setupCoinalyzeAnalytics(){
  const btn=document.getElementById('coinalyze-refresh');

  if(btn){
    btn.addEventListener('click', async ()=>{
      btn.disabled=true;
      btn.textContent='Refreshing...';

      try{
        const result=await api('/api/coinalyze/refresh',{method:'POST',body:'{}'});
        await loadCoinalyzeState();

        if(result && result.cached){
          console.info(result.message || 'Recent Coinalyze data already exists. Manual refresh skipped.');
        }
      }
      catch(e){
        console.error('Coinalyze manual refresh failed:', e);
        alert('Coinalyze refresh failed. Wait a few minutes or check logs/API key.');
      }
      finally{
        btn.disabled=false;
        btn.textContent='Refresh Coinalyze Now';
      }
    });
  }

  loadCoinalyzeState();
  setInterval(loadCoinalyzeState, 60000);
}

setupMobileMenu();
setupDesktopSidebar();
setupNavigation();
setupReportsCenter();
setupMarketMonitor();
setupCoinalyzeAnalytics();

refresh();
setInterval(refresh, 5000);
