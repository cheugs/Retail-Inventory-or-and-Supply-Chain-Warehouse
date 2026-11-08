/* Motion layer: horizon background, custom cursor, scroll reveals, active
   section in the sidebar, parallax, tilt and number count-up.
   Everything is skipped or simplified when the visitor prefers reduced motion. */

const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const FINE_POINTER = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
const mouse = { x: window.innerWidth / 2, y: window.innerHeight / 2, nx: 0, ny: 0 };
const lerp = (a, b, k) => a + (b - a) * k;

window.addEventListener("mousemove", (e) => {
  mouse.x = e.clientX; mouse.y = e.clientY;
  mouse.nx = e.clientX / window.innerWidth - 0.5;   // -0.5 .. 0.5
  mouse.ny = e.clientY / window.innerHeight - 0.5;
});

/* ---------- 1. horizon background (canvas) ----------
   A dark sky, a warm glow on the horizon and lines of "terrain" in perspective.
   The glow color changes with the chapter, the lines bend around the mouse
   and slide with the scroll. */
const Horizon = (() => {
  const canvas = document.getElementById("horizon");
  const ctx = canvas.getContext("2d");
  // glow color per chapter (index = data-hue of the section)
  const GLOWS = [[242, 184, 128], [57, 135, 229], [217, 89, 38], [25, 158, 112], [201, 133, 0], [144, 133, 233], [242, 184, 128]];
  let w = 0, h = 0, dpr = 1, t = 0;
  let glow = GLOWS[0].slice(), target = GLOWS[0].slice();
  const smooth = { mx: 0, my: 0, scroll: 0 };

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = window.innerWidth; h = window.innerHeight;
    canvas.width = w * dpr; canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function frame() {
    t += 0.004;
    smooth.mx = lerp(smooth.mx, mouse.nx, 0.05);
    smooth.my = lerp(smooth.my, mouse.ny, 0.05);
    smooth.scroll = lerp(smooth.scroll, window.scrollY, 0.08);
    for (let i = 0; i < 3; i++) glow[i] = lerp(glow[i], target[i], 0.03);
    const [r, g, b] = glow.map(Math.round);

    const horizonY = h * (0.64 + smooth.my * 0.04);
    // sky
    const sky = ctx.createLinearGradient(0, 0, 0, h);
    sky.addColorStop(0, "#05070c");
    sky.addColorStop(0.5, "#0a0e18");
    sky.addColorStop(0.64, `rgba(${r},${g},${b},0.13)`);
    sky.addColorStop(0.68, "#07090f");
    sky.addColorStop(1, "#05070c");
    ctx.fillStyle = sky;
    ctx.fillRect(0, 0, w, h);

    // sun-like glow that follows the mouse a little
    const gx = w * (0.62 + smooth.mx * 0.12);
    const rad = ctx.createRadialGradient(gx, horizonY, 0, gx, horizonY, Math.max(w, h) * 0.55);
    rad.addColorStop(0, `rgba(${r},${g},${b},0.26)`);
    rad.addColorStop(0.35, `rgba(${r},${g},${b},0.08)`);
    rad.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = rad;
    ctx.fillRect(0, 0, w, h);

    // terrain lines below the horizon, closer together near the horizon (perspective)
    const lines = 26;
    const scrollPhase = smooth.scroll * 0.0012;
    for (let i = 0; i < lines; i++) {
      const p = i / (lines - 1);
      const depth = Math.pow(p, 2.2);                  // 0 = far, 1 = near
      const baseY = horizonY + depth * (h - horizonY + 60);
      const amp = 4 + depth * 38;
      ctx.beginPath();
      for (let x = -20; x <= w + 20; x += 16) {
        const nx = x / w;
        let y = baseY
          + Math.sin(nx * 6 + t * 3 + i * 0.6 + scrollPhase) * amp * 0.35
          + Math.sin(nx * 13 - t * 2 + i * 1.3) * amp * 0.15;
        // the mouse pushes the terrain down a little around it
        const dx = x - mouse.x, dy = baseY - mouse.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        y += Math.max(0, 1 - dist / 260) * 26 * depth;
        if (x === -20) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      const alpha = 0.05 + (1 - Math.abs(p - 0.35)) * 0.12;
      ctx.strokeStyle = `rgba(${r},${g},${b},${alpha.toFixed(3)})`;
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // a few slow "stars" above the horizon
    for (let s = 0; s < 40; s++) {
      const sx = ((s * 97.13) % 1) * w + smooth.mx * -20 * ((s % 3) + 1);
      const sy = ((s * 53.71) % 1) * horizonY * 0.9 + smooth.my * -10;
      const tw = 0.3 + 0.3 * Math.sin(t * 8 + s);
      ctx.fillStyle = `rgba(255,255,255,${(tw * 0.35).toFixed(3)})`;
      ctx.fillRect(((sx % w) + w) % w, sy, 1.2, 1.2);
    }
    if (!REDUCED && !document.hidden) requestAnimationFrame(frame);
  }

  function setHue(index) { target = (GLOWS[index] || GLOWS[0]).slice(); if (REDUCED) { glow = target.slice(); frame(); } }

  resize();
  window.addEventListener("resize", () => { resize(); if (REDUCED) frame(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden && !REDUCED) requestAnimationFrame(frame); });
  frame();
  return { setHue };
})();

/* ---------- 2. custom cursor ---------- */
(() => {
  if (!FINE_POINTER || REDUCED) return;
  const dot = document.querySelector(".cursor-dot");
  const ring = document.querySelector(".cursor-ring");
  const pos = { x: mouse.x, y: mouse.y };
  document.addEventListener("mouseover", (e) => {
    ring.classList.toggle("is-hover", !!e.target.closest("a, button, .kpi, .chart rect"));
  });
  (function loop() {
    pos.x = lerp(pos.x, mouse.x, 0.18);
    pos.y = lerp(pos.y, mouse.y, 0.18);
    dot.style.transform = `translate3d(${mouse.x}px, ${mouse.y}px, 0)`;
    ring.style.transform = `translate3d(${pos.x}px, ${pos.y}px, 0)`;
    requestAnimationFrame(loop);
  })();
})();

/* ---------- 3. reveals, charts drawing and count-up ---------- */
const Motion = (() => {
  const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("is-visible");
      entry.target.querySelectorAll(".chart").forEach((c) => c.classList.add("is-drawn"));
      if (entry.target.classList.contains("chart")) entry.target.classList.add("is-drawn");
      entry.target.querySelectorAll("[data-count]").forEach(countUp);
      if (entry.target.hasAttribute("data-count")) countUp(entry.target);
      revealObserver.unobserve(entry.target);
    });
  }, { threshold: 0.15, rootMargin: "0px 0px -8% 0px" });

  function observe(root = document) {
    root.querySelectorAll("[data-reveal], .chart, .kpi").forEach((n) => {
      if (REDUCED) { n.classList.add("is-visible", "is-drawn"); n.querySelectorAll?.("[data-count]").forEach(countUp); return; }
      revealObserver.observe(n);
    });
  }

  function countUp(node) {
    if (node.dataset.counted) return;
    node.dataset.counted = "1";
    const end = parseFloat(node.dataset.count);
    const format = FORMATTERS[node.dataset.format] || ((v) => v);
    if (REDUCED) { node.textContent = format(end); return; }
    const start = performance.now(), dur = 1400;
    (function tick(now) {
      const k = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - k, 3);
      node.textContent = format(end * eased);
      if (k < 1) requestAnimationFrame(tick);
    })(start);
  }

  return { observe, countUp };
})();

