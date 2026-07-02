function fmtNum(v, digits=2){
  if(v===null||v===undefined||Number.isNaN(Number(v))) return '--';
  return Number(v).toLocaleString(undefined,{maximumFractionDigits:digits});
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


async function api(url, options={}){
  const r=await fetch(url,{headers:{'Content-Type':'application/json'},...options});
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
  document.getElementById('btc-cvd').innerHTML=`<span class="${Number(btc.cvd)>=0?'long':'short'}">${fmtNum(btc.cvd,0)}</span>`;
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
      <div class="f-row"><span>CVD</span><span class="${Number(r.cvd)>=0?'long':'short'}">${fmtNum(r.cvd,0)}</span></div>
      ${renderHealthBadge(monitorState)}`;
    body.appendChild(card);
  });
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

function renderStatus(st){
  if(!st) return;

  document.getElementById('st-binance').textContent=st.binance;
  document.getElementById('st-price').textContent=st.price_feed;
  document.getElementById('st-ls').textContent=st.ls_feed;

  document.getElementById('last-price-age').textContent=age(st.last_price_age_sec);
  document.getElementById('last-ls-age').textContent=age(st.last_ls_age_sec);
  document.getElementById('data-mode').textContent=st.mock_data?'Mock':'Real';
  document.getElementById('ls-countdown').textContent=countdown(st.ls_countdown_sec);

  const lsAge=Number(st.last_ls_age_sec||0);
  const lsRefresh=Number(st.ls_refresh_sec||300);
  const lsEl=document.getElementById('st-ls');

  if(lsEl){
    lsEl.className=lsAge>(lsRefresh*1.5)?'bad':(lsAge>lsRefresh?'warn':'ok');
  }
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
async function refresh(){
  try{
    const data=await api('/api/state');

    renderBTC(data.btc);
    renderSignal(data.signal);
    renderBTCHealth(data.symbol_states);
    renderFollowers(data.followers, data.symbol_states);
    renderPerformance(data.performance);
    renderTrades(data.open_trades,data.closed_trades);
    renderStatus(data.status);
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
    sections: sections.length ? sections : ['performance','spread','judgment','symbol','duration','btc_health','follower_health','health_matrix','funding','equity'],
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
        <div><small>Avg Duration</small><strong>${p.avg_duration || '--'}</strong></div>
        <div><small>Avg Winner</small><strong class="pos">${fmtReportPct(p.avg_winner_pct)}</strong></div>
        <div><small>Avg Loser</small><strong class="neg">${fmtReportPct(p.avg_loser_pct)}</strong></div>
      </div>
    </section>
  `;

  if(report.spread_analysis){
    html += renderReportTable(
      'Spread Analysis',
      ['Spread Zone','Trades','Win Rate','Net P/L','Avg P/L %','Avg Duration'],
      report.spread_analysis.map(r=>[r.label,r.trades,fmtReportPct(r.win_rate),fmtReportMoney(r.net_pnl),fmtReportPct(r.avg_pnl_pct),r.avg_duration || '--'])
    );
  }

  if(report.judgment_analysis){
    html += renderReportTable(
      'Judgment Analysis',
      ['Judgment','Trades','Win Rate','Net P/L','Avg P/L %','Avg Duration'],
      report.judgment_analysis.map(r=>[r.label,r.trades,fmtReportPct(r.win_rate),fmtReportMoney(r.net_pnl),fmtReportPct(r.avg_pnl_pct),r.avg_duration || '--'])
    );
  }

  if(report.symbol_analysis){
    html += renderReportTable(
      'Symbol Analysis',
      ['Symbol','Trades','Win Rate','Net P/L','Avg P/L %','Avg Duration'],
      report.symbol_analysis.map(r=>[shortSym(r.label),r.trades,fmtReportPct(r.win_rate),fmtReportMoney(r.net_pnl),fmtReportPct(r.avg_pnl_pct),r.avg_duration || '--'])
    );
  }

  if(report.duration_analysis){
    html += renderReportTable(
      'Duration Analysis',
      ['Duration','Trades','Win Rate','Net P/L','Avg P/L %','Avg Duration'],
      report.duration_analysis.map(r=>[r.label,r.trades,fmtReportPct(r.win_rate),fmtReportMoney(r.net_pnl),fmtReportPct(r.avg_pnl_pct),r.avg_duration || '--'])
    );
  }

  if(report.btc_health_analysis){
    html += renderReportTable(
      'BTC Health Analysis',
      ['BTC Health','Trades','Win Rate','Net P/L','Avg P/L %','Avg Duration'],
      report.btc_health_analysis.map(r=>[r.label,r.trades,fmtReportPct(r.win_rate),fmtReportMoney(r.net_pnl),fmtReportPct(r.avg_pnl_pct),r.avg_duration || '--'])
    );
  }

  if(report.follower_health_analysis){
    html += renderReportTable(
      'Follower Health Analysis',
      ['Follower Health','Trades','Win Rate','Net P/L','Avg P/L %','Avg Duration'],
      report.follower_health_analysis.map(r=>[r.label,r.trades,fmtReportPct(r.win_rate),fmtReportMoney(r.net_pnl),fmtReportPct(r.avg_pnl_pct),r.avg_duration || '--'])
    );
  }

  if(report.health_matrix){
    const matrixRows = (report.health_matrix || []).filter(r => Number(r.trades || 0) > 0);
    html += renderReportTable(
      'BTC × Follower Health Matrix',
      ['BTC × Follower','Trades','Win Rate','Net P/L','Avg P/L %','Avg Duration'],
      matrixRows.map(r=>[r.label,r.trades,fmtReportPct(r.win_rate),fmtReportMoney(r.net_pnl),fmtReportPct(r.avg_pnl_pct),r.avg_duration || '--'])
    );
  }

  if(report.funding_analysis){
    html += renderReportTable(
      'Funding Analysis',
      ['Funding Bucket','Trades','Win Rate','Net P/L','Avg P/L %','Avg Duration'],
      report.funding_analysis.map(r=>[r.label,r.trades,fmtReportPct(r.win_rate),fmtReportMoney(r.net_pnl),fmtReportPct(r.avg_pnl_pct),r.avg_duration || '--'])
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
  rows.push(['Section','Label','Trades','Win Rate','Net PnL','Avg PnL %','Avg Duration']);

  for(const section of [
    'spread_analysis',
    'judgment_analysis',
    'symbol_analysis',
    'duration_analysis',
    'btc_health_analysis',
    'follower_health_analysis',
    'health_matrix',
    'funding_analysis'
  ]){
    for(const r of latestReport[section] || []){
      rows.push([section,r.label,r.trades,r.win_rate,r.net_pnl,r.avg_pnl_pct,r.avg_duration || '--']);
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
    body.innerHTML='<tr class="empty-row"><td colspan="12">No Coinalyze data yet. Wait for hourly refresh or click Refresh Coinalyze Now.</td></tr>';
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
setupCoinalyzeAnalytics();

refresh();
setInterval(refresh, 1000);
