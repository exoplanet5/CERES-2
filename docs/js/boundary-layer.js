import * as THREE from 'three';
import {LineSegments2} from 'three/addons/lines/LineSegments2.js';
import {LineSegmentsGeometry} from 'three/addons/lines/LineSegmentsGeometry.js';
import {LineMaterial} from 'three/addons/lines/LineMaterial.js';
import {validateBoundaries,boundarySegments} from './boundaries.js';
import {boundaryLevel,projectedPixels} from './map-lod.js';

const FILES={coarse:'boundaries.json',medium:'boundaries-medium.json',fine:'boundaries-fine.json'};
const STYLES={regions:{width:.65,opacity:.30},countries:{width:1.15,opacity:.65},disputed:{width:1.15,opacity:.65,dashed:true}};

export function createBoundaryLayer({scene,camera,initialData}){
  const group=new THREE.Group();scene.add(group);
  const dataCache=new Map([['coarse',initialData]]),failed=new Map();
  let current=null,wanted='coarse',pending=null,shown=true,width=1,height=1;
  const stats={level:null,wanted:'coarse',loading:false,failures:0,segments:0,worldview:initialData.source.worldview};
  function replace(data,id){
    const next=new THREE.Group();let segments=0;
    try{
      for(const [key,style]of Object.entries(STYLES)){
        const positions=boundarySegments(data.layers[key]);segments+=positions.length/6;
        if(!positions.length)continue;
        const geometry=new LineSegmentsGeometry().setPositions(positions);
        for(const halo of [true,false]){
          const material=new LineMaterial({color:halo?'#05080c':'#e8eaed',linewidth:style.width+(halo?1.25:0),opacity:halo?.38:style.opacity,transparent:true,depthTest:true,depthWrite:false,dashed:!!style.dashed,dashSize:.006,gapSize:.004});
          material.resolution.set(width,height);
          const mesh=new LineSegments2(geometry,material);if(style.dashed)mesh.computeLineDistances();
          next.add(mesh);
        }
      }
    }catch(error){dispose(next);throw error;}
    if(current){group.remove(current);dispose(current);}
    current=next;group.add(next);stats.level=id;stats.segments=segments;
  }
  function dispose(g){const geometries=new Set();g.traverse((o)=>{if(o.geometry)geometries.add(o.geometry);o.material?.dispose();});for(const geometry of geometries)geometry.dispose();}
  async function load(){
    if(pending||!shown||stats.level===wanted)return;
    const id=wanted;if((failed.get(id)||0)>Date.now())return;
    pending=id;stats.loading=true;
    try{
      let data=dataCache.get(id);
      if(!data){const response=await fetch(`./data/${FILES[id]}`);if(!response.ok)throw new Error('Boundary detail unavailable');data=validateBoundaries(await response.json());dataCache.set(id,data);}
      if(shown&&wanted===id)replace(data,id);
      // Keep at most two parsed levels, including the small startup fallback.
      for(const key of dataCache.keys())if(key!=='coarse'&&key!==wanted)dataCache.delete(key);
    }catch{stats.failures++;failed.set(id,Date.now()+30000);}
    finally{pending=null;stats.loading=false;if(wanted!==id)load();}
  }
  replace(initialData,'coarse');
  return {group,stats:()=>({...stats}),update(now,w,h,pixelRatio,visible){
    shown=visible;group.visible=visible;
    if(w!==width||h!==height){width=w;height=h;group.traverse((o)=>o.material?.resolution.set(w,h));}
    if(!visible)return;
    const required=projectedPixels(camera.position.length(),camera.fov,h,pixelRatio),target=boundaryLevel(required);
    // Boundary levels use the imagery thresholds, with 12% hysteresis as well.
    const threshold=target==='fine'?10800:target==='medium'&&wanted==='coarse'?4096:wanted==='fine'?10800:4096;
    const ranks={coarse:0,medium:1,fine:2};
    if(target!==wanted&&(ranks[target]>ranks[wanted]?required>threshold*1.12:required<threshold*.88))wanted=target;
    stats.wanted=wanted;load();
  },dispose(){if(current)dispose(current);dataCache.clear();scene.remove(group);}};
}
