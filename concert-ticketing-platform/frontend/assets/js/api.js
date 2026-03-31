/**
 * api.js — CTMS Shared API Client
 * All service base URLs configurable here.
 * Import this in every page script.
 */

const API = (() => {
  const BASE = {
    concert:      'https://<your-env>.outsystemscloud.com/ConcertAPI/rest/v1',
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

  async function req(url, method = 'GET', body = null) {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    const token = localStorage.getItem('ctms_token');
    if (token) opts.headers['Authorization'] = `Bearer ${token}`;
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(url, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw { status: res.status, ...(data.error || data) };
    return data;
  }

  return {
    // ── Concert Service (OutSystems) ────────────────────────────
    concerts: {
      list:       ()               => req(`${BASE.concert}/concerts`),
      get:        (id)             => req(`${BASE.concert}/concerts/${id}`),
      seats:      (id)             => req(`${BASE.concert}/concerts/${id}/seats`),
      create:     (payload)        => req(`${BASE.concert}/concerts`, 'POST', payload),
      update:     (id, payload)    => req(`${BASE.concert}/concerts/${id}`, 'PUT', payload),
      updateSeats:(id, catId, p)   => req(`${BASE.concert}/concerts/${id}/seats/${catId}`, 'PUT', p),
    },

    // ── Pricing ─────────────────────────────────────────────────
    pricing: {
      list:       (concertId)              => req(`${BASE.pricing}/concerts/${concertId}/prices`),
      get:        (concertId, catId)       => req(`${BASE.pricing}/concerts/${concertId}/prices/${catId}`),
      ceiling:    (concertId, catId)       => req(`${BASE.pricing}/concerts/${concertId}/prices/${catId}/ceiling`),
      create:     (concertId, payload)     => req(`${BASE.pricing}/concerts/${concertId}/prices`, 'POST', payload),
      update:     (concertId, catId, p)    => req(`${BASE.pricing}/concerts/${concertId}/prices/${catId}`, 'PUT', p),
    },

    // ── Queue ────────────────────────────────────────────────────
    queue: {
      join:       (concertId, payload)     => req(`${BASE.queue}/queue/${concertId}`, 'POST', payload),
      status:     (concertId, userId)      => req(`${BASE.queue}/queue/${concertId}/${userId}`),
      depth:      (concertId)              => req(`${BASE.queue}/queue/${concertId}`),
      update:     (concertId, userId, p)   => req(`${BASE.queue}/queue/${concertId}/${userId}`, 'PUT', p),
      leave:      (concertId, userId)      => req(`${BASE.queue}/queue/${concertId}/${userId}`, 'DELETE'),
    },

    // ── Ticket Inventory ─────────────────────────────────────────
    tickets: {
      list:       (concertId, status)      => req(`${BASE.tickets}/tickets/${concertId}?status=${status||'AVAILABLE'}`),
      resale:     (concertId)              => req(`${BASE.tickets}/tickets/${concertId}/resale`),
      get:        (concertId, ticketId)    => req(`${BASE.tickets}/tickets/${concertId}/${ticketId}`),
      create:     (payload)                => req(`${BASE.tickets}/tickets`, 'POST', payload),
      update:     (concertId, ticketId, p) => req(`${BASE.tickets}/tickets/${concertId}/${ticketId}`, 'PUT', p),
      cancelAll:  (concertId, payload)     => req(`${BASE.tickets}/tickets/${concertId}/cancel-all`, 'PUT', payload),
    },

    // ── Payment ──────────────────────────────────────────────────
    payment: {
      charge:     (payload)                => req(`${BASE.payment}/payment`, 'POST', payload),
      refund:     (payload)                => req(`${BASE.payment}/payment/refund`, 'POST', payload),
      get:        (paymentId)              => req(`${BASE.payment}/payment/${paymentId}`),
      byUser:     (userId)                 => req(`${BASE.payment}/payment/user/${userId}`),
      byConcert:  (concertId)              => req(`${BASE.payment}/payment/concert/${concertId}`),
    },

    // ── QR ───────────────────────────────────────────────────────
    qr: {
      generate:    (payload)               => req(`${BASE.qr}/qr`, 'POST', payload),
      get:         (ticketId)              => req(`${BASE.qr}/qr/${ticketId}`),
      validate:    (ticketId)              => req(`${BASE.qr}/qr/${ticketId}/validate`),
      invalidate:  (ticketId, payload)     => req(`${BASE.qr}/qr/${ticketId}/invalidate`, 'PUT', payload),
      invalidateAll:(concertId)            => req(`${BASE.qr}/qr/concert/${concertId}/invalidate-all`, 'PUT', {}),
    },

    // ── Notification ─────────────────────────────────────────────
    notification: {
      get:         (id)                    => req(`${BASE.notification}/notification/${id}`),
      byUser:      (userId)                => req(`${BASE.notification}/notification/user/${userId}`),
    },

    // ── Composite: Purchase Window (S1) ──────────────────────────
    purchase: {
      complete:    (concertId, payload)    => req(`${BASE.purchase}/window/${concertId}`, 'POST', payload),
    },

    // ── Composite: Resale Purchase (S2a + S2b) ───────────────────
    resale: {
      list:        (payload)               => req(`${BASE.resale}/list`, 'POST', payload),
      buy:         (payload)               => req(`${BASE.resale}/purchase`, 'POST', payload),
    },

    // ── Composite: Concert Cancellation (S3) ─────────────────────
    cancellation: {
      cancel:      (concertId, payload)    => req(`${BASE.cancellation}/${concertId}`, 'POST', payload),
    },
  };
})();

// ── Auth helpers ─────────────────────────────────────────────────────────────
const Auth = (() => {
  const USER_KEY = 'ctms_user';
  const TOKEN_KEY = 'ctms_token';

  // Simulated users for demo — replace with real auth service
  const DEMO_USERS = [
    { userId: 'USR-0042', name: 'Alex Tan',     email: 'alex@demo.com',  password: 'demo123', role: 'customer' },
    { userId: 'USR-0099', name: 'Jamie Lee',    email: 'jamie@demo.com', password: 'demo123', role: 'customer' },
    { userId: 'USR-9001', name: 'Admin User',   email: 'admin@demo.com', password: 'admin123',role: 'admin'    },
  ];

  return {
    login(email, password) {
      const user = DEMO_USERS.find(u => u.email === email && u.password === password);
      if (!user) throw new Error('Invalid email or password');
      const { password: _, ...safe } = user;
      localStorage.setItem(USER_KEY,  JSON.stringify(safe));
      localStorage.setItem(TOKEN_KEY, `demo_token_${safe.userId}`);
      return safe;
    },
    logout() {
      localStorage.removeItem(USER_KEY);
      localStorage.removeItem(TOKEN_KEY);
      window.location.href = '/frontend/pages/login.html';
    },
    getUser()    { try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch { return null; } },
    isLoggedIn() { return !!localStorage.getItem(TOKEN_KEY); },
    isAdmin()    { return this.getUser()?.role === 'admin'; },
    require()    { if (!this.isLoggedIn()) window.location.href = '/frontend/pages/login.html'; return this.getUser(); },
    requireAdmin(){ const u = this.require(); if (u?.role !== 'admin') window.location.href = '/frontend/pages/index.html'; return u; },
  };
})();

// ── Toast notifications ───────────────────────────────────────────────────────
function toast(message, type = 'info', duration = 3500) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }
  const icons = { success: '✓', error: '✕', info: 'ℹ', warning: '⚠' };
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.innerHTML = `<span style="font-size:1rem">${icons[type]||'•'}</span><span>${message}</span>`;
  container.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transform = 'translateX(24px)'; t.style.transition = '0.3s'; setTimeout(() => t.remove(), 300); }, duration);
}

