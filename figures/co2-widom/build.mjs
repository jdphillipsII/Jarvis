// The CO2 heat-capacity column.
//
// A graduated vessel on a bench whose cross-sectional area at height T is the
// specific heat of CO2 at 80 bar. Height is temperature, area is cp, and the
// volume up to the level is the enthalpy. Pour energy in and watch where it
// goes: nearly half the window's energy is spent crossing four degrees.
//
//   node build.mjs            dark
//   node build.mjs --light    light
//
// Built with the anatomy skill, installed at .claude/skills/anatomy. Nothing
// outside the repo is needed; ANATOMY_ROOT only overrides it for development.

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { modelOf } from "./model.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = process.env.ANATOMY_ROOT
  || join(HERE, "..", "..", ".claude", "skills", "anatomy");
const k = await import(join(ROOT, "kit", "iso-kit.mjs"));
const G = await import(join(ROOT, "kit", "lathe.mjs"));
const { kitScript } = await import(join(ROOT, "scripts", "inline-kit.mjs"));

const theme = process.argv.includes("--light") ? "light" : "dark";
const data = JSON.parse(readFileSync(join(HERE, "data.json"), "utf8"));
const M = modelOf(data);

const WIDTH = 760;
const HEIGHT = 520;

// ---- world ----------------------------------------------------------------
const PLATE = { x: -150, y: -74, w: 300, d: 148, r: 8 };
const PLATE_H = 13;
const FOOT_H = 6;

const COLUMN = 182;                 // world height of the temperature window
const R_MAX = 31;                   // radius at the widest point of the vessel
const FLOOR = 16;                   // vessel floor, above the plate
const TOP = FLOOR + COLUMN;

const SCALE_X = -62;                // the graduated post
const GAUGE = [96, 4];
const GAUGE_R = 26;
const GAUGE_Z = 118;
const GAUGE_H = 12;
const HUB_R = 3.2;              // the needle's tail ends on this ring, not past it
const INLET_Z = TOP + 22;

const zOf = (tc) => FLOOR + ((tc - M.low) / (M.high - M.low)) * COLUMN;
const rOf = (tc) => M.radiusAt(tc) * R_MAX;

const P = k.fitProjection(
  [
    ...k.boxCorners(PLATE, -PLATE_H - FOOT_H, 0),
    [0, 0, INLET_Z + 16],
    [GAUGE[0] + GAUGE_R, GAUGE[1], GAUGE_Z + GAUGE_H],
    [SCALE_X - 14, 0, TOP],
  ],
  WIDTH, HEIGHT, { pad: 28, azimuth: 44 },
);

