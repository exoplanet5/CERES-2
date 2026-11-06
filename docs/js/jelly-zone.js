// Twilight-jelly zones, recomputed for each T0.  Same definition as jelly_ceres2.py: the sunlit powered vehicle reaches the minimum elevation
// and the ground point is on the night side.  The solid burns and the small S4 plume are kept apart.
// The grid holds the highest elevation above that minimum.  The night clip is not on the grid: the zone shader computes it per pixel from the
// same Sun vector as the Sun 0 line, so the zone meets that line exactly at every zoom.  Areas use one reference epoch, the sunlight pickup.
import * as THREE from 'three';
import * as A from './astro.js';
import {sunlightClearance} from './profile.js';

const R_AREA = 6371, S4_THIN = 3;

export function createJellyZones(meta, asc, poweredAt, sunAt) {
  const cfg = meta.visibility, [lon0, lon1, lat0, lat1] = cfg.extent, step = cfg.grid_step_deg;
  const nx = Math.round((lon1 - lon0) / step) + 1, ny = Math.round((lat1 - lat0) / step) + 1, n = nx * ny;
  const O = new Float64Array(n * 3), U = new Float64Array(n * 3), cellArea = new Float64Array(ny);
  const rad = step * A.D2R;
  for (let j = 0; j < ny; j++) {
    const lat = lat0 + j * step;
    cellArea[j] = R_AREA * R_AREA * rad * rad * Math.cos(lat * A.D2R);
    for (let i = 0; i < nx; i++) {
      const fr = A.siteFrame(lon0 + i * step, lat), k = j * nx + i;
      O.set(fr.P, 3 * k);
      U.set(fr.U, 3 * k);
    }
  }
  const minElev = A.MIN_ELEVATION_DEG, primeSun = meta.jelly?.prime_sun_deg ?? -6;
  const count = Math.ceil((asc.end - asc.met0) / cfg.time_step_s);
  const maxSine = (list, out) => {
    out.fill(-1);
    for (const p of list) {
      const px = p[0], py = p[1], pz = p[2];
      for (let k = 0, q = 0; k < n; k++, q += 3) {
        const x = px - O[q], y = py - O[q + 1], z = pz - O[q + 2], s = (x * U[q] + y * U[q + 1] + z * U[q + 2]) / Math.sqrt(x * x + y * y + z * z);
        if (s > out[k]) out[k] = s;
      }
    }
  };
  const sineS = new Float64Array(n), sine4 = new Float64Array(n);

  return (T0, pickupMet) => {
    const solid = [], s4 = [];
    for (let k = 0, c4 = 0; k <= count; k++) {
      const met = asc.met0 + (asc.end - asc.met0) * k / count;
      if (!poweredAt(met)) continue;
      const p = asc.sample(met).p;
      if (sunlightClearance(p, sunAt(T0 + met * 1000)) <= 0) continue;
      if (met <= meta.solid_end_met) solid.push(p);
      else if (c4++ % S4_THIN === 0) s4.push(p);
    }
    maxSine(solid, sineS);
    maxSine(s4, sine4);
    const sun = sunAt(T0 + pickupMet * 1000), elevSolid = new Float32Array(n), elevS4 = new Float32Array(n);
    let areaSolid = 0, areaPrime = 0, areaS4 = 0;
    for (let j = 0; j < ny; j++) {
      for (let i = 0; i < nx; i++) {
        const k = j * nx + i, q = 3 * k;
        const a = Math.asin(Math.max(-1, Math.min(1, sineS[k]))) * A.R2D - minElev, b = Math.asin(Math.max(-1, Math.min(1, sine4[k]))) * A.R2D - minElev;
        elevSolid[k] = a;
        elevS4[k] = b;
        const dx = sun[0] - O[q], dy = sun[1] - O[q + 1], dz = sun[2] - O[q + 2];
        const sunEl = Math.asin((dx * U[q] + dy * U[q + 1] + dz * U[q + 2]) / Math.sqrt(dx * dx + dy * dy + dz * dz)) * A.R2D;
        if (sunEl <= 0) {
          if (a > 0) areaSolid += cellArea[j];
          else if (b > 0) areaS4 += cellArea[j];
        }
        if (a > 0 && sunEl <= primeSun) areaPrime += cellArea[j];
      }
    }
    return {nx, ny, lon0, lat0, dx: step, dy: step, elevSolid, elevS4, areaSolid, areaPrime, areaS4, samples: solid.length + s4.length};
  };
}

