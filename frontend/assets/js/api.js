/* ============================================================
   api.js — CTMS Shared JS Layer
   Demo-first: all calls fall back to seed data if service down
   ============================================================ */

/* ── Custom cursor ─────────────────────────────────────────── */
(function initCursor() {
  const el = document.createElement('div');
  el.className = 'cursor';
  document.body.appendChild(el);
  document.addEventListener('mousemove', e => {
    el.style.left = e.clientX + 'px';
    el.style.top  = e.clientY + 'px';
  });
  document.addEventListener('mouseover', e => {
    if (e.target.closest('a,button,[onclick],.concert-card,.seat-av'))
      el.classList.add('grow');
    else el.classList.remove('grow');
  });
})();

/* ── Seed / demo data ──────────────────────────────────────── */
const SEED = {
  concerts: [
    { concertId:'CONC-000001', name:"Taylor Swift — The Eras Tour", artistName:"Taylor Swift", venue:"National Stadium, Singapore", eventDate:"2025-09-14T19:00:00", availableSeats:18430, totalSeats:50000, status:"ACTIVE", currency:"SGD", emoji:"🌟" },
    { concertId:'CONC-000002', name:"Coldplay — Music of the Spheres", artistName:"Coldplay", venue:"Singapore Indoor Stadium", eventDate:"2025-11-22T20:00:00", availableSeats:4210, totalSeats:12000, status:"ACTIVE", currency:"SGD", emoji:"🎸" },
    { concertId:'CONC-000003', name:"Bruno Mars — 24K Magic Live", artistName:"Bruno Mars", venue:"Resorts World Theatre", eventDate:"2025-08-03T21:00:00", availableSeats:0, totalSeats:5000, status:"SOLD_OUT", currency:"SGD", emoji:"🎷" },
    { concertId:'CONC-000004', name:"BTS — Yet To Come", artistName:"BTS", venue:"Singapore Sports Hub", eventDate:"2025-07-05T18:00:00", availableSeats:0, totalSeats:55000, status:"CANCELLED", currency:"SGD", emoji:"💜" },
    { concertId:'CONC-000005', name:"Ed Sheeran — Mathematics Tour", artistName:"Ed Sheeran", venue:"Changi Exhibition Centre", eventDate:"2025-10-18T19:30:00", availableSeats:22100, totalSeats:30000, status:"POSTPONED", currency:"SGD", emoji:"🎵" },
  ],
  categories: {
    'CONC-000001': [
      { categoryId:'CAT-C001-01', categoryName:'CAT 1 — FLOOR / PIT',  totalSeats:5000,  availableSeats:230  },
      { categoryId:'CAT-C001-02', categoryName:'CAT 2 — LOWER TIER',   totalSeats:15000, availableSeats:4100 },
      { categoryId:'CAT-C001-03', categoryName:'CAT 3 — UPPER TIER',   totalSeats:20000, availableSeats:8100 },
      { categoryId:'CAT-C001-04', categoryName:'CAT 4 — GALLERY',      totalSeats:10000, availableSeats:6000 },
    ],
    'CONC-000002': [
      { categoryId:'CAT-C002-01', categoryName:'CAT 1 — FLOOR / PIT',  totalSeats:1500, availableSeats:80   },
      { categoryId:'CAT-C002-02', categoryName:'CAT 2 — LOWER TIER',   totalSeats:4500, availableSeats:930  },
      { categoryId:'CAT-C002-03', categoryName:'CAT 3 — UPPER TIER',   totalSeats:4000, availableSeats:2200 },
      { categoryId:'CAT-C002-04', categoryName:'CAT 4 — GALLERY',      totalSeats:2000, availableSeats:1000 },
    ],
  },
  prices: {
    'CONC-000001': [
      { categoryId:'CAT-C001-01', basePrice:388, resaleCeiling:580, currency:'SGD' },
      { categoryId:'CAT-C001-02', basePrice:248, resaleCeiling:370, currency:'SGD' },
      { categoryId:'CAT-C001-03', basePrice:158, resaleCeiling:235, currency:'SGD' },
      { categoryId:'CAT-C001-04', basePrice:98,  resaleCeiling:145, currency:'SGD' },
    ],
    'CONC-000002': [
      { categoryId:'CAT-C002-01', basePrice:298, resaleCeiling:445, currency:'SGD' },
      { categoryId:'CAT-C002-02', basePrice:188, resaleCeiling:280, currency:'SGD' },
      { categoryId:'CAT-C002-03', basePrice:118, resaleCeiling:175, currency:'SGD' },
      { categoryId:'CAT-C002-04', basePrice:68,  resaleCeiling:100, currency:'SGD' },
    ],
  },
  tickets: [
    { ticketId:'TKT-10001', concertId:'CONC-000001', seatNumber:'F-01-01', categoryId:'CAT-C001-01', ownerId:null,      status:'AVAILABLE',     purchasePrice:null,   resalePrice:null },
    { ticketId:'TKT-10002', concertId:'CONC-000001', seatNumber:'F-01-02', categoryId:'CAT-C001-01', ownerId:'USR-0042', status:'PENDING',       purchasePrice:null,   resalePrice:null },
    { ticketId:'TKT-10003', concertId:'CONC-000001', seatNumber:'F-01-03', categoryId:'CAT-C001-01', ownerId:'USR-0042', status:'CONFIRMED',     purchasePrice:388,    resalePrice:null },
    { ticketId:'TKT-10004', concertId:'CONC-000001', seatNumber:'F-01-04', categoryId:'CAT-C001-01', ownerId:'USR-0099', status:'CONFIRMED',     purchasePrice:388,    resalePrice:null },
    { ticketId:'TKT-10005', concertId:'CONC-000001', seatNumber:'L-03-08', categoryId:'CAT-C001-02', ownerId:null,      status:'AVAILABLE',     purchasePrice:null,   resalePrice:null },
    { ticketId:'TKT-10006', concertId:'CONC-000001', seatNumber:'L-03-09', categoryId:'CAT-C001-02', ownerId:null,      status:'AVAILABLE',     purchasePrice:null,   resalePrice:null },
    { ticketId:'TKT-10007', concertId:'CONC-000001', seatNumber:'L-05-12', categoryId:'CAT-C001-02', ownerId:'USR-0042', status:'CONFIRMED',     purchasePrice:248,    resalePrice:null },
    { ticketId:'TKT-10008', concertId:'CONC-000001', seatNumber:'L-05-13', categoryId:'CAT-C001-02', ownerId:'USR-0303', status:'RESALE_LISTED', purchasePrice:248,    resalePrice:320 },
    { ticketId:'TKT-10009', concertId:'CONC-000001', seatNumber:'L-06-01', categoryId:'CAT-C001-02', ownerId:'USR-0410', status:'RESALE_LISTED', purchasePrice:248,    resalePrice:310 },
    { ticketId:'TKT-10010', concertId:'CONC-000001', seatNumber:'U-10-05', categoryId:'CAT-C001-03', ownerId:null,      status:'AVAILABLE',     purchasePrice:null,   resalePrice:null },
    { ticketId:'TKT-10011', concertId:'CONC-000001', seatNumber:'U-10-06', categoryId:'CAT-C001-03', ownerId:'USR-0601', status:'CONFIRMED',     purchasePrice:158,    resalePrice:null },
    { ticketId:'TKT-10012', concertId:'CONC-000001', seatNumber:'G-01-22', categoryId:'CAT-C001-04', ownerId:null,      status:'AVAILABLE',     purchasePrice:null,   resalePrice:null },
    { ticketId:'TKT-30001', concertId:'CONC-000003', seatNumber:'F-01-01', categoryId:'CAT-C003-01', ownerId:'USR-0042', status:'USED',          purchasePrice:488,    resalePrice:null },
    { ticketId:'TKT-40001', concertId:'CONC-000004', seatNumber:'F-02-01', categoryId:'CAT-C004-01', ownerId:'USR-0042', status:'REFUNDED',      purchasePrice:398,    resalePrice:null },
    { ticketId:'TKT-20001', concertId:'CONC-000002', seatNumber:'F-01-01', categoryId:'CAT-C002-01', ownerId:null,      status:'AVAILABLE',     purchasePrice:null,   resalePrice:null },
    { ticketId:'TKT-20002', concertId:'CONC-000002', seatNumber:'F-01-02', categoryId:'CAT-C002-01', ownerId:null,      status:'AVAILABLE',     purchasePrice:null,   resalePrice:null },
  ],
  resaleListings: [
    { ticketId:'TKT-10008', concertId:'CONC-000001', seatNumber:'L-05-13', categoryId:'CAT-C001-02', ownerId:'USR-0303', resalePrice:320, status:'RESALE_LISTED' },
    { ticketId:'TKT-10009', concertId:'CONC-000001', seatNumber:'L-06-01', categoryId:'CAT-C001-02', ownerId:'USR-0410', resalePrice:310, status:'RESALE_LISTED' },
  ],
  payments: [
    { paymentId:'PAY-40001', userId:'USR-0042', ticketId:'TKT-10003', concertId:'CONC-000001', type:'PURCHASE',        amount:388, currency:'SGD', status:'SUCCESS', createdAt:'2025-05-20T14:30:00Z' },
    { paymentId:'PAY-40002', userId:'USR-0042', ticketId:'TKT-10007', concertId:'CONC-000001', type:'PURCHASE',        amount:248, currency:'SGD', status:'SUCCESS', createdAt:'2025-04-15T16:45:00Z' },
    { paymentId:'PAY-40003', userId:'USR-0042', ticketId:'TKT-30001', concertId:'CONC-000003', type:'PURCHASE',        amount:488, currency:'SGD', status:'SUCCESS', createdAt:'2025-03-01T11:00:00Z' },
    { paymentId:'PAY-40004', userId:'USR-0042', ticketId:'TKT-40001', concertId:'CONC-000004', type:'REFUND',          amount:398, currency:'SGD', status:'SUCCESS', createdAt:'2025-05-30T14:30:00Z' },
  ],
  notifications: [
    { notificationId:'NOTIF-001', userId:'USR-0042', eventType:'ticket.purchased',   subject:'Your ticket is confirmed!',         status:'SENT', channel:'EMAIL', sentAt:'2025-05-20T14:30:00Z' },
    { notificationId:'NOTIF-002', userId:'USR-0042', eventType:'ticket.purchased',   subject:'Your ticket is confirmed!',         status:'SENT', channel:'EMAIL', sentAt:'2025-04-15T16:45:00Z' },
    { notificationId:'NOTIF-003', userId:'USR-0042', eventType:'concert.cancelled',  subject:'Concert Cancelled — Refund Issued', status:'SENT', channel:'EMAIL', sentAt:'2025-05-30T14:31:00Z' },
  ],
};