const at = (point) => k.iso(point, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const D = (points, style) => k.dotsSvg(points, style);
const byDepth = (points) => [...points].sort(
  (a, b) => k.depthOf([a[0], a[1], 0], P) - k.depthOf([b[0], b[1], 0], P));

const AXIS = G.frameAlong([0, 0, FLOOR], [0, 0, 1]);

// The vessel's wall IS the cp curve. Given as analytic radius and slope so
// the body is one surface cut into depth-sortable bands rather than a stack of
// rings: a bulged profile whose widest ring faces the viewer head-on makes the
// plain lathe fall back to the hull of its rings, and the vessel comes out a
// diamond. `bandsOf` is the kit's answer to exactly that.
const radiusFn = (s) => rOf(M.low + (s / COLUMN) * (M.high - M.low));
const slopeFn = (s) => {
  const h = 0.4;
  const lo = Math.max(0, s - h);
  const hi = Math.min(COLUMN, s + h);
  return (radiusFn(hi) - radiusFn(lo)) / (hi - lo);
};
const CUTS = [0.1, 0.22, 0.34, 0.43, 0.5, 0.57, 0.66, 0.78, 0.9].map((f) => f * COLUMN);
const vesselBands = () => G.bandsOf(
  [[0, radiusFn(0)], [COLUMN, radiusFn(COLUMN)]], CUTS, AXIS, P,
  { radius: radiusFn, slope: slopeFn, steps: 80, rows: 7 });
const VESSEL = vesselBands();

// A horizontal disc in world space is an ellipse on screen. Precompute the
// meniscus at every level, plus the screen y of its LOWEST point: the liquid
// body is clipped there and the disc covers the rest, so the surface reads as
// an ellipse rather than a straight cut.
const LEVELS = 160;
const levels = Array.from({ length: LEVELS + 1 }, (_, i) => {
  const energy = i / LEVELS;
  const tc = M.temperatureAt(energy);
  const z = zOf(tc);
  const r = rOf(tc);
  const points = Array.from({ length: 56 }, (_, j) => {
    const a = (j / 56) * Math.PI * 2;
    return at([r * Math.cos(a), r * Math.sin(a), z]);
  });
  return {
    energy, t: Number(tc.toFixed(3)), cp: Math.round(M.cpAt(tc)),
    disc: k.pathOf(points) + "Z",
    clip: Math.max(...points.map((p) => p[1])),
    stem: at([0, 0, z]),
  };
});

// ---- parts ----------------------------------------------------------------
function bench() {
  const out = [`<path class="iso-halo" d="${k.haloOf(PLATE, -PLATE_H - FOOT_H, PLATE_H, P)}"/>`];
  for (const [x, y] of byDepth(k.corners(PLATE, 24))) {
    out.push(S(k.cylinder(x, y, 8, -PLATE_H - FOOT_H, 1.8, P, 28), { tone: "lo" }));
    out.push(S(k.cylinder(x, y, 6.2, -PLATE_H - FOOT_H + 1.8, FOOT_H - 1.8, P, 28), { tone: "mid" }));
  }
  out.push(S(k.slabOf(PLATE, -PLATE_H, PLATE_H, P, 8, 1.7), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan(PLATE, 6), 0, P), { tone: "lo" }));
  const screws = k.corners(PLATE, 11);
  out.push(L(screws.map(([x, y]) => k.ring(x, y, 2.4, 0, P, 16)).join(""), { tone: "lo" }));
  out.push(D(screws.map(([x, y]) => at([x, y, 0])), { size: 0.5 }));

  const plateLabel = { x: 34, y: PLATE.y + 10, w: 92, d: 15, r: 1.5 };
  out.push(S(k.slabOf(plateLabel, 0, 0.8, P, 3), { tone: "lo", crease: "none" }));
  out.push(D(k.corners(plateLabel, 4).map(([x, y]) => at([x, y, 0.8])), { size: 0.4 }));

  const strip = { x: -132, y: PLATE.y + PLATE.d - 17, w: 254, d: 8, r: 1 };
  out.push(S(k.slabOf(strip, 0, 0.7, P, 3), { tone: "lo", crease: "none" }));
  const ticks = k.topTicks(strip.x + 5, strip.x + strip.w - 5, 5, 5, strip.y + 1, 0.7, [2.2, 4], P);
  out.push(L(ticks.minor, { tone: "lo" }), L(ticks.major, { tone: "mid" }));
  return out.join("");
}

function pedestal() {
  const out = [];
  // A turned foot the vessel stands in, with a clamp ring.
  out.push(S(G.lathe([[0, 34], [3, 34], [3.4, 31], [10, 29], [10.6, 26], [16, 25]],
    G.frameAlong([0, 0, 0], [0, 0, 1]), P, { steps: 44 }), { tone: "mid" }));
  out.push(L(G.circleOf(G.frameAlong([0, 0, 0], [0, 0, 1]), 3.2, 33, P, 44), { tone: "lo" }));
  out.push(D(G.dotsOf(G.frameAlong([0, 0, 0], [0, 0, 1]), 1.6, 30, 8, P, { all: true }), { size: 0.45 }));
  return out.join("");
}

