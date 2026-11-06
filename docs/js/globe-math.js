// Google Earth-style view: a pivot on the surface, the compass heading of the view, the tilt
// from vertical and the range from the pivot. Scene frame: x = lon 0, y = north pole, z = lon 90W.
const D2R=Math.PI/180,R2D=180/Math.PI;
export const LIMITS={minDistance:1.05,maxRange:13,maxTilt:80};
export const SPEEDS={heading:.25,tilt:.25,touch:1.5};   // degrees per pixel; two-finger gestures are faster
const dot=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const unit=(a)=>{const n=Math.hypot(...a)||1;return a.map((v)=>v/n);};
export const wrapHeading=(h)=>((h%360)+360)%360;
// Smallest range that keeps the camera LIMITS.minDistance from the centre at this tilt.
export function rangeMin(tilt){const c=Math.cos(tilt*D2R),d=LIMITS.minDistance;return -c+Math.sqrt(c*c+d*d-1);}
export function clampView({heading,tilt,range}){
  tilt=Math.min(LIMITS.maxTilt,Math.max(0,tilt));
  return {heading:wrapHeading(heading),tilt,range:Math.min(LIMITS.maxRange,Math.max(rangeMin(tilt),range))};
}
export function localFrame(n){
  n=unit(n);let east=cross([0,1,0],n);if(dot(east,east)<1e-12)east=[1,0,0];east=unit(east);
  return {east,north:unit(cross(n,east)),up:n};
}
// Camera position, screen-up and look target for a view; the pivot is a unit vector.
export function rig({pivot,heading,tilt,range}){
  const {east,north,up:n}=localFrame(pivot),ch=Math.cos(heading*D2R),sh=Math.sin(heading*D2R),ct=Math.cos(tilt*D2R),st=Math.sin(tilt*D2R);
  const h=north.map((v,i)=>v*ch+east[i]*sh);   // horizontal component of the view direction
  return {position:n.map((v,i)=>v+range*(ct*v-st*h[i])),up:h.map((v,i)=>ct*v+st*n[i]),target:n};
}
// Heading implied by a screen-up vector at a pivot (valid below 90° tilt).
export function headingOf(pivot,up){const {east,north}=localFrame(pivot);return wrapHeading(Math.atan2(dot(up,east),dot(up,north))*R2D);}