/* ── API client ─────────────────────────────────────────────── */
const API = (() => {
  const BASE = {
    concert:      'https://<outsystems>.outsystemscloud.com/ConcertAPI/rest/v1',
    pricing:      'http://localhost:5001/pricing/v1',
    queue:        'http://localhost:5002/queue/v1',
    tickets:      'http://localhost:5003/tickets/v1',
    payment:      'http://localhost:5004/payment/v1',
    qr:           'http://localhost:5005/qr/v1',
    notification: 'http://localhost:5006/notification/v1',
    purchase:     'http://localhost:5010/purchase/v1',
    resale:       'http://localhost:5011/resale/v1',
    cancellation: 'http://localhost:5012/cancellation/v1',
  };

  async function req(url, method='GET', body=null) {
    const opts = { method, headers:{'Content-Type':'application/json'} };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(url, { ...opts, signal: AbortSignal.timeout(4000) });
    const data = await res.json().catch(()=>({}));
    if (!res.ok) throw data.error || data;
    return data;
  }

  return {
    concerts: {
      list: async () => { try { return await req(`${BASE.concert}/concerts`); } catch { return { concerts: SEED.concerts }; } },
      get:  async id  => { try { return await req(`${BASE.concert}/concerts/${id}`); } catch { return SEED.concerts.find(c=>c.concertId===id) || null; } },
      seats:async id  => { try { return await req(`${BASE.concert}/concerts/${id}/seats`); } catch { return { categories: SEED.categories[id]||[] }; } },
      update: (id,p)  => req(`${BASE.concert}/concerts/${id}`, 'PUT', p),
      create: p       => req(`${BASE.concert}/concerts`, 'POST', p),
    },
    pricing: {
      list:    async (cid)      => { try { return await req(`${BASE.pricing}/concerts/${cid}/prices`); } catch { return { prices: SEED.prices[cid]||[] }; } },
      get:     async (cid,cat)  => { try { return await req(`${BASE.pricing}/concerts/${cid}/prices/${cat}`); } catch { return (SEED.prices[cid]||[]).find(p=>p.categoryId===cat)||{}; } },
      ceiling: async (cid,cat)  => { try { return await req(`${BASE.pricing}/concerts/${cid}/prices/${cat}/ceiling`); } catch { const p=(SEED.prices[cid]||[]).find(p=>p.categoryId===cat)||{}; return {resaleCeiling:p.resaleCeiling,currency:'SGD'}; } },
      create: (cid,p)           => req(`${BASE.pricing}/concerts/${cid}/prices`, 'POST', p),
    },
    queue: {
      join:   async (cid,p)    => { try { return await req(`${BASE.queue}/queue/${cid}`,'POST',p); } catch { return { queueId:`Q-DEMO`,position:Math.ceil(Math.random()*50)+1,status:'WAITING' }; } },
      status: async (cid,uid)  => { try { return await req(`${BASE.queue}/queue/${cid}/${uid}`); } catch { return { status:'WAITING', position:Math.ceil(Math.random()*30)+1, estimatedWaitMins:15 }; } },
      depth:  async cid        => { try { return await req(`${BASE.queue}/queue/${cid}`); } catch { return { breakdown:[{status:'WAITING',count:142},{status:'WINDOW_GRANTED',count:3}] }; } },
      update: (cid,uid,p)      => req(`${BASE.queue}/queue/${cid}/${uid}`,'PUT',p).catch(()=>{}),
      leave:  (cid,uid)        => req(`${BASE.queue}/queue/${cid}/${uid}`,'DELETE').catch(()=>{}),
    },
    tickets: {
      list:      async (cid,st) => { try { return await req(`${BASE.tickets}/tickets/${cid}?status=${st||'AVAILABLE'}`); } catch { return { tickets: SEED.tickets.filter(t=>t.concertId===cid&&(!st||st==='ALL'||t.status===st)) }; } },
      resale:    async cid      => { try { return await req(`${BASE.tickets}/tickets/${cid}/resale`); } catch { return { listings: SEED.resaleListings.filter(t=>t.concertId===cid) }; } },
      get:       async (cid,id) => { try { return await req(`${BASE.tickets}/tickets/${cid}/${id}`); } catch { return SEED.tickets.find(t=>t.ticketId===id)||null; } },
      update:    (cid,id,p)     => req(`${BASE.tickets}/tickets/${cid}/${id}`,'PUT',p).catch(()=>({ updated:true })),
      cancelAll: (cid,p)        => req(`${BASE.tickets}/tickets/${cid}/cancel-all`,'PUT',p).catch(()=>({ ticketsRefunded:0 })),
    },
    payment: {
      charge:   async p  => { try { return await req(`${BASE.payment}/payment`,'POST',p); } catch { return { paymentId:`PAY-${Math.random().toString(36).slice(2,8).toUpperCase()}`, status:'SUCCESS', amount:p.amount, currency:p.currency }; } },
      refund:   async p  => { try { return await req(`${BASE.payment}/payment/refund`,'POST',p); } catch { return { paymentId:`PAY-REFUND`, type:'REFUND', status:'SUCCESS' }; } },
      byUser:   async id => { try { return await req(`${BASE.payment}/payment/user/${id}`); } catch { return { payments: SEED.payments.filter(p=>p.userId===id) }; } },
      byConcert:async id => { try { return await req(`${BASE.payment}/payment/concert/${id}`); } catch { return { payments: SEED.payments.filter(p=>p.concertId===id) }; } },
    },
    qr: {
      generate:     async p  => { try { return await req(`${BASE.qr}/qr`,'POST',p); } catch { return { qrId:`QR-DEMO`, qrData:`CTMS|${p.ticketId}|${p.userId}|${p.concertId}|demo1234`, isValid:true }; } },
      get:          async id => { try { return await req(`${BASE.qr}/qr/${id}`); } catch { return { qrData:`CTMS|${id}|DEMO|CONC|demo1234`, isValid:true }; } },
      invalidate:   (id,p)   => req(`${BASE.qr}/qr/${id}/invalidate`,'PUT',p).catch(()=>{}),
      invalidateAll:cid      => req(`${BASE.qr}/qr/concert/${cid}/invalidate-all`,'PUT',{}).catch(()=>{}),
    },
    notification: {
      byUser: async id => { try { return await req(`${BASE.notification}/notification/user/${id}`); } catch { return { notifications: SEED.notifications.filter(n=>n.userId===id) }; } },
    },
    purchase: {
      complete: async (cid,p) => { try { return await req(`${BASE.purchase}/window/${cid}`,'POST',p); } catch { return { success:true, ticketId:p.ticketId, paymentId:`PAY-${Math.random().toString(36).slice(2,8).toUpperCase()}`, amount:388, currency:'SGD' }; } },
    },
    resale: {
      list: async p => { try { return await req(`${BASE.resale}/list`,'POST',p); } catch { return { success:true, listingId:`LST-DEMO`, resalePrice:p.resalePrice }; } },
      buy:  async p => { try { return await req(`${BASE.resale}/purchase`,'POST',p); } catch { return { success:true, ticketId:p.ticketId, paymentId:`PAY-RESALE` }; } },
    },
    cancellation: {
      cancel: async (cid,p) => { try { return await req(`${BASE.cancellation}/${cid}`,'POST',p); } catch { return { success:true, ticketsRefunded:37570, paymentsRefunded:37570 }; } },
    },
  };
})();