// how the count-up numbers are written (depends on the language)
const FORMATTERS = {
  eur: (v) => fmt.eurShort(v), int: (v) => fmt.int(v), pct: (v) => fmt.pct(v, 1),
  num1: (v) => fmt.num(v, 1), num2: (v) => fmt.num(v, 2), days: (v) => fmt.num(v, 1) + " " + t("days"),
};

/* ---------- 4. sidebar: active section, sliding indicator, progress ---------- */
(() => {
  const links = [...document.querySelectorAll(".nav a")];
  const indicator = document.getElementById("navIndicator");
  const bar = document.getElementById("progressBar");
  const sidebar = document.getElementById("sidebar");

  function moveIndicator(link) {
    if (!link) { indicator.style.opacity = 0; return; }
    indicator.style.opacity = 1;
    indicator.style.transform = `translateY(${link.offsetTop}px)`;
    indicator.style.height = link.offsetHeight + "px";
  }

  const sectionObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      const id = entry.target.id;
      links.forEach((a) => a.classList.toggle("active", a.dataset.target === id));
      moveIndicator(links.find((a) => a.dataset.target === id));
      Horizon.setHue(parseInt(entry.target.dataset.hue || "0", 10));
    });
  }, { rootMargin: "-45% 0px -50% 0px" });
  document.querySelectorAll("section.chapter").forEach((s) => sectionObserver.observe(s));

  window.addEventListener("scroll", () => {
    const max = document.documentElement.scrollHeight - window.innerHeight;
    bar.style.width = (max > 0 ? (window.scrollY / max) * 100 : 0) + "%";
  }, { passive: true });

  // mobile menu
  const toggle = document.getElementById("menuToggle");
  toggle.addEventListener("click", () => {
    const open = sidebar.classList.toggle("open");
    toggle.setAttribute("aria-expanded", open);
  });
  links.forEach((a) => a.addEventListener("click", () => { sidebar.classList.remove("open"); toggle.setAttribute("aria-expanded", false); }));
})();

/* ---------- 5. parallax of the big chapter numbers, tilt of the KPI tiles ---------- */
(() => {
  if (REDUCED) return;
  const items = [...document.querySelectorAll("[data-parallax]")];
  const smooth = { y: window.scrollY };
  (function loop() {
    smooth.y = lerp(smooth.y, window.scrollY, 0.1);
    items.forEach((node) => {
      const section = node.parentElement;
      // 0 when the section is centred in the window, limited so the number stays in its section
      const offset = smooth.y + window.innerHeight / 2 - (section.offsetTop + section.offsetHeight / 2);
      const speed = parseFloat(node.dataset.parallax);
      const shift = Math.max(-160, Math.min(160, offset * speed));
      node.style.transform = `translate3d(${mouse.nx * -18}px, ${shift}px, 0)`;
    });
    requestAnimationFrame(loop);
  })();

  if (!FINE_POINTER) return;
  document.addEventListener("mousemove", (e) => {
    const card = e.target.closest(".kpi");
    document.querySelectorAll(".kpi.tilting").forEach((k) => {
      if (k !== card) { k.classList.remove("tilting"); k.style.transform = ""; }
    });
    if (!card) return;
    const r = card.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width - 0.5, py = (e.clientY - r.top) / r.height - 0.5;
    card.classList.add("tilting");
    card.style.transform = `perspective(700px) rotateX(${(-py * 6).toFixed(2)}deg) rotateY(${(px * 6).toFixed(2)}deg)`;
  });
})();