// ── Navbar renderer ───────────────────────────────────────────────────────────
function renderNav(activePage = '') {
  const user = Auth.getUser();
  const isAdmin = user?.role === 'admin';
  const navLinks = [
    { href: 'index.html',        label: 'Concerts',    key: 'concerts' },
    { href: 'my-tickets.html',   label: 'My Tickets',  key: 'tickets',  auth: true },
    { href: 'resale.html',       label: 'Resale',      key: 'resale' },
    { href: 'admin.html',        label: 'Admin',       key: 'admin',    adminOnly: true },
  ];
  const links = navLinks
    .filter(l => !l.adminOnly || isAdmin)
    .filter(l => !l.auth || user)
    .map(l => `<a href="${l.href}" class="nav-link ${activePage===l.key?'active':''}">${l.label}</a>`)
    .join('');
  const userArea = user
    ? `<div class="nav-user">
         <span class="text-sm text-muted">${user.name}</span>
         <div class="nav-avatar" title="Profile" onclick="window.location.href='profile.html'">${user.name[0]}</div>
         <button class="btn btn-ghost btn-sm" onclick="Auth.logout()">Sign out</button>
       </div>`
    : `<a href="login.html" class="btn btn-primary btn-sm">Sign in</a>`;
  document.getElementById('navbar').innerHTML = `
    <div class="container">
      <a href="index.html" class="nav-brand">🎵 CTMS</a>
      <nav class="nav-links">${links}</nav>
      ${userArea}
    </div>`;
}

// ── Utility helpers ───────────────────────────────────────────────────────────
const Util = {
  formatDate(dt) {
    if (!dt) return '—';
    return new Date(dt).toLocaleDateString('en-SG', { weekday:'short', day:'numeric', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit' });
  },
  formatPrice(amount, currency = 'SGD') {
    return new Intl.NumberFormat('en-SG', { style: 'currency', currency }).format(amount);
  },
  statusBadge(status) {
    const map = {
      ACTIVE: 'active', SOLD_OUT: 'sold-out', CANCELLED: 'cancelled', POSTPONED: 'postponed',
      AVAILABLE: 'active', CONFIRMED: 'confirmed', PENDING: 'pending',
      RESALE_LISTED: 'resale', RESALE_PENDING: 'pending', USED: 'sold-out', REFUNDED: 'refunded',
    };
    const cls = map[status] || 'pending';
    return `<span class="badge badge-${cls}">${status.replace(/_/g,' ')}</span>`;
  },
  getParam(key) {
    return new URLSearchParams(window.location.search).get(key);
  },
  concertEmoji(name = '') {
    const n = name.toLowerCase();
    if (n.includes('taylor') || n.includes('pop')) return '🌟';
    if (n.includes('cold') || n.includes('rock')) return '🎸';
    if (n.includes('bts') || n.includes('kpop') || n.includes('k-pop')) return '💜';
    if (n.includes('bruno') || n.includes('r&b')) return '🎷';
    if (n.includes('ed') || n.includes('folk')) return '🎵';
    return '🎤';
  },
};
