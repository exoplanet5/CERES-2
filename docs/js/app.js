import * as THREE from 'three';
import {Line2} from 'three/addons/lines/Line2.js';
import {LineGeometry} from 'three/addons/lines/LineGeometry.js';
import {LineMaterial} from 'three/addons/lines/LineMaterial.js';
import {LineSegments2} from 'three/addons/lines/LineSegments2.js';
import {LineSegmentsGeometry} from 'three/addons/lines/LineSegmentsGeometry.js';
import {CSS2DRenderer, CSS2DObject} from 'three/addons/renderers/CSS2DRenderer.js';
import * as A from './astro.js';
import {fetchJSON, validateManifest, validateMission, selectProfile, createFlight, solarEphemeris, sunlightClearance, computeJelly, clockSeconds, clamp, escapeHTML as esc} from './profile.js';
import {createSkyChart} from './skychart.js';
import {validateBoundaries,boundarySegments} from './boundaries.js';
import {createMapTiles} from './map-tiles.js';
import {createBoundaryLayer} from './boundary-layer.js';
import {CITIES,cityInRange} from './cities.js';
import {GlobeCamera} from './globe-camera.js';
import {createZoneLayer} from './jelly-zone.js';
import {createJellyZones,viewerTable} from './jelly-grid.js';
import {StellarBackground,createMoon,SKY_BACKGROUND} from './sky-background.js';
import {drawVehicle,vehicleStateAt,genericStack} from './vehicle-art.js';

const $ = (id) => document.getElementById(id);
const C = {sun:'#ffd54f',accent:'#4fc3f7',ink:'#e8eaed',dim:'#9aa4ae',ascent:'#d95926',orbit:'#c77dff',footprint:'#199e70',s4:'#7ad97a'};
const qs = new URLSearchParams(location.search);
const message = (text) => { $('notice').textContent = text; };
function fail(error) {
  console.error(error);
  if ($('loading')) $('loadmsg').textContent = `Unable to start: ${error.message}. Check the local server and reload.`;
  else message(error.message);
}
addEventListener('unhandledrejection',(e) => fail(e.reason instanceof Error ? e.reason : new Error(String(e.reason))));

