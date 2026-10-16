// Generated from a figure genome by core/figure_compiler.py.
// Positions are solved from each part's `on:`; edit the genome, not this.
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = process.env.ANATOMY_ROOT
  || join(HERE, "..", "..", ".claude", "skills", "anatomy");
const k = await import(join(ROOT, "kit", "iso-kit.mjs"));
const G = await import(join(ROOT, "kit", "lathe.mjs"));
const { kitScript } = await import(join(ROOT, "scripts", "inline-kit.mjs"));
const theme = process.argv.includes("--light") ? "light" : "dark";

const WIDTH = 760, HEIGHT = 520;
const P = k.fitProjection([[-150.0, -150.0, 0.0], [-150.0, -150.0, 13.0], [-150.0, 150.0, 0.0], [-150.0, 150.0, 13.0], [150.0, -150.0, 0.0], [150.0, -150.0, 13.0], [150.0, 150.0, 0.0], [150.0, 150.0, 13.0], [-133.0, -53.0, -6.0], [-133.0, -53.0, 0.0], [-133.0, -39.0, -6.0], [-133.0, -39.0, 0.0], [-119.0, -53.0, -6.0], [-119.0, -53.0, 0.0], [-119.0, -39.0, -6.0], [-119.0, -39.0, 0.0], [0.0, 0.0, 13.0], [0.0, 0.0, 13.0], [0.0, 0.0, 13.0], [0.0, 0.0, 13.0], [0.0, 0.0, 13.0], [0.0, 0.0, 13.0], [0.0, 0.0, 13.0], [0.0, 0.0, 13.0], [0.0, 0.0, 13.0], [0.0, 0.0, 13.0], [0.0, 0.0, 13.0], [0.0, 0.0, 13.0], [0.0, 0.0, 13.0], [0.0, 0.0, 13.0], [0.0, 0.0, 13.0], [0.0, 0.0, 13.0], [-118.0, -118.0, 13.0], [-118.0, -118.0, 18.0], [-118.0, 118.0, 13.0], [-118.0, 118.0, 18.0], [118.0, -118.0, 13.0], [118.0, -118.0, 18.0], [118.0, 118.0, 13.0], [118.0, 118.0, 18.0], [-104.0, -30.0, 13.0], [-104.0, -30.0, 109.0], [-104.0, 30.0, 13.0], [-104.0, 30.0, 109.0], [-44.0, -30.0, 13.0], [-44.0, -30.0, 109.0], [-44.0, 30.0, 13.0], [-44.0, 30.0, 109.0], [-85.0, -11.0, 47.0], [-85.0, -11.0, 47.0], [-85.0, 11.0, 47.0], [-85.0, 11.0, 47.0], [-63.0, -11.0, 47.0], [-63.0, -11.0, 47.0], [-63.0, 11.0, 47.0], [-63.0, 11.0, 47.0], [-30.0, -30.0, 13.0], [-30.0, -30.0, 109.0], [-30.0, 30.0, 13.0], [-30.0, 30.0, 109.0], [30.0, -30.0, 13.0], [30.0, -30.0, 109.0], [30.0, 30.0, 13.0], [30.0, 30.0, 109.0], [-11.0, -11.0, 47.0], [-11.0, -11.0, 47.0], [-11.0, 11.0, 47.0], [-11.0, 11.0, 47.0], [11.0, -11.0, 47.0], [11.0, -11.0, 47.0], [11.0, 11.0, 47.0], [11.0, 11.0, 47.0], [44.0, -30.0, 13.0], [44.0, -30.0, 109.0], [44.0, 30.0, 13.0], [44.0, 30.0, 109.0], [104.0, -30.0, 13.0], [104.0, -30.0, 109.0], [104.0, 30.0, 13.0], [104.0, 30.0, 109.0], [63.0, -11.0, 47.0], [63.0, -11.0, 47.0], [63.0, 11.0, 47.0], [63.0, 11.0, 47.0], [85.0, -11.0, 47.0], [85.0, -11.0, 47.0], [85.0, 11.0, 47.0], [85.0, 11.0, 47.0], [-118.0, -66.0, 13.0], [-118.0, -66.0, 13.8], [-118.0, 170.0, 13.0], [-118.0, 170.0, 13.8], [118.0, -66.0, 13.0], [118.0, -66.0, 13.8], [118.0, 170.0, 13.0], [118.0, 170.0, 13.8], [0.0, 52.0, 13.8], [0.0, 52.0, 13.8], [0.0, 52.0, 13.8], [0.0, 52.0, 13.8], [0.0, 52.0, 13.8], [0.0, 52.0, 13.8], [0.0, 52.0, 13.8], [0.0, 52.0, 13.8], [107.0, -55.0, 13.0], [107.0, -55.0, 27.0], [107.0, -33.0, 13.0], [107.0, -33.0, 27.0], [129.0, -55.0, 13.0], [129.0, -55.0, 27.0], [129.0, -33.0, 13.0], [129.0, -33.0, 27.0], [-119.0, -7.0, 18.0], [-119.0, -7.0, 27.0], [-119.0, 7.0, 18.0], [-119.0, 7.0, 27.0], [-105.0, -7.0, 18.0], [-105.0, -7.0, 27.0], [-105.0, 7.0, 18.0], [-105.0, 7.0, 27.0]], WIDTH, HEIGHT, { pad: 28, azimuth: 42 });
const at = (p) => k.iso(p, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const D = (points, style) => k.dotsSvg(points, style);
const body = [];

// bed — slab, the bench everything stands on
body.push(S(k.slabOf({ x: -150, y: -65, w: 300, d: 130, r: 7.8 }, 0, 13, P, 6, 0.8), { tone: "mid" }));

// foot — cylinder
body.push(S(k.cylinder(-126, -46, 7, -6, 6, P, 28), { tone: "lo" }));

// feet — pattern, the other side of the pair
body.push(S(k.cylinder(126, -46, 7, -6, 6, P, 28), { tone: "lo" }));

// screws — dots
body.push(D([at([-138.0, -53.0, 13.0]), at([-138.0, 53.0, 13.0]), at([138.0, -53.0, 13.0]), at([138.0, 53.0, 13.0])], { size: 0.5 }));

// rail — slab, the path a call takes from entry to execution
body.push(S(k.slabOf({ x: -118, y: -4.5, w: 236, d: 9, r: 0.54 }, 13, 5, P, 6, 0.8), { tone: "mid" }));

// gate_agency — slab, first — a tool above the ceiling is never even shown
body.push(S(k.slabOf({ x: -77.5, y: -30, w: 7, d: 60, r: 0.42 }, 13, 96, P, 6, 0.8), { tone: "mid" }));

// aperture_agency — ring
body.push(L(k.ring(-74, 0, 11, 47, P, 36), { tone: "lo" }));

// gate_schema — slab, second — arguments are checked before the handler is entered
body.push(S(k.slabOf({ x: -3.5, y: -30, w: 7, d: 60, r: 0.42 }, 13, 96, P, 6, 0.8), { tone: "mid" }));

// aperture_schema — ring
body.push(L(k.ring(0, 0, 11, 47, P, 36), { tone: "lo" }));

// gate_consent — slab, third — anything mutating returns a proposal, not a result
body.push(S(k.slabOf({ x: 70.5, y: -30, w: 7, d: 60, r: 0.42 }, 13, 96, P, 6, 0.8), { tone: "mid" }));

// aperture_consent — ring
body.push(L(k.ring(74, 0, 11, 47, P, 36), { tone: "lo" }));

// scale — slab
body.push(S(k.slabOf({ x: -118, y: 48.5, w: 236, d: 7, r: 0.42 }, 13, 0.8, P, 6, 0.8), { tone: "lo" }));

// graduations — ticks
body.push(L([k.segment([-102.66666666666667, 52.0, 13.8], [-100.26666666666667, 52.0, 13.8], P), k.segment([-93.33333333333334, 52.0, 13.8], [-90.93333333333334, 52.0, 13.8], P), k.segment([-84.0, 52.0, 13.8], [-81.6, 52.0, 13.8], P), k.segment([-74.66666666666667, 52.0, 13.8], [-72.26666666666667, 52.0, 13.8], P), k.segment([-65.33333333333333, 52.0, 13.8], [-62.93333333333333, 52.0, 13.8], P), k.segment([-46.66666666666666, 52.0, 13.8], [-44.26666666666666, 52.0, 13.8], P), k.segment([-37.33333333333334, 52.0, 13.8], [-34.933333333333344, 52.0, 13.8], P), k.segment([-28.0, 52.0, 13.8], [-25.6, 52.0, 13.8], P), k.segment([-18.666666666666657, 52.0, 13.8], [-16.26666666666666, 52.0, 13.8], P), k.segment([-9.333333333333343, 52.0, 13.8], [-6.9333333333333425, 52.0, 13.8], P), k.segment([9.333333333333329, 52.0, 13.8], [11.733333333333329, 52.0, 13.8], P), k.segment([18.666666666666686, 52.0, 13.8], [21.066666666666684, 52.0, 13.8], P), k.segment([28.0, 52.0, 13.8], [30.4, 52.0, 13.8], P), k.segment([37.333333333333314, 52.0, 13.8], [39.73333333333331, 52.0, 13.8], P), k.segment([46.666666666666686, 52.0, 13.8], [49.066666666666684, 52.0, 13.8], P), k.segment([65.33333333333331, 52.0, 13.8], [67.73333333333332, 52.0, 13.8], P), k.segment([74.66666666666669, 52.0, 13.8], [77.06666666666669, 52.0, 13.8], P), k.segment([84.0, 52.0, 13.8], [86.4, 52.0, 13.8], P), k.segment([93.33333333333331, 52.0, 13.8], [95.73333333333332, 52.0, 13.8], P), k.segment([102.66666666666669, 52.0, 13.8], [105.06666666666669, 52.0, 13.8], P)].join(''), { tone: "lo" }));
body.push(L([k.segment([-112.0, 52.0, 13.8], [-107.5, 52.0, 13.8], P), k.segment([-56.0, 52.0, 13.8], [-51.5, 52.0, 13.8], P), k.segment([0.0, 52.0, 13.8], [4.5, 52.0, 13.8], P), k.segment([56.0, 52.0, 13.8], [60.5, 52.0, 13.8], P), k.segment([112.0, 52.0, 13.8], [116.5, 52.0, 13.8], P)].join(''), { tone: "mid" }));

// knob — knurl, the only control a person has — raising agency is a deliberate act
body.push(S(k.cylinder(118, -44, 11, 13, 14, P, 28), { tone: "mid" }));
body.push(L(k.knurl(118, -44, 11, 27, 14, P, 18), { tone: "lo" }));

// token — cylinder, one call, travelling
body.push(S(k.cylinder(-112, 0, 7, 18, 9, P, 28), { tone: "hi", lit: true }));

const svg = k.figureSvg({ width: WIDTH, height: HEIGHT, body: body.join("") });
const page = k.plateHtml({
  fig: "Fig 1",
  title: "Tool Gate",
  hint: "Hover to drive the mechanism",
  readout: "the call travelling the rail",
  keys: [
    { mark: "lit", label: "the call travelling the rail" },
  ],
  caption: "why a tool call that fails the first gate never reaches the second, and why the order is not negotiable",
  body: `<div class="iso-stage" tabindex="0">${svg}</div>`,
});
const name = theme === "light" ? "tool_gate-light.html" : "tool_gate.html";
writeFileSync(join(HERE, name), k.pageHtml({ title: "Tool Gate", theme, body: page, script: kitScript() }));
console.log("wrote", name);
