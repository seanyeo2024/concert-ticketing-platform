/* ============================================================
   api.js — Solstitix Shared JS Layer
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
  concerts: [],
  categories: {},
  prices: {},
  tickets: [],
  resaleListings: [],
  payments: [],
  notifications: [],
};

/* ── API client ─────────────────────────────────────────────── */
const API = (() => {
  const GATEWAY = window.CTMS_GATEWAY_URL || 'http://localhost:8000';
  const BASE = {
    concert:      GATEWAY,
    pricing:      `${GATEWAY}/pricing/v1`,
    queue:        `${GATEWAY}/queue/v1`,
    tickets:      `${GATEWAY}/tickets/v1`,
    payment:      `${GATEWAY}/payment/v1`,
    qr:           `${GATEWAY}/qr/v1`,
    notification: `${GATEWAY}/notification/v1`,
    purchase:     `${GATEWAY}/purchase/v1`,
    resale:       `${GATEWAY}/resale/v1`,
    resaleTicket: `${GATEWAY}/resale-ticket/v1`,
    cancellation: `${GATEWAY}/cancellation/v1`,
  };

  async function req(url, method='GET', body=null, timeoutMs=10000) {
    const opts = { method, headers:{'Content-Type':'application/json'} };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(url, { ...opts, signal: AbortSignal.timeout(timeoutMs) });
    const data = await res.json().catch(()=>({}));
    if (!res.ok) {
      const err = data.error || data || {};
      if (typeof err === 'object' && err !== null) {
        err.status = res.status;
      }
      throw err;
    }
    return data;
  }

  return {
    concerts: {
      list: async () => { try { const d = await req(`${BASE.concert}/concerts`); return Array.isArray(d) ? { concerts: d } : d; } catch { return { concerts: SEED.concerts }; } },
      listStrict: async () => { const d = await req(`${BASE.concert}/concerts`); return Array.isArray(d) ? { concerts: d } : d; },
      get:  async id  => { try { return await req(`${BASE.concert}/concerts/${id}`); } catch { return SEED.concerts.find(c=>c.concertId===id) || null; } },
      getStrict: async id => req(`${BASE.concert}/concerts/${id}`),
      seats:async id  => { try { return await req(`${BASE.concert}/concerts/${id}/seats`); } catch { return { categories: SEED.categories[id]||[] }; } },
      seatsStrict: async id => req(`${BASE.concert}/concerts/${id}/seats`),
      createSeats: (id,p) => req(`${BASE.concert}/concerts/${id}/seats`, 'POST', p),
      update: (id,p)  => req(`${BASE.concert}/concerts/${id}`, 'PUT', p),
      create: p       => req(`${BASE.concert}/concerts`, 'POST', p),
    },
    pricing: {
      list:    async (cid)      => { try { return await req(`${BASE.pricing}/concerts/${cid}/prices`); } catch { return { prices: SEED.prices[cid]||[] }; } },
      listStrict: async cid => req(`${BASE.pricing}/concerts/${cid}/prices`),
      get:     async (cid,cat)  => { try { return await req(`${BASE.pricing}/concerts/${cid}/prices/${cat}`); } catch { return (SEED.prices[cid]||[]).find(p=>p.categoryId===cat)||{}; } },
      ceiling: async (cid,cat)  => { try { return await req(`${BASE.pricing}/concerts/${cid}/prices/${cat}/ceiling`); } catch { const p=(SEED.prices[cid]||[]).find(p=>p.categoryId===cat)||{}; return {resaleCeiling:p.resaleCeiling,currency:'SGD'}; } },
      create: (cid,p)           => req(`${BASE.pricing}/concerts/${cid}/prices`, 'POST', p),
      update: (cid,cat,p)       => req(`${BASE.pricing}/concerts/${cid}/prices/${cat}`, 'PUT', p),
    },
    queue: {
      join:   (cid,p)          => req(`${BASE.queue}/queue/${cid}`,'POST',p),
      status: (cid,uid)        => req(`${BASE.queue}/queue/${cid}/${uid}`),
      depth:  cid              => req(`${BASE.queue}/queue/${cid}`),
      update: (cid,uid,p)      => req(`${BASE.queue}/queue/${cid}/${uid}`,'PUT',p).catch(()=>{}),
      leave:  (cid,uid)        => req(`${BASE.queue}/queue/${cid}/${uid}`,'DELETE').catch(()=>{}),
    },
    tickets: {
      list:      async (cid,st) => { try { return await req(`${BASE.tickets}/tickets/${cid}?status=${st||'AVAILABLE'}`); } catch { return { tickets: SEED.tickets.filter(t=>t.concertId===cid&&(!st||st==='ALL'||t.status===st)) }; } },
      resale:    async cid      => { try { return await req(`${BASE.tickets}/tickets/${cid}/resale`); } catch { return { listings: SEED.resaleListings.filter(t=>t.concertId===cid) }; } },
      get:       async (cid,id) => { try { return await req(`${BASE.tickets}/tickets/${cid}/${id}`); } catch { return SEED.tickets.find(t=>t.ticketId===id)||null; } },
      create:    p              => req(`${BASE.tickets}/tickets`, 'POST', p),
      update:    (cid,id,p)     => req(`${BASE.tickets}/tickets/${cid}/${id}`,'PUT',p).catch(()=>({ updated:true })),
      cancelAll: (cid,p)        => req(`${BASE.tickets}/tickets/${cid}/cancel-all`,'PUT',p).catch(()=>({ ticketsRefunded:0 })),
    },
    payment: {
      config:   async () => { try { return await req(`${BASE.payment}/config`); } catch { return { stripeConfigured:false, frontendMode:'demo-fallback' }; } },
      charge:   async p  => { try { return await req(`${BASE.payment}/payment`,'POST',p); } catch { return { paymentId:`PAY-${Math.random().toString(36).slice(2,8).toUpperCase()}`, status:'SUCCESS', amount:p.amount, currency:p.currency }; } },
      refund:   async p  => { try { return await req(`${BASE.payment}/payment/refund`,'POST',p); } catch { return { paymentId:`PAY-REFUND`, type:'REFUND', status:'SUCCESS' }; } },
      byUser:   async id => { try { return await req(`${BASE.payment}/payment/user/${id}`); } catch { return { payments: SEED.payments.filter(p=>p.userId===id) }; } },
      byConcert:async id => { try { return await req(`${BASE.payment}/payment/concert/${id}`); } catch { return { payments: SEED.payments.filter(p=>p.concertId===id) }; } },
    },
    qr: {
      generate:     async p  => { try { return await req(`${BASE.qr}/qr`,'POST',p); } catch { return { qrId:`QR-DEMO`, qrData:`Solstitix|${p.ticketId}|${p.userId}|${p.concertId}|demo1234`, isValid:true }; } },
      get:          async id => { try { return await req(`${BASE.qr}/qr/${id}`); } catch { return { qrData:`Solstitix|${id}|DEMO|CONC|demo1234`, isValid:true }; } },
      invalidate:   (id,p)   => req(`${BASE.qr}/qr/${id}/invalidate`,'PUT',p).catch(()=>{}),
      invalidateAll:cid      => req(`${BASE.qr}/qr/concert/${cid}/invalidate-all`,'PUT',{}).catch(()=>{}),
    },
    notification: {
      byUser: async id => { try { return await req(`${BASE.notification}/notification/user/${id}`); } catch { return { notifications: SEED.notifications.filter(n=>n.userId===id) }; } },
    },
    purchase: {
      complete: (cid,p) => req(`${BASE.purchase}/window/${cid}`,'POST',p,30000),
    },
    resaleTicket: {
      listings: async cid => {
        return req(`${BASE.resaleTicket}/listings/${cid}`);
      },
      list: async p => {
        return await req(`${BASE.resaleTicket}/list`, 'POST', p);
      },
      unlist: async p => {
        return await req(`${BASE.resaleTicket}/unlist`, 'PUT', p);
      },
      purchase: async p => {
        return await req(`${BASE.resaleTicket}/purchase`, 'POST', p);
      },
    },
    resale: {
      list: async p => API.resaleTicket.list(p),
      buy:  async p => API.resaleTicket.purchase(p),
      unlist: async p => API.resaleTicket.unlist(p),
      listings: async cid => API.resaleTicket.listings(cid),
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
    homePage()   { return this.isAdmin() ? 'admin.html' : 'index.html'; },
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
  const homeHref = Auth.homePage();
  const navItems = user?.role==='admin'
    ? [
        { href:'admin.html', label:'ADMIN', key:'admin' },
      ]
    : [
        { href:'index.html',      label:'LINEUP',     key:'concerts' },
        { href:'resale.html',     label:'RESALE',     key:'resale'   },
        { href:'my-tickets.html', label:'MY TICKETS', key:'tickets',  auth:true },
        { href:'admin.html',      label:'ADMIN',      key:'admin',    adminOnly:true },
      ].filter(l=>(!l.auth||user)&&(!l.adminOnly||user?.role==='admin'));
  const links = navItems
   .map(l=>`<a href="${l.href}" class="nav-link ${active===l.key?'active':''}">${l.label}</a>`)
   .join('');
  const mobileLinks = [
    ...navItems,
    ...(user ? [{ href:'profile.html', label:'PROFILE', key:'profile' }] : []),
  ].map(l=>`<a href="${l.href}" class="nav-mobile-link ${active===l.key?'active':''}">${l.label}</a>`)
   .join('');
  const userArea = user
    ? `<div class="nav-user-meta">
         <span class="nav-user-name">${user.name}</span>
         <a href="profile.html" class="nav-user-pill">PROFILE</a>
         <button onclick="Auth.logout()" class="btn btn-sm nav-logout-btn">LOGOUT</button>
       </div>`
    : `<a href="login.html" class="btn btn-yellow btn-sm">SIGN IN →</a>`;
  const mobileAccountArea = user
    ? `<div class="nav-mobile-account">
         <span class="nav-user-name">${user.name}</span>
         <a href="profile.html" class="nav-user-pill">PROFILE</a>
         <button onclick="Auth.logout()" class="btn btn-sm nav-logout-btn">LOGOUT</button>
       </div>`
    : `<div class="nav-mobile-account"><a href="login.html" class="btn btn-yellow btn-sm">SIGN IN →</a></div>`;
  const el = document.getElementById('navbar');
  if (el) {
    el.classList.remove('menu-open');
    el.innerHTML = `<div class="container"><a href="${homeHref}" class="nav-brand"><img src="../assets/logo.svg" alt="Solstitix logo" class="nav-brand-logo"> <span>Solstitix</span></a><nav class="nav-links">${links}</nav><div class="nav-actions">${userArea}</div><button class="nav-menu-toggle" type="button" aria-label="Toggle navigation" aria-expanded="false"><span></span></button><div class="nav-mobile-menu"><nav class="nav-mobile-links">${mobileLinks}</nav>${mobileAccountArea}</div></div>`;
    const toggle = el.querySelector('.nav-menu-toggle');
    const closeMenu = () => {
      el.classList.remove('menu-open');
      toggle?.setAttribute('aria-expanded', 'false');
    };
    toggle?.addEventListener('click', () => {
      const isOpen = el.classList.toggle('menu-open');
      toggle.setAttribute('aria-expanded', String(isOpen));
    });
    el.querySelectorAll('.nav-mobile-menu a, .nav-mobile-menu button').forEach(node => {
      node.addEventListener('click', closeMenu);
    });
    document.addEventListener('click', e => {
      if (!el.classList.contains('menu-open')) return;
      if (el.contains(e.target)) return;
      closeMenu();
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') closeMenu();
    });
  }
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
