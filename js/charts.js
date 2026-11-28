/* Small SVG chart helpers (no chart library).
   Each function draws into a container element and adds hover tooltips.
   Animations (lines drawing, bars growing) start when the container gets the
   class "is-drawn", which motion.js adds when the chart scrolls into view. */

const SVG_NS = "http://www.w3.org/2000/svg";
const tooltipEl = () => document.getElementById("tooltip");

function el(tag, attrs = {}, parent) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}

function showTip(html, evt) {
  const tip = tooltipEl();
  tip.innerHTML = html;
  tip.classList.add("show");
  const pad = 14;
  const w = tip.offsetWidth, h = tip.offsetHeight;
  let x = evt.clientX + pad, y = evt.clientY + pad;
  if (x + w > window.innerWidth - 8) x = evt.clientX - w - pad;
  if (y + h > window.innerHeight - 8) y = evt.clientY - h - pad;
  tip.style.left = x + "px";
  tip.style.top = y + "px";
}
function hideTip() { tooltipEl().classList.remove("show"); }

function niceMax(v) {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
}

function newSvg(container, height) {
  container.innerHTML = "";
  const width = Math.max(280, container.clientWidth || 600);
  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, role: "img" }, container);
  return { svg, width, height };
}

/* ---------- line / area chart with crosshair ---------- */
function lineChart(container, { labels, series, yFormat = (v) => v, xFormat = (v) => v, height = 280, area = false, yMin = 0 }) {
  const { svg, width } = newSvg(container, height);
  const m = { top: 12, right: 12, bottom: 28, left: 56 };
  const iw = width - m.left - m.right, ih = height - m.top - m.bottom;
  const maxV = niceMax(Math.max(...series.flatMap((s) => s.values.filter((v) => v != null))));
  const x = (i) => m.left + (labels.length === 1 ? iw / 2 : (i / (labels.length - 1)) * iw);
  const y = (v) => m.top + ih - ((v - yMin) / (maxV - yMin)) * ih;

  // recessive grid + y labels
  for (let k = 0; k <= 4; k++) {
    const v = yMin + ((maxV - yMin) * k) / 4;
    el("line", { class: "grid-line", x1: m.left, x2: width - m.right, y1: y(v), y2: y(v) }, svg);
    el("text", { x: m.left - 8, y: y(v) + 4, "text-anchor": "end" }, svg).textContent = yFormat(v);
  }
  // x labels (about 6)
  const step = Math.max(1, Math.ceil(labels.length / 6));
  labels.forEach((lab, i) => {
    if (i % step === 0) el("text", { x: x(i), y: height - 8, "text-anchor": "middle" }, svg).textContent = xFormat(lab);
  });

  series.forEach((s) => {
    const pts = s.values.map((v, i) => (v == null ? null : [x(i), y(v)])).filter(Boolean);
    const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
    if (area && s.area !== false) {
      const gid = "g" + Math.random().toString(36).slice(2, 8);
      const grad = el("linearGradient", { id: gid, x1: 0, x2: 0, y1: 0, y2: 1 }, el("defs", {}, svg));
      el("stop", { offset: "0%", "stop-color": s.color, "stop-opacity": 0.28 }, grad);
      el("stop", { offset: "100%", "stop-color": s.color, "stop-opacity": 0 }, grad);
      el("path", { class: "fade-area", d: `${d} L${pts[pts.length - 1][0]} ${m.top + ih} L${pts[0][0]} ${m.top + ih} Z`, fill: `url(#${gid})` }, svg);
    }
    const path = el("path", { class: "draw-line", d, fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
    requestAnimationFrame(() => path.style.setProperty("--len", Math.ceil(path.getTotalLength())));
  });

  // crosshair + tooltip
  const cross = el("line", { y1: m.top, y2: m.top + ih, stroke: "rgba(255,255,255,0.25)", opacity: 0 }, svg);
  const dots = series.map((s) => el("circle", { r: 4, fill: s.color, stroke: "#07090f", "stroke-width": 2, opacity: 0 }, svg));
  const hit = el("rect", { x: m.left, y: m.top, width: iw, height: ih, fill: "transparent" }, svg);
  hit.addEventListener("mousemove", (evt) => {
    const box = svg.getBoundingClientRect();
    const px = ((evt.clientX - box.left) / box.width) * width;
    const i = Math.max(0, Math.min(labels.length - 1, Math.round(((px - m.left) / iw) * (labels.length - 1))));
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("opacity", 1);
    series.forEach((s, k) => {
      const v = s.values[i];
      dots[k].setAttribute("opacity", v == null ? 0 : 1);
      if (v != null) { dots[k].setAttribute("cx", x(i)); dots[k].setAttribute("cy", y(v)); }
    });
    showTip(`<strong>${xFormat(labels[i])}</strong>` + series.map((s) =>
      `<div class="tt-row"><span><i style="background:${s.color}"></i>${s.name}</span><span>${s.values[i] == null ? "-" : yFormat(s.values[i])}</span></div>`).join(""), evt);
  });
  hit.addEventListener("mouseleave", () => { cross.setAttribute("opacity", 0); dots.forEach((d) => d.setAttribute("opacity", 0)); hideTip(); });
}

/* ---------- horizontal bars ---------- */
function hbarChart(container, items, { format = (v) => v, color = "var(--series-1)", sub = null, labelWidth = 130, rowH = 30 } = {}) {
  const height = items.length * rowH + 6;
  const { svg, width } = newSvg(container, height);
  const valueW = sub ? 140 : 70;
  const lw = Math.min(labelWidth, width * 0.38);
  const iw = Math.max(40, width - lw - valueW);
  const maxV = Math.max(...items.map((d) => d.value)) || 1;
  items.forEach((d, i) => {
    const yy = i * rowH;
    const label = el("text", { class: "bar-label", x: 0, y: yy + rowH / 2 + 4 }, svg);
    label.textContent = d.label.length > 22 ? d.label.slice(0, 21) + "…" : d.label;
    el("rect", { x: lw, y: yy + rowH / 2 - 5, width: iw, height: 10, rx: 4, fill: "rgba(255,255,255,0.04)" }, svg);
    const bar = el("rect", { class: "grow-bar", x: lw, y: yy + rowH / 2 - 5, width: Math.max(2, (d.value / maxV) * iw), height: 10, rx: 4, fill: d.color || color }, svg);
    bar.style.setProperty("--d", (i * 0.05) + "s");
    bar.style.transformOrigin = `${lw}px 0`;
    const vt = el("text", { class: "value-label", x: width, y: yy + rowH / 2 + 4, "text-anchor": "end" }, svg);
    const extra = sub ? sub(d) : "";
    vt.textContent = format(d.value) + (extra ? "  ·  " + extra : "");
    const hit = el("rect", { x: 0, y: yy, width, height: rowH, fill: "transparent" }, svg);
    hit.addEventListener("mousemove", (evt) => showTip(`<strong>${d.label}</strong>${d.tip || format(d.value)}`, evt));
    hit.addEventListener("mouseleave", hideTip);
  });
}

/* ---------- vertical columns ---------- */
function columnChart(container, items, { format = (v) => v, color = "var(--series-1)", height = 220, highlight = null } = {}) {
  const { svg, width } = newSvg(container, height);
  const m = { top: 22, bottom: 26, left: 6, right: 6 };
  const ih = height - m.top - m.bottom;
  const gap = 8;
  const bw = (width - m.left - m.right - gap * (items.length - 1)) / items.length;
  const maxV = Math.max(...items.map((d) => d.value)) || 1;
  items.forEach((d, i) => {
    const h = Math.max(2, (d.value / maxV) * ih);
    const x = m.left + i * (bw + gap);
    const fill = highlight && highlight(d) ? "var(--series-2)" : (d.color || color);
    el("rect", { class: "grow-col", x, y: m.top + ih - h, width: bw, height: h, rx: 4, fill, style: `--d:${i * 0.05}s` }, svg);
    el("text", { class: "value-label", x: x + bw / 2, y: m.top + ih - h - 6, "text-anchor": "middle" }, svg).textContent = format(d.value);
    el("text", { x: x + bw / 2, y: height - 8, "text-anchor": "middle" }, svg).textContent = d.label;
    const hit = el("rect", { x, y: m.top, width: bw, height: ih, fill: "transparent" }, svg);
    hit.addEventListener("mousemove", (evt) => showTip(`<strong>${d.label}</strong>${d.tip || format(d.value)}`, evt));
    hit.addEventListener("mouseleave", hideTip);
  });
}

/* ---------- dumbbell: two values per row (promised vs actual) ---------- */
function dumbbellChart(container, items, { aName, bName, aColor = "var(--series-1)", bColor = "var(--series-2)", format = (v) => v, rowH = 28 } = {}) {
  const height = items.length * rowH + 30;
  const { svg, width } = newSvg(container, height);
  const lw = 70, right = 16;
  const iw = width - lw - right;
  const maxV = niceMax(Math.max(...items.flatMap((d) => [d.a, d.b])));
  const x = (v) => lw + (v / maxV) * iw;
  for (let k = 0; k <= 4; k++) {
    const v = (maxV * k) / 4;
    el("line", { class: "grid-line", x1: x(v), x2: x(v), y1: 0, y2: items.length * rowH }, svg);
    el("text", { x: x(v), y: height - 8, "text-anchor": "middle" }, svg).textContent = format(v);
  }
  items.forEach((d, i) => {
    const yy = i * rowH + rowH / 2;
    el("text", { class: "bar-label", x: 0, y: yy + 4 }, svg).textContent = d.label;
    el("line", { x1: x(Math.min(d.a, d.b)), x2: x(Math.max(d.a, d.b)), y1: yy, y2: yy, stroke: "rgba(255,255,255,0.25)", "stroke-width": 2 }, svg);
    el("circle", { cx: x(d.a), cy: yy, r: 5, fill: aColor, stroke: "#07090f", "stroke-width": 2 }, svg);
    el("circle", { cx: x(d.b), cy: yy, r: 5, fill: bColor, stroke: "#07090f", "stroke-width": 2 }, svg);
    const hit = el("rect", { x: 0, y: yy - rowH / 2, width, height: rowH, fill: "transparent" }, svg);
    hit.addEventListener("mousemove", (evt) => showTip(`<strong>${d.label}${d.name ? " · " + d.name : ""}</strong>
      <div class="tt-row"><span><i style="background:${aColor}"></i>${aName}</span><span>${format(d.a)}</span></div>
      <div class="tt-row"><span><i style="background:${bColor}"></i>${bName}</span><span>${format(d.b)}</span></div>`, evt));
    hit.addEventListener("mouseleave", hideTip);
  });
}

function legend(container, entries) {
  container.innerHTML = entries.map((e) => `<span><i style="background:${e.color}"></i>${e.name}</span>`).join("");
}

function table(container, columns, rows) {
  const head = columns.map((c) => `<th class="${c.num ? "num" : ""}">${c.label}</th>`).join("");
  const body = rows.map((r) => "<tr>" + columns.map((c) =>
    `<td class="${c.num ? "num" : ""}">${c.render ? c.render(r) : (r[c.key] ?? "")}</td>`).join("") + "</tr>").join("");
  container.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}
