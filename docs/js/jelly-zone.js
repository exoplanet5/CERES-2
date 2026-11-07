// The twilight-jelly shell. The grid itself is in jelly-grid.js; both names stay importable from here.
import * as THREE from 'three';
export {createJellyZones, viewerTable} from './jelly-grid.js';

export function createZoneLayer(sunDirUniform, colors, extent = null) {
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
        float lon = atan(-n.z, n.x) * R2D; if (lon < box.x) lon += 360.0;   // extents may run past 180 east
        vec2 uv = (vec2(lon, asin(n.y) * R2D) - box.xy) * box.zw;
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
  // Only the extent, two degrees beyond the grid, since the shader discards everything outside the field: the whole-sphere shell cost
  // about 1 ms of GPU time per frame at 2x for a field covering 3 % of the surface. Without an extent there is nothing to draw.
  const r = 1.0012, seg = (deg) => Math.max(4, Math.ceil(deg / 1.4));
  let geometry = new THREE.SphereGeometry(r, 8, 4);
  if (extent) {
    const [w, e, s, n] = extent, west = w - 2, east = e + 2, south = Math.max(-90, s - 2), north = Math.min(90, n + 2);
    geometry = new THREE.SphereGeometry(r, seg(east - west), seg(north - south), (west + 180) * Math.PI / 180, (east - west) * Math.PI / 180, (90 - north) * Math.PI / 180, (north - south) * Math.PI / 180);
  }
  const mesh = new THREE.Mesh(geometry, material);
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

