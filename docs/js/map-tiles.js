import * as THREE from 'three';
import {TILE_CONFIG,TileCache,worldPixels,projectedPixels,chooseLevel,tileBounds,llVector} from './map-lod.js';

// The Earth shader fades the day map out by mu=-0.055, so a tile wholly beyond this angle from the Sun draws nothing from its texture.
const DAY_EDGE=Math.acos(-.065);
const SWEEP_COS=Math.cos(Math.PI/180);  // more than 1 degree between tile updates, 160 ms apart

export function createMapTiles({scene,camera,renderer,earthMaterial,loadTexture,baseWidth=8192}){
  const group=new THREE.Group();scene.add(group);
  const frustum=new THREE.Frustum(),matrix=new THREE.Matrix4(),direction=new THREE.Vector3(),sun=earthMaterial.uniforms.sunDir.value;
  const lastDirection=new THREE.Vector3();
  let level=-1,required=0,last=-Infinity,lastView='',selection=[],lastDistance=0;
  const cache=new TileCache({load:async(tile)=>{
    const texture=await loadTexture(`./tex/tiles/${tile.key}.jpg`);
    const {west,east,north,south}=tile;
    const geometry=new THREE.SphereGeometry(1.00015,Math.max(2,Math.ceil((east-west)/.7)),Math.max(2,Math.ceil((north-south)/.7)),(west+180)*Math.PI/180,(east-west)*Math.PI/180,(90-north)*Math.PI/180,(north-south)*Math.PI/180);
    // SphereGeometry offsets polar UVs for a whole-world map; a tile uses exact UVs.
    const uv=geometry.attributes.uv,columns=geometry.parameters.widthSegments,rows=geometry.parameters.heightSegments;
    for(let y=0;y<=rows;y++)for(let x=0;x<=columns;x++)uv.setXY(y*(columns+1)+x,x/columns,1-y/rows);
    const edge=TILE_CONFIG.tileSize+2*TILE_CONFIG.gutter,g=TILE_CONFIG.gutter/edge,span=TILE_CONFIG.tileSize/edge;
    const material=new THREE.ShaderMaterial({uniforms:{...earthMaterial.uniforms,dayTex:{value:texture},tileRect:{value:new THREE.Vector4(tile.x/tile.columns,1-(tile.y+1)/tile.rows,1/tile.columns,1/tile.rows)},imageRect:{value:new THREE.Vector4(g,g,span,span)}},vertexShader:earthMaterial.vertexShader,fragmentShader:earthMaterial.fragmentShader});
    const mesh=new THREE.Mesh(geometry,material);mesh.visible=false;group.add(mesh);
    return {mesh,texture};
  },dispose:({mesh,texture})=>{group.remove(mesh);mesh.geometry.dispose();mesh.material.dispose();texture.dispose();texture.image?.close?.();}});
  function candidates(z){
    if(z<0)return [];
    const d=camera.position.length(),horizon=Math.acos(1/d);direction.copy(camera.position).normalize();
    const tiles=[];
    for(let y=0;y<(TILE_CONFIG.baseRows<<z);y++)for(let x=0;x<(TILE_CONFIG.baseColumns<<z);x++){
      const tile=tileBounds(z,x,y),mid=new THREE.Vector3(...llVector((tile.west+tile.east)/2,(tile.south+tile.north)/2));
      const angle=((tile.east-tile.west)+(tile.north-tile.south))*Math.PI/360;
      if(Math.acos(Math.min(1,Math.max(-1,direction.dot(mid))))>horizon+angle)continue;
      if(sun.dot(mid)<Math.cos(Math.min(Math.PI,DAY_EDGE+angle)))continue;
      tile.score=-camera.position.distanceTo(mid);   // nearest ground first in tilted views
      if(!frustum.intersectsSphere(new THREE.Sphere(mid,2*Math.sin(angle/2))))continue;
      tiles.push(tile);
    }
    return tiles.sort((a,b)=>b.score-a.score);
  }
  function update(now,width,height){
    if(now-last>=160){
      last=now;
      // While the view sweeps fast, tiles in flight finish but no new ones start: most would be out of view before they arrive.
      const distance=camera.position.length();direction.copy(camera.position).normalize();
      cache.paused=lastDistance>0&&(direction.dot(lastDirection)<SWEEP_COS||Math.abs(distance/lastDistance-1)>.03);
      lastDirection.copy(direction);lastDistance=distance;
      const key=[...camera.position.toArray(),...camera.quaternion.toArray(),camera.aspect,width,height,renderer.getPixelRatio()].map((x)=>x.toFixed(4)).join(',')+sun.toArray().map((x)=>x.toFixed(3)).join(',');
      if(key!==lastView){
        lastView=key;camera.updateMatrixWorld();matrix.multiplyMatrices(camera.projectionMatrix,camera.matrixWorldInverse);frustum.setFromProjectionMatrix(matrix);
        required=projectedPixels(camera.position.length(),camera.fov,height,renderer.getPixelRatio());
        const previous=level;
        level=chooseLevel(required,level,baseWidth);selection=candidates(level);
        // Stepping up to a finer tile level needs room to spare, so a view near the limit does not flip between levels while dragged.
        const room=()=>previous>=0&&level>previous?TILE_CONFIG.maxTiles*.8:TILE_CONFIG.maxTiles;
        while(selection.length>room()&&level>=0){level=level<=2?-1:level-1;selection=candidates(level);}
        cache.select(selection);
      }
      cache.pump();
    }
    for(const entry of cache.entries.values())if(entry.value)entry.value.mesh.visible=false;
    const shown=cache.ready();for(const entry of shown)entry.value.mesh.visible=true;
    return shown.length;
  }
  return {update,group,setBaseWidth:(width)=>{baseWidth=width;lastView='';},stats:()=>({...cache.stats(),level,requiredPixels:required,worldWidth:level>=0?worldPixels(level):baseWidth,nativeLimit:21600,estimatedTileBytes:cache.entries.size*(677**2)*4*4/3}),dispose:()=>{cache.clear();scene.remove(group);}};
}
