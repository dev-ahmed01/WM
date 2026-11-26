// UI sweep: layout, touch targets, labels and contrast for every role/route at desktop, tablet and phone widths.
//
// Usage (Playwright MCP "run code" tool or any Playwright runner that passes `page`):
//   browser_run_code_unsafe({ filename: "backend/e2e/ui_sweep.js" })
// Needs the app running on :3000 with the demo users seeded (python -m demo.seed_demo / seed_activity).
// Credentials come from .demo-credentials.local.json - paste them into CREDS below locally; never commit real ones.
//
// Checks per route: horizontal overflow, visible controls under 40px tall on touch widths, unlabeled form
// controls, buttons/links without an accessible name, exactly one <h1>, text contrast below WCAG AA (4.5:1,
// 3:1 for large text), console errors and failed /api calls. It reads the page only; it never clicks anything.
async (page) => {
  const CREDS = {
    employee: { email: 'demo_general@demo.workmate.test', pw: process.env.WM_EMPLOYEE_PW || '' },
    manager: { email: 'demo_manager_hyd@demo.workmate.test', pw: process.env.WM_MANAGER_PW || '' },
    admin: { email: 'demo_admin@demo.workmate.test', pw: process.env.WM_ADMIN_PW || '' },
  };
  const ROUTES = {
    employee: ['/workspace', '/copilot', '/copilot/history', '/copilot/sources', '/copilot/handover'],
    manager: ['/control-room', '/intelligence-hub', '/handover/review', '/work/exceptions', '/work/integrations', '/pilot', '/knowledge-gaps', '/approvals'],
    admin: ['/procedure-studio', '/procedure-studio/drafts', '/knowledge-studio', '/knowledge-studio/upload', '/knowledge-studio/references', '/employees', '/knowledge-gaps'],
  };
  const SIZES = [{ n: 'desktop', w: 1440, h: 900 }, { n: 'tablet', w: 820, h: 1180 }, { n: 'phone', w: 390, h: 844 }];

  const audit = (touch) => {
    const vis = el => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
    const name = el => (el.getAttribute('aria-label') || el.innerText || el.getAttribute('title') || el.getAttribute('placeholder') || '').trim();
    const small = touch ? [...document.querySelectorAll('main button, main a[href], main [role=button], main select, main input:not([type=hidden]), main textarea')]
      .filter(vis).filter(el => el.getBoundingClientRect().height < 40 && !(['checkbox', 'radio', 'file'].includes(el.type) || el.className?.toString().includes('sr-only') || el.closest('p')))
      .map(el => `${el.tagName.toLowerCase()}:${name(el).slice(0, 22)}`) : [];
    const unlabeled = [...document.querySelectorAll('input:not([type=hidden]), textarea, select')].filter(vis)
      .filter(el => !(el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || (el.labels && el.labels.length) || (el.id && document.querySelector(`label[for="${el.id}"]`)) || el.closest('label'))).length;
    const noName = [...document.querySelectorAll('button, a[href]')].filter(vis).filter(el => !name(el) && !el.querySelector('img[alt]')).length;
    const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(',').map(parseFloat); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
    const lum = ({ r, g, b }) => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
    const blend = (fg, bg) => ({ r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a), b: fg.b * fg.a + bg.b * (1 - fg.a), a: 1 });
    const bgOf = el => { const stack = []; for (let e = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor); if (c && c.a > 0) { stack.push(c); if (c.a === 1) break; } } let base = { r: 255, g: 255, b: 255, a: 1 }; for (const c of stack.reverse()) base = blend(c, base); return base; };
    const low = new Map(); const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const t = walker.currentNode.textContent.trim(); if (t.length < 2) continue;
      const el = walker.currentNode.parentElement; if (!el || el.closest('script,style,noscript,nextjs-portal,[class*="sr-only"],[disabled]')) continue;
      const cs = getComputedStyle(el); const r = el.getBoundingClientRect();
      if (cs.visibility === 'hidden' || cs.display === 'none' || r.width === 0 || parseFloat(cs.opacity) === 0) continue;
      const fgc = parse(cs.color); if (!fgc) continue;
      const bg = bgOf(el); const fg = blend({ ...fgc, a: fgc.a * (parseFloat(cs.opacity) || 1) }, bg);
      const ratio = (Math.max(lum(fg), lum(bg)) + 0.05) / (Math.min(lum(fg), lum(bg)) + 0.05);
      const size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight) >= 700;
      if (ratio < ((size >= 24 || (size >= 18.66 && bold)) ? 3 : 4.5)) low.set(t.slice(0, 28), +ratio.toFixed(2));
    }
    return {
      overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth, smallTargets: small.slice(0, 5), smallCount: small.length,
      unlabeled, noName, h1s: document.querySelectorAll('h1').length, lowContrast: [...low.entries()].slice(0, 4), lowContrastCount: low.size,
    };
  };

  const problems = []; let checked = 0;
  for (const role of Object.keys(CREDS)) {
    if (!CREDS[role].pw) { problems.push({ role, error: `set WM_${role.toUpperCase()}_PW or edit CREDS` }); continue; }
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('http://localhost:3000/login');
    await page.evaluate(async () => { await fetch('/api/session/logout', { method: 'POST' }).catch(() => {}); });
    await page.goto('http://localhost:3000/login');
    await page.locator('input[type=text]').fill(CREDS[role].email);
    await page.locator('input[type=password]').fill(CREDS[role].pw);
    await page.locator('button[type=submit]').click();
    await page.waitForURL(u => !u.pathname.startsWith('/login'));
    for (const sz of SIZES) {
      await page.setViewportSize({ width: sz.w, height: sz.h });
      for (const route of ROUTES[role]) {
        const errors = [], failed = [];
        const onC = m => { if (m.type() === 'error' && !/favicon|DevTools|hydrat/i.test(m.text())) errors.push(m.text().slice(0, 120)); };
        const onR = r => { if (r.url().includes('/api/') && r.status() >= 400) failed.push(r.status() + ' ' + r.url().replace('http://localhost:3000', '').slice(0, 70)); };
        page.on('console', onC); page.on('response', onR);
        try {
          await page.goto('http://localhost:3000' + route, { waitUntil: 'load', timeout: 30000 });
          await page.waitForTimeout(1500);
          const r = await page.evaluate(audit, sz.n !== 'desktop');
          checked++;
          const bad = r.overflowX > 0 || r.smallCount || r.unlabeled || r.noName || r.h1s !== 1 || r.lowContrastCount || errors.length || failed.length;
          if (bad) problems.push({ role, size: sz.n, route, ...r, errors, failed });
        } catch (e) { problems.push({ role, size: sz.n, route, error: String(e).slice(0, 100) }); }
        page.off('console', onC); page.off('response', onR);
      }
    }
  }
  return { checked, problemCount: problems.length, problems };
}
