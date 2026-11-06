export const BOUNDARY_LAYERS = ['countries','disputed','regions'];

export function validateBoundaries(data) {
  if (data?.schema_version !== 1 || !data.layers) throw new Error('Unsupported boundary data');
  let points = 0;
  for (const key of BOUNDARY_LAYERS) {
    if (!Array.isArray(data.layers[key])) throw new Error(`Missing ${key} boundaries`);
    for (const line of data.layers[key]) {
      if (!Array.isArray(line) || line.length < 2) throw new Error('Invalid boundary line');
      points += line.length;
      for (const p of line) {
        if (!Array.isArray(p) || p.length !== 2 || !p.every(Number.isFinite) || Math.abs(p[0]) > 180 || Math.abs(p[1]) > 90) throw new Error('Invalid boundary coordinate');
      }
    }
  }
  if (points > 250000) throw new Error('Boundary dataset exceeds the rendering budget');
  return data;
}

export function boundarySegments(lines,maxStep=.35,radius=1.0005){
  if(!(maxStep>0&&maxStep<=1))throw new Error('Invalid boundary tessellation');
  const positions=[],rad=Math.PI/180;
  const point=(lon,lat)=>{const a=lon*rad,b=lat*rad,c=radius*Math.cos(b);return [c*Math.cos(a),radius*Math.sin(b),-c*Math.sin(a)];};
  for(const line of lines)for(let i=1;i<line.length;i++){
    const [lon,lat]=line[i-1],dl=((line[i][0]-lon+540)%360)-180,dy=line[i][1]-lat;
    const n=Math.max(1,Math.ceil(Math.max(Math.abs(dl),Math.abs(dy))/maxStep));
    if(positions.length+n*6>6e6)throw new Error('Boundary tessellation exceeds budget');
    let a=point(lon,lat);
    for(let j=1;j<=n;j++){const b=point(lon+dl*j/n,lat+dy*j/n);positions.push(...a,...b);a=b;}
  }
  return new Float32Array(positions);
}