try { await start(); } catch (error) { fail(error); }
async function start() {
  const index = validateManifest(await fetchJSON('./data/profiles.json'));
  const {profile,entry} = selectProfile(index,qs);
  const data = validateMission(await fetchJSON('./'+entry.file)), M = data.meta;
  const {tracks:T,flight,shipAt,poweredAt,end:MET_END} = createFlight(data), ASC = T.ascent;
  const moonAt = data.moon ? solarEphemeris(data.moon) : null, sunAt = solarEphemeris(data.sun), sunVecAt = (utc) => { const p=sunAt(utc),r=Math.hypot(...p);return p.map((v)=>v/r); };
  const sunSubpoint = (utc) => A.vecToLL(...sunAt(utc));
  const t0Min=clockSeconds(M.t0_min), t0Max=clockSeconds(M.t0_max), metMin=-600;
  const num = (key,def,lo,hi) => qs.has(key) && Number.isFinite(+qs.get(key)) ? clamp(+qs.get(key),lo,hi) : def;
  const requestedT0=clockSeconds(qs.get('t0'));
  const state = {date:M.date,t0:Number.isFinite(requestedT0)?clamp(requestedT0,t0Min,t0Max):clockSeconds(M.t0_default),
    met:num('met',M.met_default??300,metMin,MET_END),follow:qs.get('follow')==='1',playing:false,live:false,speed:num('speed',10,1,300),
    show:Object.fromEntries(['term','zones','labels','gt','jelly','vis','falls','sky','grid','lights','cities','fp','borders'].map((k)=>[k,qs.get(k)!=='0']))};
  const t0ms=()=>A.dateT0ms(M.date,state.t0), phaseOf=(met)=>(M.phases.find((p)=>met<p.until)||M.phases.at(-1)).label;
  function styleAt(met,T0) {
    const s=shipAt(met),lit=sunlightClearance(s.p,sunAt(T0+met*1000))>0,powered=poweredAt(met);
    return {lit,powered,color:powered?(lit?C.sun:C.ascent):C.orbit};
  }
  // Optional mission fields. meta.jelly adds the jelly panel and 10° zones; meta.solid_end_met splits the sunlit arc into solid and upper-stage plumes.
  const hasJelly=!!M.jelly,hasSolid=Number.isFinite(M.solid_end_met),solidEnd=hasSolid?M.solid_end_met:MET_END,seco=M.s4_cutoff_met??M.insertion_met,localZone=M.local_time??{label:'CST',offset_h:8},stack=M.stack??genericStack(M),ALL_CITIES=[...CITIES,...(M.extra_cities??[])];
  if(!hasJelly)state.show.vis=false;
  let J=computeJelly(ASC,sunAt,t0ms()), tablesDirty=true;
  const dirty=()=>{tablesDirty=true;};
  $('ttl').textContent=M.vehicle; $('ttlsub').textContent=M.date;
  $('subt').textContent=`${M.mission} · ${M.inc.toFixed(1)}° · ${M.orbit_revolutions} revolutions`;
  $('profile-summary').textContent=`${M.perigee_km.toFixed(0)} × ${M.apogee_km.toFixed(0)} km · i ${M.inc.toFixed(2)}°`;
  $('datev').textContent=M.date;
  $('model-badge').textContent=M.model_badge??'Pre-launch model';
  $('c-zone').textContent=localZone.label;
  $('tle-note').textContent=`Model TLE for the modeled ${Math.round((M.perigee_km+M.apogee_km)/2)} km orbit, not a catalog element set. A changed T0 shifts epoch and RAAN for the same Earth-fixed path; the viewer uses numerical track samples, not SGP4 propagation.`;
  document.body.classList.toggle('no-jelly',!hasJelly);
  if(M.jelly?.pickup_note)$('jelly-note').textContent=M.jelly.pickup_note;
  if(M.jelly?.viewers_title)$('viewers-title').textContent=M.jelly.viewers_title;
  if(M.jelly?.viewers_note)$('viewers-note').textContent=M.jelly.viewers_note;

  // Phones and low-memory devices skip the 8K maps and, at 2x, MSAA, which costs about 270 MB on a large screen. Hi-dpi desktops keep MSAA: thin lines are this page's main content.
  const lightDevice=Math.min(innerWidth,innerHeight)<=600||(navigator.deviceMemory??8)<8;
  const view=$('view'), renderer=new THREE.WebGLRenderer({antialias:!lightDevice||devicePixelRatio<2,powerPreference:'high-performance'});
  renderer.setPixelRatio(Math.min(devicePixelRatio,2)); view.appendChild(renderer.domElement);
  const labels=new CSS2DRenderer(); Object.assign(labels.domElement.style,{position:'absolute',inset:'0',pointerEvents:'none'});view.appendChild(labels.domElement);
  renderer.autoClear=false;renderer.setClearColor(SKY_BACKGROUND);
  const scene=new THREE.Scene();
  const camera=new THREE.PerspectiveCamera(35,1,0.005,200);
  // Google Earth-style camera: left-drag grabs the globe, right-drag or two fingers tilt and turn about the view point.
  const cam=new GlobeCamera(camera,renderer.domElement,{onClick:(x,y)=>pick(x,y),onGesture:(kind)=>{if(kind==='drag')setFollow(false);}});
  const materials=new Set(), Y=new THREE.Vector3(0,1,0);
  function line(flat,{color=C.ink,width=1.8,opacity=1,dashed=false}={}) {
    const g=new LineGeometry();g.setPositions(flat);
    const m=new LineMaterial({color,linewidth:width,transparent:opacity<1||dashed,opacity,dashed,dashSize:.008,gapSize:.006,depthTest:true});
    m.resolution.set(view.clientWidth,view.clientHeight); materials.add(m);
    const l=new Line2(g,m);if(dashed)l.computeLineDistances();return l;
  }
  function group() {const g=new THREE.Group();scene.add(g);return g;}
  function clear(g) {
    g.traverse((o)=>{o.geometry?.dispose();if(o.material){materials.delete(o.material);o.material.dispose();}if(o.isCSS2DObject)o.element.remove();});g.clear();
  }
  function label(text,cls='') {const el=document.createElement('div');el.className='lbl '+cls;el.textContent=text;const o=new CSS2DObject(el);o.center.set(0,.5);return o;}
  function texture(draw,size=64) {const cv=document.createElement('canvas');cv.width=cv.height=size;draw(cv.getContext('2d'),size);const t=new THREE.CanvasTexture(cv);t.colorSpace=THREE.SRGBColorSpace;return t;}
  function sprite(tex,size=.016) {const s=new THREE.Sprite(new THREE.SpriteMaterial({map:tex,sizeAttenuation:false,transparent:true,depthTest:true,depthWrite:false}));s.scale.set(size,size,1);return s;}
  const dotTex=texture((g,s)=>{g.fillStyle='#c9ccd1';g.strokeStyle='#080a0e';g.lineWidth=7;g.beginPath();g.arc(s/2,s/2,s/2-9,0,2*Math.PI);g.fill();g.stroke();});
  const squareTex=texture((g,s)=>{g.fillStyle=C.ink;g.strokeStyle='#080a0e';g.lineWidth=6;g.fillRect(s*.28,s*.28,s*.44,s*.44);g.strokeRect(s*.28,s*.28,s*.44,s*.44);});
  const starTex=texture((g,s)=>{g.beginPath();for(let i=0;i<10;i++){const a=-Math.PI/2+i*Math.PI/5,r=s*(i%2?.18:.42);g.lineTo(s/2+r*Math.cos(a),s/2+r*Math.sin(a));}g.closePath();g.fillStyle=C.ink;g.strokeStyle='#080a0e';g.lineWidth=4;g.fill();g.stroke();});
  // Fill a lon/lat polygon on the sphere; long edges are bisected so large zones follow the curvature.
  function fillMesh(ring,color,opacity,r=1.0012){
    const pts=[];for(const [lon,lat]of ring){const prev=pts.at(-1)?.x??lon;pts.push(new THREE.Vector2(prev+((lon-prev+540)%360)-180,lat));}
    const out=[],split=(a,b,c)=>{const [p,q,o]=[[a,b,c],[b,c,a],[c,a,b]].reduce((x,y)=>y[0].distanceTo(y[1])>x[0].distanceTo(x[1])?y:x);
      if(p.distanceTo(q)<=.5){for(const v of [a,b,c])out.push(...A.llToVec(v.x,v.y,r));return;}
      const m=p.clone().lerp(q,.5);split(p,m,o);split(m,q,o);};
    for(const [i,j,k]of THREE.ShapeUtils.triangulateShape(pts,[]))split(pts[i],pts[j],pts[k]);
    const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(out,3));
    return new THREE.Mesh(g,new THREE.MeshBasicMaterial({color,transparent:true,opacity,depthWrite:false,side:THREE.DoubleSide}));
  }
  function circle(colat,r=1.002,n=360) {const out=[],a=colat*A.D2R;for(let i=0;i<=n;i++){const p=i/n*2*Math.PI;out.push(r*Math.sin(a)*Math.cos(p),r*Math.cos(a),r*Math.sin(a)*Math.sin(p));}return out;}
  const drawPoint=(s)=>s.u.map((v)=>v*(1+s.alt/A.RE));
  function visible(p) {
    const d=p.clone().sub(camera.position),t=clamp(-camera.position.dot(d)/d.lengthSq(),0,1);
    return camera.position.clone().addScaledVector(d,t).lengthSq()>=.9999 && p.clone().project(camera).z<1;
  }

  // Maps decode off the main thread, so a large one arriving does not freeze the page. Safari keeps the plain loader: this path is untested there.
  const isSafari=/^((?!chrome|android).)*safari/i.test(navigator.userAgent);
  const bitmapLoader=typeof createImageBitmap==='function'&&!isSafari?new THREE.ImageBitmapLoader().setOptions({imageOrientation:'flipY',premultiplyAlpha:'none',colorSpaceConversion:'none'}):null,plainLoader=new THREE.TextureLoader();
  const loadTex=(url)=>new Promise((resolve,reject)=>{
    const ready=(t)=>{t.colorSpace=THREE.NoColorSpace;t.anisotropy=renderer.capabilities.getMaxAnisotropy();resolve(t);},fail=()=>reject(new Error(`Texture missing: ${url}`));
    if(bitmapLoader)bitmapLoader.load(url,(image)=>{const t=new THREE.Texture(image);t.flipY=false;t.needsUpdate=true;ready(t);},undefined,fail);
    else plainLoader.load(url,ready,undefined,fail);
  });
  $('loadmsg').textContent='Loading Blue Marble…';
  // The light 4K pair opens the page. sharpenBase fetches the 8K maps afterwards, where the GPU and screen can hold them.
  const big=renderer.capabilities.maxTextureSize>=8192&&!lightDevice;
  const lightTex=(webp,jpg)=>loadTex(webp).catch(()=>loadTex(jpg));
  const [dayTex,nightTex,boundaryRaw,moonTex,starCatalog]=await Promise.all([lightTex('./tex/earth_day_4k.webp','./tex/earth_day_4k.jpg'),lightTex('./tex/earth_night_4k.webp','./tex/earth_night.jpg'),fetchJSON('./data/boundaries.json'),loadTex('./tex/moon_1024.jpg'),fetchJSON('./data/hipparcos.json')]);
  const boundaryData=validateBoundaries(boundaryRaw);
  const earthMat=new THREE.ShaderMaterial({uniforms:{dayTex:{value:dayTex},nightTex:{value:nightTex},sunDir:{value:new THREE.Vector3(1,0,0)},lights:{value:1},tileRect:{value:new THREE.Vector4(0,0,1,1)},imageRect:{value:new THREE.Vector4(0,0,1,1)}},
    vertexShader:`varying vec2 vUv;varying vec3 vP;void main(){vUv=uv;vP=position;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
    // Day side: Blue Marble, dimming toward the terminator.  Night side: Black Marble, whose lights and moonlit terrain are natural colours;
    // the lights layer removes only the bright city pixels.  The limb picks up a thin haze and the twilight band a warm tint.
    fragmentShader:`uniform sampler2D dayTex,nightTex;uniform vec3 sunDir;uniform float lights;uniform vec4 tileRect,imageRect;varying vec2 vUv;varying vec3 vP;
      void main(){vec2 globalUV=tileRect.xy+vUv*tileRect.zw;vec2 imageUV=imageRect.xy+vUv*imageRect.zw;
        vec3 n=normalize(vP),view=normalize(cameraPosition-vP);float mu=dot(n,sunDir),ndv=max(dot(n,view),0.0);
        vec3 day=texture2D(dayTex,imageUV).rgb*(0.66+0.42*sqrt(clamp(mu,0.0,1.0)));
        vec3 nl=texture2D(nightTex,globalUV).rgb;float L=max(nl.r,max(nl.g,nl.b)),city=smoothstep(0.10,0.42,L);
        vec3 night=nl*(1.0-city)*0.6+nl*city*mix(0.3,1.75,lights);
        vec3 col=mix(night,day,smoothstep(-0.055,0.085,mu));
        float rim=pow(1.0-ndv,3.0);
        col+=vec3(0.26,0.50,1.0)*rim*smoothstep(-0.12,0.30,mu)*0.42;
        col+=vec3(0.75,0.30,0.10)*exp(-pow((mu+0.015)/0.06,2.0))*0.16*(0.35+0.65*rim);
        gl_FragColor=vec4(col,1.0);}`});
  scene.add(new THREE.Mesh(new THREE.SphereGeometry(1,256,128),earthMat));
  // Atmosphere: a back-face shell shaded by the ray's closest approach to the Earth, blue where the air is sunlit and red along the terminator.
  const ATMO_R=1.055,atmosphere=new THREE.Mesh(new THREE.SphereGeometry(ATMO_R,128,64),new THREE.ShaderMaterial({uniforms:{sunDir:earthMat.uniforms.sunDir},side:THREE.BackSide,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,
    vertexShader:`varying vec3 vP;void main(){vP=position;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
    fragmentShader:`uniform vec3 sunDir;varying vec3 vP;
      void main(){vec3 rd=normalize(vP-cameraPosition),cp=cameraPosition-dot(cameraPosition,rd)*rd;float h=length(cp);
        float x=clamp((h-1.0)/${(ATMO_R-1).toFixed(3)},0.0,1.0),density=exp(-x*4.0)*(1.0-smoothstep(0.72,1.0,x));
        float mu=dot(cp/h,sunDir),lit=smoothstep(-0.24,0.10,mu);
        vec3 col=mix(vec3(1.0,0.40,0.14),vec3(0.32,0.58,1.0),smoothstep(-0.03,0.26,mu));
        gl_FragColor=vec4(col*density*lit*0.92,1.0);}`}));
  atmosphere.renderOrder=-1;scene.add(atmosphere);
  const mapTiles=createMapTiles({scene,camera,renderer,earthMaterial:earthMat,loadTexture:loadTex,baseWidth:4096});
  // Tiles sharpen only the day map, so the dark side gets the 8K night map once a view outgrows 4K. The 8K day map is
  // needed only when too many lit tiles are in view to use them. A failed fetch keeps the light map.
  let sharpenNight=big,sharpenDay=big,gpuJudged=false;
  const swapBase=(name,url)=>loadTex(url).then((texture)=>{const old=earthMat.uniforms[name].value;earthMat.uniforms[name].value=texture;old.dispose();old.image?.close?.();});
  function sharpenBase(){
    if(!gpuJudged||(!sharpenNight&&!sharpenDay))return;
    const {level,requiredPixels}=mapTiles.stats();
    if(requiredPixels<=4096*1.12)return;
    if(sharpenNight){sharpenNight=false;swapBase('nightTex','./tex/earth_night_8k.webp').catch(()=>{});}
    if(sharpenDay&&level<0){sharpenDay=false;swapBase('dayTex','./tex/earth_day_8k.webp').then(()=>mapTiles.setBaseWidth(8192)).catch(()=>{});}
  }
  const skyBg=new StellarBackground(starCatalog),moon=createMoon(moonTex,earthMat.uniforms.sunDir);scene.add(moon);
  const boundaryLayer=createBoundaryLayer({scene,camera,initialData:boundaryData});
  const termGroup=group();termGroup.add(line(circle(90),{color:C.sun,width:1.8}),line(circle(102),{color:C.accent,width:1.5}));
  // Screen-space graticule: 10° meridians and parallels stay one pixel wide at every zoom.
  const gridGroup=group(),gridLines=[];for(let lon=-180;lon<180;lon+=10)gridLines.push([[lon,-90],[lon,90]]);for(let lat=-80;lat<=80;lat+=10)gridLines.push([-180,-90,0,90,180].map((lon)=>[lon,lat]));
  const gridMat=new LineMaterial({color:'#ffffff',linewidth:1,transparent:true,opacity:.16,depthWrite:false});materials.add(gridMat);gridGroup.add(new LineSegments2(new LineSegmentsGeometry().setPositions(boundarySegments(gridLines,1,1.0003)),gridMat));
  const fallGroup=group(),zoneGroup=group(),zoneLabels=group(),trajGroup=group(),gtGroup=group(),eventGroup=group(),jellyGroup=group(),cityGroup=group();
  const PAD=A.llToVec(...M.pad),pad=sprite(squareTex,.021);pad.position.set(...PAD.map((v)=>v*1.002));scene.add(pad);
  for(const z of data.zones){const pts=[];for(let i=0;i<z.ring.length-1;i++){const a=z.ring[i],b=z.ring[i+1],dl=((b[0]-a[0]+540)%360)-180,n=Math.max(1,Math.ceil(Math.max(Math.abs(dl),Math.abs(b[1]-a[1]))/.1));for(let j=0;j<n;j++)pts.push(...A.llToVec(a[0]+dl*j/n,a[1]+(b[1]-a[1])*j/n,1.0015));}pts.push(...A.llToVec(...z.ring.at(-1),1.0015));zoneGroup.add(fillMesh(z.ring,C.ink,.18),line(pts,{color:z.color,width:1.5}));
    const o=label(`${z.role==='boosters'?'Booster':z.role} drop zone\n${z.id} · ${z.t0}–${z.t1} UTC`,'zone below');o.position.set(...A.llToVec(...z.centroid,1.002));zoneLabels.add(o);}
  for(const [name,lon,lat,tier] of ALL_CITIES){const p=A.llToVec(lon,lat,1.001),dot=sprite(dotTex,.007);dot.position.set(...p);dot.userData={tier,city:name};cityGroup.add(dot);const o=label(name,'city');o.position.set(...p);o.userData={tier,city:name};o.element.title=`Sky chart over ${name}`;o.element.tabIndex=0;o.element.setAttribute('role','button');o.element.addEventListener('click',(e)=>openSky({name,lon,lat},false,{x:e.clientX,y:e.clientY}));o.element.addEventListener('keydown',(e)=>{if(e.key==='Enter')openSky({name,lon,lat});});cityGroup.add(o);}
  const pickup=sprite(starTex,.025),pickupLabel=label('','below');scene.add(pickup,pickupLabel);
  // Compact location pin: a solid teardrop whose tip sits on the clicked ground point.
  const siteTex=texture((g,s)=>{const r=s*.27,cx=s/2,cy=r+s*.05,tip=s*.97;g.beginPath();g.arc(cx,cy,r,Math.PI*.85,Math.PI*.15);g.quadraticCurveTo(cx+r*.62,cy+r*1.25,cx,tip);g.quadraticCurveTo(cx-r*.62,cy+r*1.25,cx-r*Math.cos(Math.PI*.15),cy+r*Math.sin(Math.PI*.15));g.closePath();g.fillStyle=C.accent;g.strokeStyle='#061018';g.lineWidth=s*.055;g.lineJoin='round';g.stroke();g.fill();g.fillStyle='#061018';g.beginPath();g.arc(cx,cy,r*.34,0,2*Math.PI);g.fill();},96);
  const siteMark=sprite(siteTex,.026);siteMark.center.set(.5,.02);siteMark.renderOrder=9;siteMark.material.depthTest=false;siteMark.visible=false;scene.add(siteMark);
  // Solid motors draw the bold sunlit arc; the small S4 plume stays thin, because it is far fainter.
  function buildJellyLayer(){clear(jellyGroup);let run=[],kind=null;
    const flush=()=>{if(run.length>=6){if(kind==='solid')jellyGroup.add(line(run,{color:C.sun,width:8,opacity:.16}),line(run,{color:C.sun,width:2.6}));else jellyGroup.add(line(run,{color:C.s4,width:1.9}));}run=[];};
    for(let i=0;i<ASC.n;i++){const met=ASC.metAt(i),on=J.lit[i]&&poweredAt(met),k=met<=solidEnd?'solid':'s4';if(on){if(k!==kind){flush();kind=k;}run.push(...ASC.pt(i,1));}else flush();}flush();
    if(J.pickup){pickup.position.set(...drawPoint(J.pickup));pickupLabel.position.copy(pickup.position);pickupLabel.element.textContent=`Sunlight pickup\n${A.fmtMET(J.pickup.met)} · ${J.pickup.alt.toFixed(1)} km`;}
  }
  // 10-degree jelly zones for this T0.  The shell's night clip is per pixel from the live Sun vector, so it ends exactly on the Sun 0 line.
  const visLayer=createZoneLayer(earthMat.uniforms.sunDir,{s4:'0.478, 0.851, 0.478'},hasJelly?M.visibility.extent:null);let zoneAt=null;
  visLayer.renderOrder=-1;scene.add(visLayer);
  let zones=null,viewers=[],zoneTimer=null,zoneVersion=0,zoneShown=0,zoneWorker=null;
  // The grid is 80,000 cells by a few hundred samples, 60-70 ms on an M1 Max, so a worker computes it and the result is applied when it arrives. Without a worker it runs inline.
  if(hasJelly&&typeof Worker==='function')try{zoneWorker=new Worker(new URL('./zone-worker.js',import.meta.url),{type:'module'});zoneWorker.postMessage({mission:data});zoneWorker.onmessage=({data:m})=>{if(m.version===zoneVersion)applyZones(m.zones);};zoneWorker.onerror=()=>{zoneWorker.terminate();zoneWorker=null;buildZones();};}catch{zoneWorker=null;}
  function applyZones(Z){zones=Z;visLayer.setZones(Z);zoneShown++;dirty();}
  function buildZones(){if(!hasJelly)return;const T0=t0ms(),pickupMet=J.pickup?.met??0;viewers=viewerTable(M.jelly.cities,ASC,solidEnd,J,sunAt,T0,poweredAt);dirty();zoneVersion++;
    if(zoneWorker)zoneWorker.postMessage({version:zoneVersion,T0,pickupMet});else applyZones((zoneAt??=createJellyZones(M,ASC,poweredAt,sunAt))(T0,pickupMet));}
  function buildTrajectory(){clear(trajGroup);clear(gtGroup);clear(eventGroup);clear(fallGroup);
    const p=label(M.pad_name);p.position.copy(pad.position);eventGroup.add(p);
    for(const [key,tr] of Object.entries(T)){const seg=data.tracks[key],on=M.flight_segments.includes(key);(on?trajGroup:fallGroup).add(line(tr.pts(1),{color:seg.color,width:on?1.8:1.2,dashed:!!seg.dashed}));if(on)gtGroup.add(line(tr.pts(1,0,tr.n-1,true),{color:C.ink,width:1,opacity:.26}));}
    for(const e of data.events){if(!e.major || e.met===0)continue;const tr=e.track?T[e.track]:null,s=tr?tr.sample(e.met):shipAt(e.met);const p=drawPoint(s),dot=sprite(squareTex,.016);dot.position.set(...p);eventGroup.add(dot);const o=label(`${e.label}\n${A.fmtMET(e.met)}`,'small');o.position.set(...p);eventGroup.add(o);}
    buildJellyLayer();
  }
  function onT0Change(){J=computeJelly(ASC,sunAt,t0ms());buildJellyLayer();clearTimeout(zoneTimer);zoneTimer=setTimeout(buildZones,120);dirty();}

  // One cartoon per flight state: the stack shortens as stages separate, and burning states carry a flame.
  const vehicleTex=new Map(),vehicleTexture=(state,burning)=>{const key=`${state}/${burning}`;if(!vehicleTex.has(key))vehicleTex.set(key,texture((g,s)=>drawVehicle(g,s,stack,state,burning),256));return vehicleTex.get(key);};
  const ship=sprite(vehicleTexture(0,false),.062),shipLabel=label(M.vehicle,'vehicle');ship.renderOrder=8;scene.add(ship,shipLabel);let shipKey='0/false';
  const glowTex=texture((g,s)=>{const r=s/2,gr=g.createRadialGradient(r,r,0,r,r,r);gr.addColorStop(0,'rgba(255,244,211,.55)');gr.addColorStop(.22,'rgba(255,230,150,.36)');gr.addColorStop(.7,'rgba(120,190,255,.1)');gr.addColorStop(1,'rgba(120,190,255,0)');g.fillStyle=gr;g.fillRect(0,0,s,s);},128);
  const glow=sprite(glowTex,.10);glow.material.blending=THREE.AdditiveBlending;glow.material.depthWrite=false;glow.renderOrder=7;scene.add(glow);
  let fp=null,fpLam=-1;
  function updateFootprint(s){if(!state.show.fp){if(fp)fp.visible=false;return;}const lam=A.footprintDeg(s.alt,A.MIN_ELEVATION_DEG);if(!fp||Math.abs(lam-fpLam)>.03){if(fp){scene.remove(fp);fp.geometry.dispose();materials.delete(fp.material);fp.material.dispose();}fp=line(circle(lam),{color:C.footprint,dashed:true,width:1.5});scene.add(fp);fpLam=lam;}fp.quaternion.setFromUnitVectors(Y,new THREE.Vector3(...s.u));fp.visible=s.alt>1;}
  let skySite=null;
  const sky=createSkyChart({shipAt,metEnd:()=>MET_END,styleAt,seco,cutoffLabel:M.cutoff_label??'Cutoff',vehicle:M.vehicle,fmtMET:A.fmtMET,sunSubpoint,
    sunPosition:sunAt,getState:()=>({met:state.met,t0ms:t0ms()}),onJump:(met)=>{setPlaying(false);setMet(met);},onSite:(site)=>{skySite=site;siteMark.position.set(...A.llToVec(site.lon,site.lat,1.001));}});
  function openSky(site,focus=false,near=null){sky.open(site,focus,near).catch((e)=>message(`Sky chart: ${e.message}`));}
  const [home,homeLon,homeLat]=ALL_CITIES.find((c)=>c[0]===M.observer_home)??[M.pad_name,...M.pad];
  $('skybtn').onclick=()=>openSky(skySite||{name:home,lon:homeLon,lat:homeLat},true);

  function setFollow(on){state.follow=on;$('o-follow').checked=on;}
  const cameraScale=()=>Math.max(1,1.4/camera.aspect);
  function flyTo(lon,lat,dist){setFollow(false);cam.flyTo({lon,lat,range:(dist-1)*cameraScale()});}
  function setMet(v){if(!Number.isFinite(v))return;state.met=clamp(v,metMin,MET_END);state.live=false;$('live').classList.remove('on');dirty();}
  function setPlaying(on){if(on){state.live=false;$('live').classList.remove('on');if(state.met>=MET_END)state.met=0;}state.playing=on;$('play').textContent=on?'❚❚ Pause':'▶ Play';}
  function setT0(v){if(!Number.isFinite(v))return;state.t0=clamp(v,t0Min,t0Max);$('t0').value=state.t0;onT0Change();}
  function option(select,value,text){const o=document.createElement('option');o.value=value;o.textContent=text;select.appendChild(o);}
  for(const p of index.profiles)option($('profilesel'),p.id,p.label);$('profilesel').value=profile.id;
  for(const m of profile.missions)option($('launchsel'),m.id,m.label);$('launchsel').value=entry.id;
  function selectMission(p,m){const q=new URLSearchParams(location.search);q.set('profile',p);q.set('mission',m);for(const k of ['t0','met','cam','sky','follow'])q.delete(k);location.search=q;}
  $('profilesel').onchange=()=>{const p=index.profiles.find((p)=>p.id===$('profilesel').value);selectMission(p.id,p.default_mission);};
  $('launchsel').onchange=()=>selectMission(profile.id,$('launchsel').value);
  Object.assign($('t0'),{min:t0Min,max:t0Max,value:state.t0});Object.assign($('met'),{min:metMin,max:MET_END,value:state.met});
  $('t0presets').innerHTML=M.t0_presets.map((p)=>`<button class="btn" data-t0="${esc(p.time)}">${esc(p.label)}</button>`).join('');
  $('views').innerHTML=M.views.map((v,i)=>`<button class="btn" data-view="${i}">${esc(v[0])}</button>`).join('');
  $('t0').oninput=()=>setT0(+$('t0').value);$('t0presets').onclick=(e)=>{if(e.target.dataset.t0)setT0(clockSeconds(e.target.dataset.t0));};
  $('met').oninput=()=>{setPlaying(false);setMet(+$('met').value);};$('play').onclick=()=>setPlaying(!state.playing);
  $('speed').value=String(state.speed);$('speed').onchange=()=>{state.speed=+$('speed').value;};
  $('back').onclick=()=>setMet(state.met-30);$('fwd').onclick=()=>setMet(state.met+30);
  $('live').onclick=()=>{if(state.live){state.live=false;$('live').classList.remove('on');return;}const met=(Date.now()-t0ms())/1000;if(met<metMin||met>MET_END){message('The wall clock is outside this modeled flight. Use playback to explore the scenario.');return;}message('');setPlaying(false);state.live=true;$('live').classList.add('on');};
  $('views').onclick=(e)=>{const v=M.views[+e.target.dataset.view];if(v)flyTo(v[1],v[2],v[3]);};
  for(const k of Object.keys(state.show)){$('o-'+k).checked=state.show[k];$('o-'+k).onchange=()=>{state.show[k]=$('o-'+k).checked;dirty();};}
  $('o-follow').checked=state.follow;$('o-follow').onchange=()=>setFollow($('o-follow').checked);
  async function copyText(text,button){const old=button.textContent;let copied=false;try{await navigator.clipboard.writeText(text);copied=true;}catch{const box=document.createElement('textarea');box.value=text;document.body.appendChild(box);box.select();copied=document.execCommand('copy');box.remove();}button.textContent=copied?'Copied':'Copy unavailable';if(!copied)message('Clipboard unavailable. Select the TLE text or copy the browser address.');setTimeout(()=>{button.textContent=old;},1600);}
  function shareURL(){const v=cam.get(),q=new URLSearchParams({profile:profile.id,mission:entry.id,t0:A.fmtHMS(t0ms()),met:state.met.toFixed(3),cam:`${v.lon.toFixed(3)},${v.lat.toFixed(3)},${(1+v.range).toFixed(3)},${v.heading.toFixed(1)},${v.tilt.toFixed(1)}`,follow:state.follow?'1':'0',speed:state.speed});for(const [k,v]of Object.entries(state.show))q.set(k,v?'1':'0');if(sky.isOpen()&&skySite)q.set('sky',`${skySite.lat.toFixed(4)},${skySite.lon.toFixed(4)}`);return `${location.origin}${location.pathname}?${q}`;}
  $('link').onclick=()=>{const url=shareURL();history.replaceState(null,'',url);copyText(url,$('link'));};$('copytle').onclick=()=>copyText($('tle').textContent,$('copytle'));
  $('events').onclick=(e)=>{const row=e.target.closest('[data-met]');if(row){setPlaying(false);setMet(+row.dataset.met);}};
  $('legend').innerHTML=`<div>${M.flight_segments.map((k)=>`<span><i style="border-color:${data.tracks[k].color}"></i>${esc(data.tracks[k].label)}</span>`).join('')}${hasSolid?`<span><i style="border-color:${C.sun};border-top-width:3px"></i>Lit solid</span><span><i style="border-color:${C.s4}"></i>Lit S4</span>`:`<span><i style="border-color:${C.sun};border-top-width:3px"></i>Lit plume</span>`}</div><div><span><i class="d" style="border-color:${C.footprint}"></i>${A.MIN_ELEVATION_DEG}° circle</span>${hasJelly?`<span><i style="border-color:#fff"></i>${A.MIN_ELEVATION_DEG}° zone</span>`:''}<span><i style="border-color:${C.sun}"></i>Sun 0°</span><span><i style="border-color:${C.accent}"></i>Sun −12°</span></div>`;
  const about=M.about??['Pre-launch model fitted to the NOTAM zones and public vehicle figures; not telemetry.','WGS84 geometry · JPL DE440s sunlight.'];
  $('about').innerHTML=`${about.map((s)=>`<p>${esc(s)}</p>`).join('')}<details><summary>Model notes</summary>${M.notes.map((n)=>`<p>${esc(n)}</p>`).join('')}</details><p>Full assumptions: ${M.readme_url?`<a href="${esc(M.readme_url)}" target="_blank" rel="noopener noreferrer">README ↗</a>`:'README.md in this project'}.</p>`;
  const narrow=matchMedia('(max-width:860px)');let panels={ctl:!narrow.matches,info:!narrow.matches};
  try{const saved=JSON.parse(localStorage.getItem('globe-panels'));if(saved&&!narrow.matches)panels={ctl:!!saved.ctl,info:!!saved.info};}catch{}
  function applyPanels(){document.body.classList.toggle('ctl-open',panels.ctl);document.body.classList.toggle('info-open',panels.info);document.querySelectorAll('[data-panel]').forEach((b)=>{b.classList.toggle('on',panels[b.dataset.panel]);b.setAttribute('aria-expanded',String(panels[b.dataset.panel]));});}
  document.querySelectorAll('[data-panel]').forEach((b)=>b.onclick=()=>{const k=b.dataset.panel,on=!panels[k];if(narrow.matches)panels={ctl:false,info:false};panels[k]=on;applyPanels();try{localStorage.setItem('globe-panels',JSON.stringify(panels));}catch{}});
  narrow.onchange=()=>{panels={ctl:!narrow.matches,info:!narrow.matches};applyPanels();};applyPanels();
  addEventListener('keydown',(e)=>{if(document.activeElement?.matches('input,select,textarea,button,[role="button"]'))return;if(e.code==='Space'){e.preventDefault();setPlaying(!state.playing);}if(e.key==='ArrowRight')setMet(state.met+(e.shiftKey?300:10));if(e.key==='ArrowLeft')setMet(state.met-(e.shiftKey?300:10));});

  const timeline=()=>[...data.events,...(J.pickup&&!J.pickup.fromLiftoff?[{met:J.pickup.met,label:'Sunlight pickup'}]:[])].sort((a,b)=>a.met-b.met);
  function buildTables(){const T0=t0ms();$('t0v').textContent=A.fmtHMS(T0)+'Z';
    $('hazard').querySelector('tbody').innerHTML=data.zones.map((z)=>`<tr><td>${esc(z.id)}<br>${esc(z.role)}</td><td>${z.t0.slice(0,2)}:${z.t0.slice(2)}–${z.t1.slice(0,2)}:${z.t1.slice(2)}Z</td><td>${z.impact?A.fmtHMS(T0+z.impact.met*1000)+'Z':esc(z.impact_note||'Not modeled')}</td></tr>`).join('');
    $('events').querySelector('tbody').innerHTML=timeline().map((e)=>`<tr><td><button class="time-jump" data-met="${e.met}">${A.fmtMET(e.met)}</button></td><td>${A.fmtHMS(T0+e.met*1000)}</td><td>${esc(e.label)}</td></tr>`).join('');
    buildJellyTables(T0);
    const R=data.tle_ref,sets=R?.sets||[];$('tle').textContent=sets.length?sets.map((s)=>{const t=A.tleForT0(s,R.t0,R.raan_rate_deg_per_min,T0);return `${t.name}\n${t.l1}\n${t.l2}`;}).join('\n\n'):'No TLE supplied for this profile.';$('copytle').disabled=!sets.length;
    document.querySelectorAll('[data-t0]').forEach((b)=>b.classList.toggle('on',clockSeconds(b.dataset.t0)===state.t0));tablesDirty=false;
  }
  // The jelly numbers follow T0: the Earth-fixed path is fixed and only the Sun moves.
  function buildJellyTables(T0){if(!hasJelly)return;const cfg=M.jelly,fr=A.siteFrame(...M.pad),met=(m)=>A.fmtMET(m).replace(/^T\+00:/,'T+');
    let refr=null,clear=null;const high=[];
    for(let i=0;i<ASC.n;i++){const alt=ASC.alt[i],t=ASC.metAt(i),dep=J.dep[i];if(!refr&&alt>=A.shadowAltKm(dep))refr={t,alt};const ray=dep>0?(A.R_JELLY+alt)*Math.cos(dep*A.D2R)-A.R_JELLY:alt;if(!clear&&J.lit[i]&&ray>=cfg.clear_ray_km)clear={t,alt};if(J.lit[i]&&poweredAt(t)&&t<=solidEnd&&alt>=cfg.high_km)high.push(t);}
    const lit=(a,b)=>{let n=0;for(let i=0;i<ASC.n;i++){const t=ASC.metAt(i);if(t>=a&&t<b&&J.lit[i])n+=ASC.dt;}return n;};
    const fmtPt=(p)=>p?`${met(p.t??p.met)} · ${(p.alt).toFixed(0)} km`:'—',P=J.pickup,area=(x)=>`${(x/1e6).toFixed(2)} M km²`;
    const rows=[['Sun at pad',`${A.lookAngles(fr,sunAt(T0)).el.toFixed(2)}° at T0`],['Sunlight pickup',P?fmtPt(P):'None'],["With 34′ refraction",fmtPt(refr)],['Clear sunlight',fmtPt(clear)],
      [`Solid plume ≥${cfg.high_km} km`,high.length?`${met(high[0])} – ${met(high.at(-1))}`:'—'],...cfg.stages.map((q)=>[`${q.label} lit`,`${lit(q.a,q.b).toFixed(0)} of ${(q.b-q.a).toFixed(0)} s`])];
    if(zones)rows.push([`10° zone, ${cfg.solid_label??'solid burns'}`,area(zones.areaSolid)],['…with Sun ≤'+cfg.prime_sun_deg+'°',area(zones.areaPrime)]);
    $('jelly').querySelector('tbody').innerHTML=rows.map(([k,v])=>`<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('');
    $('viewers').querySelector('tbody').innerHTML=viewers.filter((v)=>v.el>=5).slice(0,14).map((v)=>`<tr class="${v.sun<=cfg.prime_sun_deg?'dark':v.sun>0?'day':''}"><td><button class="time-jump" data-site="${esc(v.name)}" data-lon="${v.lon}" data-lat="${v.lat}">${esc(v.name)}</button></td><td>${v.el.toFixed(0)}°</td><td>${met(v.met)}</td><td>${v.sun.toFixed(1)}°</td></tr>`).join('');
  }
  $('viewers').onclick=(e)=>{const b=e.target.closest('[data-site]');if(b)openSky({name:b.dataset.site,lon:+b.dataset.lon,lat:+b.dataset.lat},false,{x:e.clientX,y:e.clientY});};
  function updateUI(s){const utc=t0ms()+state.met*1000,st=styleAt(state.met,t0ms()),ll=A.vecToLL(...s.u),fr=A.siteFrame(ll.lon,ll.lat),sunAlt=A.lookAngles(fr,sunAt(utc)).el;
    $('c-date').textContent=A.fmtDate(utc);$('c-utc').textContent=A.fmtHMS(utc);$('c-met').textContent=A.fmtMET(state.met);$('c-cst').textContent=A.fmtHMS(utc,localZone.offset_h);$('metv').textContent=A.fmtMET(state.met);if(document.activeElement!==$('met'))$('met').value=state.met;
    if(tablesDirty)buildTables();
    const a=shipAt(state.met-1),b=shipAt(state.met+1),v=b.p.map((x,i)=>(x-a.p[i])/2),w=7.2921158553e-5;
    const speed=state.met>1&&state.met<MET_END-1?Math.hypot(v[0]+w*s.p[2],v[1],v[2]-w*s.p[0]).toFixed(2)+' km/s':'—';
    const rows=[['Phase',phaseOf(state.met)],['Altitude',s.alt.toFixed(1)+' km WGS84'],['Inertial speed',speed],['Sub-point',`${ll.lat.toFixed(2)}°, ${ll.lon.toFixed(2)}°`],['Illumination',st.lit?(st.powered?'Sunlit powered arc':'Sunlit'):'Earth shadow'],['Ground below',`${A.lightingClass(sunAlt)} · ${sunAlt.toFixed(1)}°`],['Orbit progress',state.met>=M.insertion_met?`${((state.met-M.insertion_met)/M.period_s).toFixed(2)} / ${M.orbit_revolutions} rev`:'Before insertion']];
    $('status').querySelector('tbody').innerHTML=rows.map(([k,v])=>`<tr><td>${k}</td><td>${esc(v)}</td></tr>`).join('');
    const next=timeline().find((e)=>e.met>state.met);document.querySelectorAll('#events [data-met]').forEach((b)=>{b.closest('tr').classList.toggle('past',+b.dataset.met<=state.met);b.closest('tr').classList.toggle('next',next?.met===+b.dataset.met);});
  }
  function trackAt(x,y){const r=view.getBoundingClientRect();let nearest=null,best=13;
    for(const tr of flight)for(let i=0;i<tr.n;i+=3){const p=new THREE.Vector3(...tr.pt(i,1));if(!visible(p))continue;const q=p.project(camera),d=Math.hypot((q.x+1)*r.width/2+r.left-x,(1-q.y)*r.height/2+r.top-y);if(d<best){best=d;nearest={met:tr.metAt(i),alt:tr.alt[i]};}}
    return nearest;}
  // A clean click or tap seeks on the trajectory, or opens the sky chart for the ground under the pointer.
  function pick(x,y){const track=trackAt(x,y);if(track){setPlaying(false);setMet(track.met);return;}const ll=cam.groundAt(x,y);if(ll)openSky({lat:+ll.lat.toFixed(4),lon:+ll.lon.toFixed(4),custom:true},false,{x,y});}
  renderer.domElement.addEventListener('pointerleave',()=>{$('inspect').hidden=true;});
  renderer.domElement.addEventListener('pointermove',(e)=>{if(e.buttons||e.pointerType==='touch')return;const nearest=trackAt(e.clientX,e.clientY);
    $('inspect').hidden=!nearest;renderer.domElement.style.cursor=nearest?'pointer':cam.groundAt(e.clientX,e.clientY)?'crosshair':'';if(nearest){$('inspect').textContent=`${A.fmtMET(nearest.met)} · ${nearest.alt.toFixed(1)} km\nClick to seek`;Object.assign($('inspect').style,{left:Math.max(16,Math.min(innerWidth-240,e.clientX+15))+'px',top:Math.min(innerHeight-80,e.clientY+15)+'px'});}});
  function declutterLabels(){
    const boxes=['ctl','info','legend'].map((id)=>$(id)).filter((el)=>el.getClientRects().length).map((el)=>el.getBoundingClientRect());
    const overlap=(a,b)=>a.left<b.right+4 && a.right+4>b.left && a.top<b.bottom+3 && a.bottom+3>b.top;
    const objects=[shipLabel,pickupLabel,...eventGroup.children,...zoneLabels.children,...cityGroup.children];
    for(const o of objects){if(!o.isCSS2DObject || o.element.style.display==='none')continue;const r=o.element.getBoundingClientRect();const show=r.left>=16 && r.right<=innerWidth-16 && r.top>=50 && r.bottom<=innerHeight-24 && !boxes.some((b)=>overlap(r,b));o.element.style.visibility=show?'visible':'hidden';if(show)boxes.push(r);}
  }
  // Sun and Moon markers, as in cislunar-eye: beside the body when it is in view, otherwise a chevron on the screen edge pointing at it.
  const sunMark=$('sun-mark'),moonMark=$('moon-mark'),_sk=new THREE.Vector3(),_q=new THREE.Quaternion();
  function placeSkyMarker(el,dir,on,dist,avoid=null){if(!on){el.hidden=true;return;}
    const rect=view.getBoundingClientRect(),boxes=['ctl','info'].map((id)=>$(id)).filter((b)=>b.getClientRects().length).map((b)=>b.getBoundingClientRect());
    const left=Math.max(14,...boxes.filter((b)=>b.left<rect.left+rect.width/2).map((b)=>b.right+12)),right=Math.min(rect.right-14,...boxes.filter((b)=>b.left>=rect.left+rect.width/2).map((b)=>b.left-12)),top=rect.top+14,bottom=rect.bottom-34;
    _sk.copy(dir).multiplyScalar(dist);const p=_sk.clone().project(camera),c=dir.clone().applyQuaternion(_q.copy(camera.quaternion).invert());
    const sx=(p.x+1)*rect.width/2+rect.left,sy=(1-p.y)*rect.height/2+rect.top,ahead=c.z<0&&sx>=left&&sx<=right&&sy>=top&&sy<=bottom;
    el.hidden=false;
    if(ahead){if(!visible(_sk)){el.hidden=true;return;}el.classList.remove('edge');el.firstChild.style.transform='';el.style.transform=`translate(${sx+9}px,${sy-8}px)`;return;}
    const a=Math.atan2(-c.y,c.x),cx=(left+right)/2,cy=(top+bottom)/2,dx=Math.cos(a),dy=Math.sin(a),k=Math.min(dx>1e-6?(right-cx)/dx:dx<-1e-6?(left-cx)/dx:1e9,dy>1e-6?(bottom-cy)/dy:dy<-1e-6?(top-cy)/dy:1e9);
    const x=cx+dx*k,y=cy+dy*k;let px=Math.min(x,right-58),py=Math.max(top,Math.min(y-8,bottom-16));
    if(avoid&&Math.abs(px-avoid.x)<62&&Math.abs(py-avoid.y)<17)py=py+(py+34<bottom?17:-17);
    el.classList.add('edge');el.firstChild.style.transform=`rotate(${a}rad)`;el.style.transform=`translate(${px}px,${py}px)`;el.dataset.x=px;el.dataset.y=py;}
  function updateSkyMarkers(sv,utc){const on=state.show.sky&&state.show.labels;placeSkyMarker(sunMark,new THREE.Vector3(...sv),on,150);
    if(moonAt){const q=moonAt(utc),r=Math.hypot(...q),sunEdge=sunMark.classList.contains('edge')&&!sunMark.hidden?{x:+sunMark.dataset.x,y:+sunMark.dataset.y}:null;placeSkyMarker(moonMark,new THREE.Vector3(q[0]/r,q[1]/r,q[2]/r),on,r/A.RE,sunEdge);}else moonMark.hidden=true;}
  // Redraw only when the picture can change. Whatever this list misses is caught by the input window or the once-a-second redraw.
  let drawnState=[],lastDraw=-Infinity,lastInput=-Infinity,draws=0;
  for(const type of ['pointerdown','pointerup','wheel','keydown','input','change','click'])addEventListener(type,()=>{lastInput=performance.now();},{capture:true,passive:true});
  function sceneChanged(now,tilesShown){
    const p=camera.position,q=camera.quaternion,u=earthMat.uniforms;
    let shown=0,bit=0;for(const on of Object.values(state.show))shown|=(on?1:0)<<bit++;
    const next=[p.x,p.y,p.z,q.x,q.y,q.z,q.w,view.clientWidth,view.clientHeight,renderer.getPixelRatio(),state.met,state.t0,tilesShown,u.dayTex.value.id,u.nightTex.value.id,boundaryLayer.stats().segments,shown,zoneShown];
    if(gpuJudged&&now-lastDraw<1000&&now-lastInput>=1000&&next.every((v,k)=>Math.abs(v-drawnState[k])<=1e-7))return false;
    drawnState=next;lastDraw=now;draws++;return true;
  }
  // Judge the GPU by real frame cost, timed to completion with a blocking readback: frame gaps look fine while commands queue up.
  // Three frames from the fourth draw on, then every 5 s. The 8K maps wait for the first verdict. Over 33 ms lowers the pixel ratio, in steps down to 1, and stops further 8K fetches.
  const gl=renderer.getContext(),syncPixel=new Uint8Array(4),syncGpu=()=>gl.readPixels(0,0,1,1,gl.RGBA,gl.UNSIGNED_BYTE,syncPixel);
  let frameCosts=[],nextProbe=0;
  function judgeGpu(cost){
    frameCosts.push(cost);if(frameCosts.length<3)return;
    const median=frameCosts.sort((a,b)=>a-b)[1];frameCosts=[];gpuJudged=true;nextProbe=performance.now()+5000;
    if(median<=33)return;
    sharpenNight=sharpenDay=false;
    const ratio=renderer.getPixelRatio();
    if(ratio>1){renderer.setPixelRatio(Math.max(1,ratio-.5));resize();nextProbe=0;}
  }
  let last=null,lastUI=0;
  function frame(now){const dt=Math.min(.1,(now-(last??now))/1000);last=now;
    if(state.live){const met=(Date.now()-t0ms())/1000;state.met=clamp(met,metMin,MET_END);if(met>=MET_END){state.live=false;$('live').classList.remove('on');message('Modeled flight complete.');}}
    else if(state.playing){state.met=Math.min(MET_END,state.met+dt*state.speed);if(state.met===MET_END)setPlaying(false);}
    const s=shipAt(state.met),nowUtc=t0ms()+state.met*1000,sv=sunVecAt(nowUtc);earthMat.uniforms.sunDir.value.set(...sv);
    if(state.follow&&!cam.fly)cam.approach(new THREE.Vector3(...s.u),1-Math.exp(-dt*2.5));
    cam.update(now,dt);
    const tilesShown=mapTiles.update(now,view.clientWidth,view.clientHeight);sharpenBase();
    boundaryLayer.update(now,view.clientWidth,view.clientHeight,renderer.getPixelRatio(),state.show.borders);
    if(!sceneChanged(now,tilesShown)){requestAnimationFrame(frame);return;}
    const sty=styleAt(state.met,t0ms());earthMat.uniforms.lights.value=state.show.lights?1:0;termGroup.quaternion.setFromUnitVectors(Y,new THREE.Vector3(...sv));termGroup.visible=state.show.term;
    ship.position.set(...drawPoint(s));shipLabel.position.copy(ship.position);{const v=vehicleStateAt(state.met,stack,poweredAt),key=`${v.state}/${v.burning}`;if(key!==shipKey){shipKey=key;ship.material.map=vehicleTexture(v.state,v.burning);ship.material.needsUpdate=true;}}ship.material.color.setScalar(sty.lit?1:.45);glow.position.copy(ship.position);glow.visible=state.show.jelly&&sty.lit&&sty.powered;if(glow.visible){const solid=state.met<=solidEnd,k=clamp((s.alt-20)/200,0,1);glow.scale.setScalar(solid?.045+.115*k:.035);}
    const ahead=shipAt(Math.min(MET_END,state.met+2)),p0=ship.position.clone().project(camera),p1=new THREE.Vector3(...drawPoint(ahead)).project(camera);if(state.met>0&&state.met<MET_END)ship.material.rotation=Math.atan2((p1.y-p0.y)*view.clientHeight,(p1.x-p0.x)*view.clientWidth)-Math.PI/2;
    updateFootprint(s);gtGroup.visible=state.show.gt;gridGroup.visible=state.show.grid;zoneGroup.visible=state.show.zones;zoneLabels.visible=state.show.zones;jellyGroup.visible=state.show.jelly;visLayer.visible=state.show.vis;fallGroup.visible=state.show.falls;cityGroup.visible=state.show.cities;
    for(const g of [zoneLabels,eventGroup])for(const o of g.children)if(o.isCSS2DObject)o.visible=state.show.labels&&visible(o.position);
    pickup.visible=!!J.pickup&&state.show.jelly;pickupLabel.visible=pickup.visible&&state.show.labels&&visible(pickup.position);shipLabel.visible=state.show.labels&&visible(ship.position);
    siteMark.visible=!!skySite&&sky.isOpen()&&visible(siteMark.position);
    const cityDistance=camera.position.length();
    for(const o of cityGroup.children)o.visible=visible(o.position)&&cityInRange(o.userData.tier,cityDistance)&&(!o.isCSS2DObject||state.show.labels);
    const gmst=A.gmstRad(nowUtc);moon.visible=state.show.sky&&!!moonAt;if(moon.visible)moon.update(moonAt(nowUtc),gmst,A.RE);
    const probing=draws>3&&performance.now()>=nextProbe;if(probing)syncGpu();const drawStart=performance.now();
    renderer.clear();if(state.show.sky){skyBg.render(renderer,camera,gmst,sv);renderer.clearDepth();}renderer.render(scene,camera);
    if(probing){syncGpu();judgeGpu(performance.now()-drawStart);}
    labels.render(scene,camera);updateSkyMarkers(sv,nowUtc);declutterLabels();if(sky.isOpen()&&now-lastUI>80)sky.render();if(now-lastUI>100){lastUI=now;updateUI(s);}requestAnimationFrame(frame);
  }
  function resize(){const w=view.clientWidth,h=view.clientHeight,oldScale=cameraScale();camera.aspect=w/h;cam.scaleRange(cameraScale()/oldScale);renderer.setSize(w,h);labels.setSize(w,h);camera.updateProjectionMatrix();for(const m of materials)m.resolution.set(w,h);}
  addEventListener('resize',resize);resize();
  const camq=(qs.get('cam')||'').split(',').map(Number),v=M.views[Math.min(2,M.views.length-1)],custom=(camq.length===3||camq.length===5)&&camq.every(Number.isFinite);
  const [lon,lat,dist]=custom?[camq[0],clamp(camq[1],-90,90),camq[2]]:v.slice(1);
  cam.set({lon,lat,range:custom?dist-1:(dist-1)*cameraScale(),heading:camq.length===5?camq[3]:0,tilt:camq.length===5?camq[4]:0});buildTrajectory();buildZones();
  requestAnimationFrame((t)=>{frame(t);$('loading').remove();});
  const want=qs.get('sky'),city=CITIES.find((c)=>c[0].toLowerCase()===want?.toLowerCase()),ll=(want||'').split(',').map(Number);
  if(city)openSky({name:city[0],lon:city[1],lat:city[2]});else if(ll.length===2&&ll.every(Number.isFinite)&&Math.abs(ll[0])<=90&&Math.abs(ll[1])<=180)openSky({lat:ll[0],lon:ll[1],custom:true});
  window.__globe={zones:()=>zones,viewers:()=>viewers,state,setMet,setT0,setPlaying,flyTo,camera,view:()=>cam.get(),setView:(view)=>cam.set(view),pick:(x,y)=>cam.groundAt(x,y),trackAt,observerMarker:siteMark,shareURL,sky,shipAt,jelly:()=>J,footprint:()=>fp,boundaryCoverage:boundaryData.coverage,earth:earthMat,mapLOD:mapTiles,boundaries:boundaryLayer,draws:()=>draws,meta:M,moon,skyBg,visLayer,renderer,groups:{trajGroup,gtGroup,jellyGroup,fallGroup,termGroup,cityGroup,gridGroup,zoneGroup},profile:profile.id,mission:entry.id};
}