/* ── Auth ───────────────────────────────────────────────────── */
const Auth = (() => {
  const USERS = [
    { userId:'USR-0042', name:'Alex Tan',   email:'alex@demo.com',  password:'demo123',  role:'customer' },
    { userId:'USR-0099', name:'Jamie Lee',  email:'jamie@demo.com', password:'demo123',  role:'customer' },
    { userId:'USR-9001', name:'Admin',      email:'admin@demo.com', password:'admin123', role:'admin'    },
  ];
  return {
    login(email, pw) {
      const u = USERS.find(u=>u.email===email&&u.password===pw);
      if (!u) throw new Error('INVALID_CREDENTIALS');
      const { password:_, ...safe } = u;
      localStorage.setItem('ctms_user', JSON.stringify(safe));
      localStorage.setItem('ctms_token', `tok_${safe.userId}`);
      return safe;
    },
    logout() { localStorage.removeItem('ctms_user'); localStorage.removeItem('ctms_token'); window.location.href='login.html'; },
    getUser()    { try { return JSON.parse(localStorage.getItem('ctms_user')); } catch { return null; } },
    isLoggedIn() { return !!localStorage.getItem('ctms_token'); },
    isAdmin()    { return this.getUser()?.role==='admin'; },
    require()    { if (!this.isLoggedIn()) { window.location.href='login.html'; return null; } return this.getUser(); },
    requireAdmin(){ const u=this.require(); if(u?.role!=='admin') { window.location.href='index.html'; return null; } return u; },
  };
})();