function scalePost() {
  // A graduated plate, read on its near face. Every tick ends on a rule:
  // minor ticks on the inner rule, major ticks on the outer one, which is
  // what a real scale looks like and what the line check asks for.
  const out = [];
  const FACE = 4;                       // the face turned toward the viewer
  const RULE_L = SCALE_X;
  const RULE_M = SCALE_X + 4.5;
  const RULE_R = SCALE_X + 11;
  const post = { x: RULE_L - 3.5, y: -FACE, w: (RULE_R - RULE_L) + 7, d: FACE * 2, r: 1 };
  out.push(S(k.slabOf(post, 0, TOP + 7, P, 2, 0.5), { tone: "mid" }));

  const rule = (x, from, to) => k.segment([x, FACE, from], [x, FACE, to], P);
  out.push(L(rule(RULE_L, zOf(M.low), zOf(M.high)) + rule(RULE_R, zOf(M.low), zOf(M.high)),
    { tone: "mid" }));
  out.push(L(rule(RULE_M, zOf(M.low), zOf(M.high)), { tone: "lo" }));

  const minor = [];
  const major = [];
  for (let tc = Math.ceil(M.low); tc <= M.high; tc += 1) {
    const z = zOf(tc);
    const far = tc % 5 === 0 ? RULE_R : RULE_M;
    (tc % 5 === 0 ? major : minor).push(k.segment([RULE_L, FACE, z], [far, FACE, z], P));
  }
  out.push(L(minor.join(""), { tone: "lo" }));
  out.push(L(major.join(""), { tone: "mid" }));

  // The Widom line, called out. Its far end carries a dot, so it is rooted at
  // both ends rather than pointing into space.
  const peakZ = zOf(M.peak.t_c);
  const tipX = RULE_R + 13;
  out.push(L(k.segment([RULE_L, FACE, peakZ], [tipX, FACE, peakZ], P), { tone: "lit" }));
  out.push(D([at([tipX, FACE, peakZ])], { size: 0.85, tone: "lit" }));
  out.push(D([at([RULE_L, FACE, zOf(M.low)]), at([RULE_R, FACE, zOf(M.high)])], { size: 0.45 }));
  return out.join("");
}

function inlet() {
  // Where the energy comes in: a pipe over the mouth with a valve and a knob.
  const out = [];
  const F = G.frameAlong([-56, 0, INLET_Z], [1, 0, 0]);
  out.push(S(G.lathe([[0, 5], [26, 5], [28, 8.5], [40, 8.5], [42, 5], [56, 5]], F, P, { steps: 36 }), { tone: "mid" }));
  out.push(L(G.circleOf(F, 28, 9, P, 32), { tone: "lo" }));
  out.push(L(G.circleOf(F, 40, 9, P, 32), { tone: "lo" }));
  const stem = G.frameAlong([-22, 0, INLET_Z + 8], [0, 0, 1]);
  out.push(S(G.lathe([[0, 3], [10, 3], [11, 9], [15, 9]], stem, P, { steps: 28 }), { tone: "mid" }));
  out.push(L(k.knurl(-22, 0, 9, INLET_Z + 19, 4, P, 18), { tone: "lo" }));
  // The spout, over the vessel mouth.
  const spout = G.frameAlong([0, 0, INLET_Z], [0, 0, -1]);
  out.push(S(G.lathe([[0, 4.5], [9, 4.5], [10, 6]], spout, P, { steps: 28 }), { tone: "mid" }));
  out.push(D([at([-56, 0, INLET_Z])], { size: 0.5 }));
  return out.join("");
}

function gauge() {
  // Reads cp at the level, because that is the number the figure is about.
  const out = [];
  const F = G.frameAlong([GAUGE[0], GAUGE[1], GAUGE_Z], [0, 0, 1]);
  const stand = { x: GAUGE[0] - 9, y: GAUGE[1] - 7, w: 18, d: 14, r: 2 };
  out.push(S(k.slabOf(stand, 0, GAUGE_Z, P, 3, 0.6), { tone: "mid" }));
  out.push(S(G.lathe([[0, GAUGE_R], [GAUGE_H - 2, GAUGE_R], [GAUGE_H, GAUGE_R - 2.5]], F, P, { steps: 56, bevel: 0.6 }), { tone: "mid" }));
  const FACE_R = GAUGE_R - 3.5;
  out.push(L(G.circleOf(F, GAUGE_H, FACE_R, P, 56), { tone: "lo" }));
  // Two rings, as a real dial has: ticks run inward from the bezel ring and
  // the long ones land on the chapter ring, so both ends sit on a stroke.
  const CHAPTER_R = FACE_R - 7;
  out.push(L(G.circleOf(F, GAUGE_H, CHAPTER_R, P, 48), { tone: "lo" }));
  const dial = k.radialTicks(GAUGE[0], GAUGE[1], FACE_R, 40, 5, GAUGE_Z + GAUGE_H, [3.5, 7], P);
  out.push(L(dial.minor, { tone: "lo" }), L(dial.major, { tone: "mid" }));
  out.push(D(G.dotsOf(F, GAUGE_H, GAUGE_R - 1.5, 6, P, { all: true }), { size: 0.45 }));
  // A hub, so the needle's tail ends on a part rather than in the middle of a
  // blank face.
  out.push(S(k.cylinder(GAUGE[0], GAUGE[1], HUB_R, GAUGE_Z + GAUGE_H, 1.2, P, 20), { tone: "hi" }));
  out.push(L(k.ring(GAUGE[0], GAUGE[1], HUB_R, GAUGE_Z + GAUGE_H + 1.2, P, 20), { tone: "lo" }));
  return out.join("");
}

