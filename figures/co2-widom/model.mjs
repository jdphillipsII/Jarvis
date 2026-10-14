// The model. Pure: no DOM, no kit, no drawing.
//
// data.json holds cp(T) for CO2 at 80 bar straight from CoolProp. The vessel's
// cross-sectional AREA at height T is cp(T), which makes three things true at
// once and is the whole reason the object explains anything:
//
//   height          is temperature
//   area at height  is specific heat
//   volume to a level is the enthalpy change from the floor
//
// So "pour energy in" is literally "add volume", and the level rises by
// dT = dQ / cp(T). Through the bulge at the Widom line a lot of energy buys
// almost no temperature; outside it a little energy sends the level away.
//
// Everything the figure prints comes from here.

export function modelOf(data) {
  const profile = data.profile;
  const t = profile.map((p) => p.t_c);
  const r = profile.map((p) => p.r);
  // area ∝ r², and r was normalised from sqrt(cp), so area ∝ cp exactly.
  const area = r.map((v) => v * v);

  // Cumulative volume: the enthalpy axis, in the same arbitrary units as area.
  const volume = [0];
  for (let i = 1; i < t.length; i++) {
    volume.push(volume[i - 1] + 0.5 * (area[i] + area[i - 1]) * (t[i] - t[i - 1]));
  }
  const total = volume[volume.length - 1];

  const lerp = (xs, ys, x) => {
    if (x <= xs[0]) return ys[0];
    if (x >= xs[xs.length - 1]) return ys[ys.length - 1];
    let lo = 0;
    let hi = xs.length - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (xs[mid] <= x) lo = mid; else hi = mid;
    }
    const span = xs[hi] - xs[lo];
    const f = span === 0 ? 0 : (x - xs[lo]) / span;
    return ys[lo] + f * (ys[hi] - ys[lo]);
  };

  // The inverse that makes the object work: given energy poured in, where is
  // the level? This is why the peak cannot be held — absorbing heat is what
  // carries you out of it.
  const temperatureAt = (energyFraction) =>
    lerp(volume, t, Math.max(0, Math.min(1, energyFraction)) * total);

  const radiusAt = (tc) => lerp(t, r, tc);
  const cpAt = (tc) => data.pseudocritical.cp_peak * Math.pow(radiusAt(tc), 2);
  const energyAt = (tc) => lerp(t, volume, tc) / total;

  return {
    data, profile, total,
    low: t[0], high: t[t.length - 1],
    peak: data.pseudocritical,
    temperatureAt, radiusAt, cpAt, energyAt,

    // Where the lesson lives. The energy it takes to cross the bulge, against
    // the energy to cross the same width of temperature well away from it.
    bulgeShare(halfWidth) {
      const peakT = data.pseudocritical.t_c;
      const inside = energyAt(peakT + halfWidth) - energyAt(peakT - halfWidth);
      const away = energyAt(t[t.length - 1]) -
                   energyAt(t[t.length - 1] - 2 * halfWidth);
      return { inside, away, ratio: away === 0 ? Infinity : inside / away };
    },
  };
}