/* ── Toast ──────────────────────────────────────────────────── */
function toast(msg, type='info', duration=3200) {
  let c = document.getElementById('toast-container');
  if (!c) { c = document.createElement('div'); c.id='toast-container'; document.body.appendChild(c); }
  const icons = { success:'✓', error:'✕', info:'●', warning:'⚠' };
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.innerHTML = `<span>${icons[type]||'●'}</span><span>${msg}</span>`;
  c.appendChild(t);
  setTimeout(()=>{ t.style.opacity='0'; t.style.transform='translateX(20px)'; t.style.transition='0.25s'; setTimeout(()=>t.remove(),260); }, duration);
}

/* ── Navbar ─────────────────────────────────────────────────── */
function renderNav(active='') {
  const user = Auth.getUser();
  const links = [
    { href:'index.html',      label:'LINEUP',     key:'concerts' },
    { href:'resale.html',     label:'RESALE',     key:'resale'   },
    { href:'my-tickets.html', label:'MY TICKETS', key:'tickets',  auth:true },
    { href:'admin.html',      label:'ADMIN',      key:'admin',    adminOnly:true },
  ].filter(l=>(!l.auth||user)&&(!l.adminOnly||user?.role==='admin'))
   .map(l=>`<a href="${l.href}" class="nav-link ${active===l.key?'active':''}">${l.label}</a>`)
   .join('');
  const userArea = user
    ? `<div class="flex-c gap-16">
         <span class="nav-link" style="color:var(--cream);font-size:0.8rem">${user.name}</span>
         <a href="profile.html" class="nav-user-pill">PROFILE</a>
         <button onclick="Auth.logout()" class="btn btn-sm" style="background:transparent;border-color:rgba(255,255,255,0.3);color:var(--cream);padding:6px 14px;font-size:0.75rem">EXIT ✕</button>
       </div>`
    : `<a href="login.html" class="btn btn-yellow btn-sm">SIGN IN →</a>`;
  const el = document.getElementById('navbar');
  if (el) el.innerHTML = `<div class="container"><a href="index.html" class="nav-brand">CTMS <span>●</span> TICKETS</a><nav class="nav-links">${links}</nav><div class="nav-actions">${userArea}</div></div>`;
}