export function needleAt(fraction) {
  const angle = -Math.PI / 2 + fraction * Math.PI * 1.6 - Math.PI * 0.3;
  const tip = [GAUGE[0] + Math.cos(angle) * (GAUGE_R - 9), GAUGE[1] + Math.sin(angle) * (GAUGE_R - 9), GAUGE_Z + GAUGE_H + 0.6];
  const tail = [GAUGE[0] - Math.cos(angle) * HUB_R, GAUGE[1] - Math.sin(angle) * HUB_R, GAUGE_Z + GAUGE_H + 0.6];
  return k.segment(tail, tip, P);
}

// ---- assembly -------------------------------------------------------------
const start = levels[Math.round(LEVELS * 0.5)];

const svg = k.figureSvg({
  width: WIDTH, height: HEIGHT,
  body: [
    bench(),
    pedestal(),
    scalePost(),
    // The vessel, dark: the empty volume above the level.
    VESSEL.bands.map((band) => S(band.paths, { tone: "lo", inner: band.seam || "" })).join(""),
    // The liquid: the same body, lit, clipped at the meniscus. One shape, two
    // readings — which is the point of the object.
    // Screen y grows downward, so the liquid is the region BELOW the meniscus:
    // the rect starts at the cut, it does not end there.
    `<clipPath id="fill"><rect data-part="clip" x="0" y="${start.clip}" width="${WIDTH}" height="${HEIGHT}"/></clipPath>`,
    `<g clip-path="url(#fill)">${VESSEL.bands.map((band) => S(band.paths, { lit: true, inner: band.seam || "" })).join("")}</g>`,
    `<g class="iso-solid" data-lit><path class="iso-fill" data-part="meniscus" d="${start.disc}"/></g>`,
    `<path data-part="rim" class="iso-line" data-tone="mid" d="${start.disc}"/>`,
    // One continuous outline over the bands, so the glass reads as one body.
    L(VESSEL.sidesOf(undefined, undefined, { ends: true }).d, { tone: "mid" }),
    L(G.circleOf(AXIS, COLUMN, rOf(M.high), P, 48), { tone: "mid" }),
    L(G.circleOf(AXIS, 0, rOf(M.low), P, 48), { tone: "lo" }),
    inlet(),
    gauge(),
    `<path data-part="needle" class="iso-line" data-tone="lit" d="${needleAt(0.5)}"/>`,
  ].join(""),
});

