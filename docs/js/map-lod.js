const RAD=Math.PI/180;
export const TILE_CONFIG={tileSize:675,gutter:1,baseColumns:4,baseRows:2,minLevel:2,maxLevel:3,maxTiles:32,concurrency:4};

export function worldPixels(level){return TILE_CONFIG.tileSize*(TILE_CONFIG.baseColumns<<level);}
export function projectedPixels(distance,fov,height,pixelRatio=1){
  return Math.PI*height*Math.min(2,Math.max(1,pixelRatio))/(Math.tan(fov*RAD/2)*Math.max(.05,distance-1));
}
// baseWidth is the permanent globe texture: tiles are needed only above it.
export function chooseLevel(required,previous=-1,baseWidth=8192){
  if(!Number.isFinite(required)||required<=0)return -1;
  const target=required<=baseWidth?-1:required<=10800?2:3;
  // Small zoom gestures near a threshold must not repeatedly replace textures.
  if(target!==previous&&(previous===-1||previous===2||previous===3)){
    const low=Math.min(target,previous),boundary=low<0?baseWidth:10800;
    if(target>previous&&required<boundary*1.12)return previous;
    if(target<previous&&required>boundary*.88)return previous;
  }
  return target;
}
export function boundaryLevel(required){return required>10800?'fine':required>4096?'medium':'coarse';}
export function tileBounds(level,x,y){
  const columns=TILE_CONFIG.baseColumns<<level,rows=TILE_CONFIG.baseRows<<level;
  if(!Number.isInteger(level)||level<TILE_CONFIG.minLevel||level>TILE_CONFIG.maxLevel||!Number.isInteger(x)||!Number.isInteger(y)||x<0||x>=columns||y<0||y>=rows)throw new Error('Invalid map tile');
  return {level,x,y,columns,rows,west:x*360/columns-180,east:(x+1)*360/columns-180,north:90-y*180/rows,south:90-(y+1)*180/rows,key:`${level}/${x}/${y}`};
}
export function tileUV(tile,u,v){return [(tile.x+u)/tile.columns,1-(tile.y+1-v)/tile.rows];}
export function llVector(lon,lat,r=1){const a=lon*RAD,b=lat*RAD,c=r*Math.cos(b);return [c*Math.cos(a),r*Math.sin(b),-c*Math.sin(a)];}

// A strict LRU includes in-flight textures in its count. Base imagery is separate.
export class TileCache {
  constructor({load,dispose,max=TILE_CONFIG.maxTiles,concurrency=TILE_CONFIG.concurrency}){
    this.load=load;this.dispose=dispose;this.max=max;this.concurrency=concurrency;
    this.entries=new Map();this.wanted=new Map();this.active=0;this.clock=0;this.failures=0;this.loads=0;this.peak=0;this.stopped=false;
  }
  select(tiles){
    this.wanted=new Map(tiles.slice(0,this.max).map((t)=>[t.key,t]));
    for(const [key,entry]of this.entries)if(this.wanted.has(key))entry.used=++this.clock;
    this.pump();
  }
  pump(){
    if(this.stopped||this.paused)return;
    for(const [key,tile]of this.wanted){
      if(this.active>=this.concurrency)break;
      const existing=this.entries.get(key);
      if(existing?.status==='failed'&&Date.now()>=existing.retryAt)this.entries.delete(key);
      else if(existing)continue;
      while(this.entries.size>=this.max){
        const victim=[...this.entries].filter(([k,e])=>!this.wanted.has(k)&&e.status!=='loading').sort((a,b)=>a[1].used-b[1].used)[0];
        if(!victim)break;
        if(victim[1].value)this.dispose(victim[1].value);
        this.entries.delete(victim[0]);
      }
      if(this.entries.size>=this.max)continue;
      const entry={status:'loading',used:++this.clock,tile};this.entries.set(key,entry);this.active++;this.loads++;
      this.peak=Math.max(this.peak,this.entries.size);
      Promise.resolve().then(()=>this.load(tile)).then((value)=>{
        if(this.stopped){this.dispose(value);return;}
        entry.value=value;entry.status='ready';
      }).catch(()=>{entry.status='failed';entry.retryAt=Date.now()+30000;this.failures++;}).finally(()=>{this.active--;this.pump();});
    }
  }
  ready(){return [...this.wanted.keys()].map((key)=>this.entries.get(key)).filter((e)=>e?.status==='ready');}
  stats(){return {resident:this.entries.size,active:this.active,visible:this.ready().length,wanted:this.wanted.size,loads:this.loads,failures:this.failures,peak:this.peak,max:this.max};}
  clear(){this.stopped=true;for(const entry of this.entries.values())if(entry.value)this.dispose(entry.value);this.entries.clear();this.wanted.clear();}
}
