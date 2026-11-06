import * as THREE from 'three';
import {llToVec,vecToLL} from './astro.js';
import {LIMITS,SPEEDS,rangeMin,clampView,rig,headingOf} from './globe-math.js';

const D2R=Math.PI/180,R2D=180/Math.PI,lerp=THREE.MathUtils.lerp;
// Left-drag grabs the ground, right-drag (or Ctrl/Shift-drag, or two fingers) turns and tilts
// about the view point, the wheel or a pinch zooms. A short still press reports a click.
export class GlobeCamera{
  constructor(camera,element,{onClick=()=>{},onGesture=()=>{}}={}){
    Object.assign(this,{camera,element,onClick,onGesture,pivot:new THREE.Vector3(1,0,0),heading:0,tilt:0,range:2.6,targetRange:2.6,fly:null,pointers:new Map(),mode:null,press:null,grab:null,pinch:null});
    this.ray=new THREE.Raycaster();this.sphere=new THREE.Sphere(new THREE.Vector3(),1);this.hit=new THREE.Vector3();
    element.style.touchAction='none';
    element.addEventListener('pointerdown',(e)=>this.down(e));element.addEventListener('pointermove',(e)=>this.move(e));
    for(const type of ['pointerup','pointercancel'])element.addEventListener(type,(e)=>this.up(e));
    element.addEventListener('wheel',(e)=>this.wheel(e),{passive:false});element.addEventListener('contextmenu',(e)=>e.preventDefault());
    this.apply();
  }
  get(){const {lon,lat}=vecToLL(...this.pivot.toArray());return {lon,lat,heading:this.heading,tilt:this.tilt,range:this.range};}
  set({lon,lat,heading,tilt,range}={}){
    if(Number.isFinite(lon)&&Number.isFinite(lat))this.pivot.set(...llToVec(lon,lat));
    if(Number.isFinite(heading))this.heading=heading;if(Number.isFinite(tilt))this.tilt=tilt;if(Number.isFinite(range))this.range=this.targetRange=range;
    this.fly=null;this.apply();
  }
  apply(){
    this.pivot.normalize();Object.assign(this,clampView(this));this.targetRange=Math.min(LIMITS.maxRange,Math.max(rangeMin(this.tilt),this.targetRange));
    const {position,up}=rig({pivot:this.pivot.toArray(),heading:this.heading,tilt:this.tilt,range:this.range});
    this.camera.position.set(...position);this.camera.up.set(...up);this.camera.lookAt(this.pivot);this.camera.updateMatrixWorld();
  }
  update(now,dt){
    if(this.fly){const f=this.fly,k=Math.min(1,(now-f.start)/f.duration),t=k*k*(3-2*k);
      this.pivot.copy(f.from.pivot).lerp(f.to.pivot,t);this.heading=lerp(f.from.heading,f.to.heading,t);this.tilt=lerp(f.from.tilt,f.to.tilt,t);this.range=this.targetRange=lerp(f.from.range,f.to.range,t);if(k===1)this.fly=null;}
    else if(this.range!==this.targetRange){this.range+=(this.targetRange-this.range)*(1-Math.exp(-dt*12));if(Math.abs(this.targetRange-this.range)<1e-5)this.range=this.targetRange;}
    this.apply();
  }
  flyTo({lon,lat,range=this.range,heading=0,tilt=0},duration=1200){
    const from={pivot:this.pivot.clone(),heading:this.heading,tilt:this.tilt,range:this.range},to={pivot:new THREE.Vector3(...llToVec(lon,lat)),heading,tilt,range};
    if(from.pivot.dot(to.pivot)<-.999)from.pivot.lerp(new THREE.Vector3(0,1,0),.01).normalize();   // antipodes: pick a path
    to.heading=from.heading+((to.heading-from.heading+540)%360)-180;   // turn the short way round
    this.fly={from,to,start:performance.now(),duration};
  }
  approach(unit,k){this.pivot.lerp(unit,k);}   // follow mode; apply() renormalises
  scaleRange(f){this.range*=f;this.targetRange*=f;this.apply();}
  zoomBy(f){this.targetRange=Math.min(LIMITS.maxRange,Math.max(rangeMin(this.tilt),this.targetRange*f));}
  unitAt(x,y){
    const r=this.element.getBoundingClientRect();if(!(r.width>0&&r.height>0))return null;
    this.camera.updateMatrixWorld();this.ray.setFromCamera({x:(x-r.left)/r.width*2-1,y:1-(y-r.top)/r.height*2},this.camera);
    return this.ray.ray.intersectSphere(this.sphere,this.hit)?this.hit.clone():null;
  }
  groundAt(x,y){const u=this.unitAt(x,y);return u?vecToLL(u.x,u.y,u.z):null;}
  // A rigid rotation about the globe centre keeps tilt and range; the heading follows the rotated screen-up.
  rotate(q){const up=this.camera.up.clone().applyQuaternion(q);this.pivot.applyQuaternion(q);this.heading=headingOf(this.pivot.toArray(),up.toArray());this.apply();}
  centerRate(){return 2*this.range*Math.tan(this.camera.fov*D2R/2)/Math.max(1,this.element.clientHeight);}   // radians per pixel at the pivot
  grabTo(x,y,dx,dy){
    const c=this.unitAt(x,y),rate=this.centerRate();
    if(!c){const m=this.camera.matrixWorld.elements,right=new THREE.Vector3(m[0],m[1],m[2]),up=new THREE.Vector3(m[4],m[5],m[6]);
      this.rotate(new THREE.Quaternion().setFromAxisAngle(up,2*dx*rate).multiply(new THREE.Quaternion().setFromAxisAngle(right,2*dy*rate)));this.grab=null;return;}
    if(!this.grab){this.grab=c;return;}
    const angle=c.angleTo(this.grab),cap=4*rate*Math.hypot(dx,dy);
    if(angle<1e-7)return;
    this.rotate(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3().crossVectors(c,this.grab).normalize(),Math.min(angle,cap)));
    if(angle>cap)this.grab=this.unitAt(x,y);   // foreshortened ground near the limb slips at a bounded rate
  }
  pivotBy(dx,dy,k=1){this.heading+=dx*SPEEDS.heading*k;this.tilt-=dy*SPEEDS.tilt*k;this.apply();}
  measure(){const [a,b]=[...this.pointers.values()];return {x:(a.x+b.x)/2,y:(a.y+b.y)/2,dist:Math.hypot(b.x-a.x,b.y-a.y),angle:Math.atan2(b.y-a.y,b.x-a.x)};}
  pinchMove(){
    const p=this.pinch,n=this.measure(),twist=((n.angle-p.angle+3*Math.PI)%(2*Math.PI))-Math.PI;
    this.heading+=(n.x-p.x)*SPEEDS.heading*SPEEDS.touch-twist*R2D;this.tilt-=(n.y-p.y)*SPEEDS.tilt*SPEEDS.touch;
    if(n.dist>1&&p.dist>1){this.range*=p.dist/n.dist;this.targetRange=this.range;}
    this.pinch=n;this.apply();
  }
  down(e){
    if(e.button>2)return;
    try{this.element.setPointerCapture(e.pointerId);}catch{}
    this.pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});this.fly=null;this.onGesture('drag');
    if(this.pointers.size===1){
      const pivot=e.pointerType==='mouse'&&(e.button!==0||e.ctrlKey||e.shiftKey||e.metaKey);
      this.mode=pivot?'pivot':'grab';this.grab=pivot?null:this.unitAt(e.clientX,e.clientY);
      this.press=!pivot&&e.button===0?{x:e.clientX,y:e.clientY,t:performance.now(),slop:e.pointerType==='mouse'?4:10}:null;
    }else{this.mode='pinch';this.press=null;this.grab=null;this.pinch=this.measure();}
    this.element.style.cursor=this.mode==='pivot'?'move':'grabbing';
  }
  move(e){
    const p=this.pointers.get(e.pointerId);if(!p)return;
    const dx=e.clientX-p.x,dy=e.clientY-p.y;p.x=e.clientX;p.y=e.clientY;
    if(this.press){if(Math.hypot(e.clientX-this.press.x,e.clientY-this.press.y)<=this.press.slop)return;this.press=null;}
    if(this.mode==='grab'&&this.pointers.size===1)this.grabTo(e.clientX,e.clientY,dx,dy);
    else if(this.mode==='pivot'&&this.pointers.size===1)this.pivotBy(dx,dy);
    else if(this.mode==='pinch'&&this.pointers.size===2)this.pinchMove();
  }
  up(e){
    const p=this.pointers.get(e.pointerId);if(!p)return;
    this.pointers.delete(e.pointerId);try{this.element.releasePointerCapture(e.pointerId);}catch{}
    const press=this.press;this.press=null;
    if(this.pointers.size===1){const [q]=this.pointers.values();this.mode='grab';this.grab=this.unitAt(q.x,q.y);this.pinch=null;return;}
    if(this.pointers.size)return;
    this.mode=null;this.grab=null;this.pinch=null;this.element.style.cursor='';
    if(press&&e.type==='pointerup'&&performance.now()-press.t<600&&Math.hypot(e.clientX-press.x,e.clientY-press.y)<=press.slop)this.onClick(e.clientX,e.clientY,e);
  }
  wheel(e){
    e.preventDefault();const dy=Math.max(-1000,Math.min(1000,e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?this.element.clientHeight:1)));
    this.fly=null;this.onGesture('zoom');this.zoomBy(Math.pow(.95,-dy*.009));
  }
}