// One sphere shell that shades both zones per pixel.  sunDir is the uniform the Earth and Sun lines already use.
export function createZoneLayer(sunDirUniform, colors) {
  const material = new THREE.ShaderMaterial({
    uniforms: {field: {value: null}, box: {value: new THREE.Vector4()}, sunDir: sunDirUniform},
    transparent: true, depthWrite: false, side: THREE.FrontSide,
    vertexShader: `varying vec3 vP; void main() { vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `uniform sampler2D field; uniform vec4 box; uniform vec3 sunDir; varying vec3 vP;
      const float R2D = 57.29577951;
      float fill(float v) { float w = max(fwidth(v), 1e-5); return smoothstep(-w, w, v); }
      float edge(float v) { return 1.0 - smoothstep(0.55, 1.35, abs(v) / max(fwidth(v), 1e-5)); }
      void main() {
        vec3 n = normalize(vP);
        vec2 uv = (vec2(atan(-n.z, n.x), asin(n.y)) * R2D - box.xy) * box.zw;
        if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) discard;
        vec2 e = texture2D(field, uv).rg;
        float night = fill(-dot(n, sunDir));
        float s = fill(e.r), f = fill(e.g);
        float a = night * max(s * 0.09, (1.0 - s) * f * 0.05);
        vec3 c = mix(vec3(${colors.s4}), vec3(1.0), s);
        float ls = night * edge(e.r) * 0.92, lf = night * edge(e.g) * (1.0 - s) * 0.75;
        c = mix(c, vec3(${colors.s4}), lf); a = max(a, lf);
        c = mix(c, vec3(1.0), ls); a = max(a, ls);
        if (a < 0.003) discard;
        gl_FragColor = vec4(c, a);
      }`,
  });
  const mesh = new THREE.Mesh(new THREE.SphereGeometry(1.0012, 256, 128), material);
  let texture = null;
  mesh.setZones = (Z) => {
    if (!texture) {
      texture = new THREE.DataTexture(new Uint16Array(Z.nx * Z.ny * 2), Z.nx, Z.ny, THREE.RGFormat, THREE.HalfFloatType);
      texture.internalFormat = 'RG16F';
      texture.magFilter = texture.minFilter = THREE.LinearFilter;
      texture.wrapS = texture.wrapT = THREE.ClampToEdgeWrapping;
      material.uniforms.field.value = texture;
      // Grid nodes sit on texel centres: u = ((lon - lon0)/dx + 0.5)/nx.
      material.uniforms.box.value.set(Z.lon0 - Z.dx / 2, Z.lat0 - Z.dy / 2, 1 / (Z.dx * Z.nx), 1 / (Z.dy * Z.ny));
    }
    const data = texture.image.data, half = THREE.DataUtils.toHalfFloat;
    for (let k = 0, q = 0; k < Z.elevSolid.length; k++) { data[q++] = half(Z.elevSolid[k]); data[q++] = half(Z.elevS4[k]); }
    texture.needsUpdate = true;
  };
  return mesh;
}

// Highest elevation of the sunlit solid-motor flight from each listed site, with the Sun's altitude at that moment.
export function viewerTable(cities, asc, solidEnd, J, sunAt, T0, poweredAt, stepS = 2) {
  const samples = [];
  for (let met = J.pickup?.met ?? 0; met <= solidEnd; met += stepS) {
    if (!poweredAt(met)) continue;
    const s = asc.sample(met), sun = sunAt(T0 + met * 1000);
    if (sunlightClearance(s.p, sun) > 0) samples.push({met, p: s.p, sun});
  }
  return cities.map(([name, lon, lat]) => {
    const fr = A.siteFrame(lon, lat);
    let best = null;
    for (const q of samples) {
      const la = A.lookAngles(fr, q.p);
      if (!best || la.el > best.el) best = {el: la.el, az: la.az, met: q.met, sun: A.lookAngles(fr, q.sun).el};
    }
    return {name, lon, lat, ...(best || {el: -90, az: 0, met: 0, sun: 0})};
  }).sort((a, b) => b.el - a.el);
}
