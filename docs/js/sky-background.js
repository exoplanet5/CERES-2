// Star background after cislunar-eye web/sky.js and sky-style.js: own scene and camera, rotation-only, drawn first and followed by a
// depth clear, so stars sit at infinity and the Earth, Moon and tracks all draw over them.  The star core is pure grey and subdued, so
// no star competes with a track or marker colour.  The Sun is here too: it is a body at infinity on this scale.
import * as THREE from 'three';

export const SKY_BACKGROUND = '#04060c';
const STAR_CORE = '0.840, 0.840, 0.840';

// Packed Hipparcos: ra uint16 / dec int16 in units.deg, mag int16 in units.mag.
function decode(text, Type) {
  const bytes = Uint8Array.from(atob(text), (c) => c.charCodeAt(0));
  return new Type(bytes.buffer);
}
export function unpackStars(S) {
  const ra = decode(S.ra, Uint16Array), dec = decode(S.dec, Int16Array), mag = decode(S.mag, Int16Array), out = new Array(S.n);
  for (let i = 0; i < S.n; i++) out[i] = [ra[i] * S.units.deg, dec[i] * S.units.deg, mag[i] * S.units.mag];
  return out;
}
const skyDirection = (ra, dec) => {
  const a = ra * Math.PI / 180, d = dec * Math.PI / 180;
  return [Math.cos(d) * Math.cos(a), Math.sin(d), -Math.cos(d) * Math.sin(a)];
};
function starAppearance(magnitude) {
  const area = .30 * Math.max(0, 6.9 - magnitude) ** 2.0;
  return [Math.max(.6, Math.sqrt(area) * 96 / 72), Math.max(.16, Math.min(.78, .16 + .095 * (6.6 - magnitude)))];
}
function sunTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d'), r = 128, grad = g.createRadialGradient(r, r, 0, r, r, r);
  grad.addColorStop(0, 'rgba(255,255,250,1)'); grad.addColorStop(.095, 'rgba(255,252,235,1)'); grad.addColorStop(.125, 'rgba(255,232,170,.62)');
  grad.addColorStop(.28, 'rgba(255,205,120,.17)'); grad.addColorStop(.6, 'rgba(255,190,110,.04)'); grad.addColorStop(1, 'rgba(255,190,110,0)');
  g.fillStyle = grad; g.fillRect(0, 0, 256, 256);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

export class StellarBackground {
  constructor(catalog) {
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(35, 1, .01, 10);
    this.root = new THREE.Group(); this.scene.add(this.root);
    const stars = unpackStars(catalog.stars), positions = new Float32Array(stars.length * 3), style = new Float32Array(stars.length * 2);
    stars.forEach(([ra, dec, mag], i) => { positions.set(skyDirection(ra, dec), 3 * i); style.set(starAppearance(mag), 2 * i); });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('appearance', new THREE.BufferAttribute(style, 2));
    this.material = new THREE.ShaderMaterial({
      uniforms: {pixelRatio: {value: 1}}, transparent: true, depthWrite: false,
      vertexShader: `attribute vec2 appearance; uniform float pixelRatio; varying vec2 vStyle; varying float vSize;
        void main() { vStyle = appearance; gl_PointSize = max(1.0, (vStyle.x + 2.0) * pixelRatio); vSize = gl_PointSize / pixelRatio;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
      fragmentShader: `varying vec2 vStyle; varying float vSize;
        void main() { float r = length(gl_PointCoord - vec2(0.5)) * vSize;
          float core = 1.0 - smoothstep(max(0.0, vStyle.x * 0.5 - 0.5), vStyle.x * 0.5 + 0.5, r);
          float alpha = min(1.0, core * vStyle.y);
          if (alpha < 0.001) discard;
          gl_FragColor = vec4(vec3(${STAR_CORE}), alpha); }`,
    });
    this.stars = new THREE.Points(geometry, this.material); this.stars.frustumCulled = false; this.root.add(this.stars);
    // The disc is drawn at about the true 0.53 deg at the default field of view, inside a soft glare.
    this.sun = new THREE.Sprite(new THREE.SpriteMaterial({map: sunTexture(), sizeAttenuation: false, transparent: true, depthTest: false, depthWrite: false, blending: THREE.AdditiveBlending}));
    this.sun.scale.setScalar(.098); this.sun.frustumCulled = false; this.scene.add(this.sun);
  }
  // sunDir: unit vector, scene frame.  gmst: radians.  The scene is Earth-fixed, so the stars turn at -gmst.
  render(renderer, camera, gmst, sunDir) {
    this.material.uniforms.pixelRatio.value = renderer.getPixelRatio();
    this.root.rotation.y = -gmst;
    this.sun.position.set(...sunDir);
    this.camera.fov = camera.fov; this.camera.aspect = camera.aspect; this.camera.quaternion.copy(camera.quaternion);
    this.camera.updateProjectionMatrix(); this.camera.updateMatrixWorld(true);
    renderer.render(this.scene, this.camera);
  }
}

// The Moon at its true position and size, tidally oriented as in cislunar-eye web/scene/bodies.js: 0 deg longitude faces the Earth and the
// spin axis follows the ecliptic pole.  Lit by the same Sun direction as the Earth.
export function createMoon(texture, sunUniform) {
  const material = new THREE.ShaderMaterial({
    uniforms: {map: {value: texture}, sunDir: sunUniform},
    vertexShader: `varying vec2 vUv; varying vec3 vN; void main() { vUv = uv; vN = normalize(mat3(modelMatrix) * position);
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `uniform sampler2D map; uniform vec3 sunDir; varying vec2 vUv; varying vec3 vN;
      void main() { float m = clamp((dot(normalize(vN), sunDir) + 0.05) / 1.05, 0.0, 1.0);
        gl_FragColor = vec4(texture2D(map, vUv).rgb * (0.10 + 1.25 * pow(m, 0.6)), 1.0); }`,   // 0.10: earthshine, so a thin crescent still shows the disc
  });
  const mesh = new THREE.Mesh(new THREE.SphereGeometry(1737.4 / 6378.137, 64, 32), material);
  const ex = new THREE.Vector3(), ey = new THREE.Vector3(), ez = new THREE.Vector3(), pole = new THREE.Vector3(), m4 = new THREE.Matrix4();
  const EPS = 23.439 * Math.PI / 180;
  mesh.update = (moonKm, gmst, re) => {
    mesh.position.set(moonKm[0] / re, moonKm[1] / re, moonKm[2] / re);
    // Ecliptic pole in the Earth-fixed scene frame: (0, -sin e, cos e) in ICRF, turned by -gmst to Earth-fixed, mapped (x, z, -y).
    pole.set(-Math.sin(EPS) * Math.sin(gmst), Math.cos(EPS), Math.sin(EPS) * Math.cos(gmst));
    ex.copy(mesh.position).normalize().negate();
    ez.copy(pole).addScaledVector(ex, -pole.dot(ex)).normalize();
    ey.crossVectors(ez, ex);
    m4.makeBasis(ex, ez, ey.clone().negate());     // SphereGeometry local axes are (bx, bz, -by)
    mesh.quaternion.setFromRotationMatrix(m4);
  };
  return mesh;
}