const live = `
const P = ${JSON.stringify(P)};
const LEVELS = ${JSON.stringify(levels.map((l) => [l.energy, l.t, l.cp, l.disc, l.clip]))};
const PEAK = ${JSON.stringify(M.peak)};
const needleAt = ${needleAt.toString()
  .replace(/k\./g, "")
  .replace(/GAUGE_R/g, String(GAUGE_R))
  .replace(/GAUGE_Z/g, String(GAUGE_Z))
  .replace(/GAUGE_H/g, String(GAUGE_H))
  .replace(/HUB_R/g, String(HUB_R))
  .replace(/GAUGE/g, JSON.stringify(GAUGE))};
const stage = document.querySelector(".iso-stage");
const svg = stage.querySelector("svg");
const clip = svg.querySelector('[data-part="clip"]');
const meniscus = svg.querySelector('[data-part="meniscus"]');
const rim = svg.querySelector('[data-part="rim"]');
const needle = svg.querySelector('[data-part="needle"]');
const readout = document.querySelector("[data-readout]");
const still = matchMedia("(prefers-reduced-motion: reduce)");
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const pick = (e) => LEVELS[clamp(Math.round(e * (LEVELS.length - 1)), 0, LEVELS.length - 1)];
let energy = 0.5, target = 0.5, frame = 0, last = 0, clock = 0, touring = true, visible = false, idle = 0;
function draw() {
  const [, t, cp, disc, cut] = pick(energy);
  clip.setAttribute("y", String(cut));
  meniscus.setAttribute("d", disc);
  rim.setAttribute("d", disc);
  needle.setAttribute("d", needleAt(cp / PEAK.cp_peak));
  const text = t.toFixed(2) + " \\u00b0C \\u00b7 cp " + cp.toLocaleString("en") + " J/kg\\u00b7K";
  if (readout.textContent !== text) readout.textContent = text;
  stage.setAttribute("aria-valuenow", String(Math.round(t * 100) / 100));
  stage.setAttribute("aria-valuetext", text);
}
function tick(now) {
  const dt = last ? Math.min((now - last) / 1000, 1 / 30) : 1 / 60;
  last = now;
  const calm = still.matches;
  if (touring) { clock += dt; target = 0.5 - 0.5 * Math.cos(clock * 0.55); }
  energy = calm ? target : energy + (target - energy) * (1 - Math.exp(-dt / 0.22));
  if (Math.abs(target - energy) < 0.0004) energy = target;
  draw();
  const settled = !touring && energy === target;
  frame = visible && !settled ? requestAnimationFrame(tick) : 0;
}
const run = () => { if (!frame && visible) { last = 0; frame = requestAnimationFrame(tick); } };
const steer = (next) => { touring = false; target = clamp(next, 0, 1); clearTimeout(idle); idle = setTimeout(() => { touring = !still.matches; clock = Math.acos(1 - 2 * target) / 0.55 || 0; run(); }, 3600); run(); };
new IntersectionObserver((e) => { visible = e[e.length - 1].isIntersecting; if (visible) run(); }, { rootMargin: "120px 0px" }).observe(stage);
if (still.matches) touring = false;
stage.addEventListener("pointermove", (event) => {
  const box = svg.getBoundingClientRect();
  steer(clamp(((event.clientY - box.top) / box.height - 0.12) / 0.74, 0, 1) * -1 + 1);
});
stage.addEventListener("keydown", (event) => {
  const step = event.shiftKey ? 0.1 : 0.02;
  let to = null;
  if (event.key === "ArrowUp" || event.key === "ArrowRight") to = target + step;
  if (event.key === "ArrowDown" || event.key === "ArrowLeft") to = target - step;
  if (event.key === "Home") to = 0;
  if (event.key === "End") to = 1;
  if (to === null) return;
  event.preventDefault();
  steer(to);
});
draw();
`;

const bulge = M.bulgeShare(2.0);
const body = k.plateHtml({
  fig: "Fig 1",
  title: "CO₂ at 80 bar",
  hint: "Move up and down the column to pour heat in",
  readout: `${start.t.toFixed(2)} °C · cp ${start.cp.toLocaleString("en")} J/kg·K`,
  keys: [
    { mark: "lit", label: "The level: energy poured in. Its height is temperature." },
    { mark: "raised", label: `The wall: cross-sectional area is cp, peaking at ${M.peak.t_c} °C` },
  ],
  caption:
    `The vessel's cross-section at any height is the specific heat of CO₂ at 80 bar, so pouring energy in raises a level that is temperature and the volume beneath it is the enthalpy. ` +
    `Crossing the four degrees between ${(M.peak.t_c - 2).toFixed(1)} and ${(M.peak.t_c + 2).toFixed(1)} °C costs ${(bulge.inside * 100).toFixed(0)}% of all the energy in the window; the four degrees below 50 °C cost ${(bulge.away * 100).toFixed(1)}%. ` +
    `That is why the peak value of ${M.peak.cp_peak.toLocaleString("en")} J/kg·K is not a design number: absorbing heat is the thing that carries you out of the bulge. ` +
    `CoolProp ${data.coolprop_version}, ${data.equation_of_state}.`,
  body: `<div class="iso-stage" tabindex="0" role="slider" aria-label="Heat poured into CO2 at 80 bar; arrow keys add or remove energy" aria-valuemin="${M.low}" aria-valuemax="${M.high}" aria-valuenow="${start.t}">${svg}</div>`,
});

const name = theme === "light" ? "co2-widom-light.html" : "co2-widom.html";
writeFileSync(join(HERE, name), k.pageHtml({ title: "CO2 at 80 bar", theme, body, script: kitScript() + live }));
console.log("wrote", name);