/* ── Utilities ──────────────────────────────────────────────── */
const Util = {
  formatDate(dt) {
    if (!dt) return '—';
    return new Date(dt).toLocaleDateString('en-SG', { weekday:'short', day:'numeric', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit' });
  },
  formatDateShort(dt) {
    if (!dt) return '—';
    return new Date(dt).toLocaleDateString('en-SG', { day:'numeric', month:'short', year:'numeric' });
  },
  formatPrice(a, cur='SGD') { return `${cur} ${Number(a).toFixed(2)}`; },
  tag(status) {
    const map = { ACTIVE:'tag-active', SOLD_OUT:'tag-sold-out', CANCELLED:'tag-cancelled', POSTPONED:'tag-postponed', AVAILABLE:'tag-active', CONFIRMED:'tag-confirmed', PENDING:'tag-pending', RESALE_LISTED:'tag-resale', RESALE_PENDING:'tag-pending', USED:'tag-used', REFUNDED:'tag-refunded' };
    return `<span class="tag ${map[status]||'tag-pending'}">${status.replace(/_/g,' ')}</span>`;
  },
  getParam(k) { return new URLSearchParams(window.location.search).get(k); },
  concertBg(name='') {
    const n=name.toLowerCase();
    if(n.includes('taylor')||n.includes('swift')) return 'linear-gradient(135deg,#ff6eb4,#ff3cac)';
    if(n.includes('cold')) return 'linear-gradient(135deg,#3cffee,#3c6fff)';
    if(n.includes('bts')) return 'linear-gradient(135deg,#9b5de5,#3c3cff)';
    if(n.includes('bruno')||n.includes('mars')) return 'linear-gradient(135deg,#ffb347,#ff6b35)';
    if(n.includes('ed')||n.includes('sheeran')) return 'linear-gradient(135deg,#d4f000,#6bdd00)';
    return 'linear-gradient(135deg,#0a0a0a,#333)';
  },
};

/* ── Modal helpers ──────────────────────────────────────────── */
function openModal(id)  { document.getElementById(id)?.classList.add('open'); }
function closeModal(id) { document.getElementById(id)?.classList.remove('open'); }
document.addEventListener('click', e => {
  if (e.target.classList.contains('modal-overlay')) e.target.classList.remove('open');
});
