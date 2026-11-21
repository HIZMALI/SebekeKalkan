import {useRef, useState} from 'react';
import type {KeyboardEvent, PointerEvent} from 'react';
import {format} from './domain';
import type {Diagram, Point} from './domain';

export const BANDS = [
  ['negative','Negatif'], ['low','0–<15 m'], ['reduced','15–<20 m'], ['full','≥20 m'],
] as const;

export function band(pressure: number) {
  return pressure < 0 ? 'negative' : pressure < 15 ? 'low' : pressure < 20 ? 'reduced' : 'full';
}

const BAR_LABELS: Record<string, string> = {fault:'Arızalı · kapalı', work:'Onarılıyor · kapalı',
  repaired:'Onarıldı · açık', pending:'Arıza öncesi · açık', selected:'Seçili arıza'};
export type PipeMark = {kind: string; label: string; description?: string};

export default function NetworkStage({diagram, name, pressures, marks, eligible, onSelect}:{
  diagram: Diagram; name: string; pressures?: Record<string, number>; marks: Record<string, PipeMark>;
  eligible?: ReadonlySet<string>; onSelect?: (id: string) => void;
}) {
  const [camera,setCamera] = useState({x:0,y:0,z:1});
  const drag = useRef<Point|null>(null);
  const coords = [...Object.values(diagram.nodes), ...Object.values(diagram.pipes).flat(), ...diagram.other_links.flat()];
  const minX = Math.min(...coords.map(p=>p[0])), minY = Math.min(...coords.map(p=>p[1]));
  const spanX = Math.max(...coords.map(p=>p[0]))-minX || 1, spanY = Math.max(...coords.map(p=>p[1]))-minY || 1;
  const scale = 750 / Math.max(spanX,spanY);
  const rotate = Boolean(pressures) && spanY > 1.15 * spanX;
  const point = ([x,y]:Point):Point => {
    const dx=(x-minX-spanX/2)*scale, dy=(y-minY-spanY/2)*scale;
    return rotate?[-dy,dx]:[dx,dy];
  };
  const path = (points:Point[]) => points.map(p=>point(p).join(',')).join(' ');
  const width=(pressures?(rotate?spanY:spanX)*scale+90:1120)/camera.z;
  const height=(pressures?(rotate?spanX:spanY)*scale+128:900)/camera.z;
  const view=[camera.x-width/2,camera.y-height/2,width,height].join(' ');
  const zoom = (factor:number)=>setCamera(c=>({...c,z:Math.min(7,Math.max(.8,c.z*factor))}));
  const move = (dx:number,dy:number)=>setCamera(c=>({...c,x:c.x+dx,y:c.y+dy}));
  function key(e:KeyboardEvent<SVGSVGElement>) {
    if (e.target!==e.currentTarget) return;
    const directions:Record<string,Point>={ArrowLeft:[-width/12,0],ArrowRight:[width/12,0],
      ArrowUp:[0,-height/12],ArrowDown:[0,height/12]};
    if(directions[e.key]) {e.preventDefault(); move(...directions[e.key]);}
    if(e.key==='+'||e.key==='-') {e.preventDefault(); zoom(e.key==='+'?1.3:1/1.3);}
  }
  function pointer(e:PointerEvent<SVGSVGElement>) {
    if(!drag.current) return;
    const ratio=Math.max(width/e.currentTarget.clientWidth,height/e.currentTarget.clientHeight);
    move((drag.current[0]-e.clientX)*ratio,(drag.current[1]-e.clientY)*ratio);
    drag.current=[e.clientX,e.clientY];
  }
  return <div className="v4-map">
    <svg className="v4-network" tabIndex={0} role={onSelect?'group':'img'}
      aria-label={name+' şebeke şeması. Ok tuşlarıyla kaydırın.'} viewBox={view} onKeyDown={key}
      onPointerDown={e=>{if(!e.isPrimary||e.button!==0)return;e.currentTarget.setPointerCapture(e.pointerId);drag.current=[e.clientX,e.clientY];}}
      onPointerMove={pointer} onLostPointerCapture={()=>{drag.current=null;}}>
      <g className="v4-edges">
        {diagram.other_links.map((points,i)=><polyline key={i} className="device" vectorEffect="non-scaling-stroke" points={path(points)}/>)}
        {Object.entries(diagram.pipes).map(([id,points])=>{
          const active=marks[id];
          return <polyline key={id} data-pipe={id} data-kind={active?.kind}
            className={active?.kind||''} vectorEffect="non-scaling-stroke" points={path(points)}>
            <title>{'Boru '+id+(active?' · '+BAR_LABELS[active.kind]:'')+(active?.description?' · '+active.description:'')}</title>
          </polyline>;
        })}
      </g>
      <g className="v4-nodes">
        {Object.entries(diagram.nodes).map(([id,p])=>{
          const [x,y]=point(p), value=pressures?.[id];
          return <circle key={id} cx={x} cy={y} r={10/camera.z} vectorEffect="non-scaling-stroke" data-node={id}
            className={value===undefined?'neutral':band(value)}><title>
            {value===undefined?'Düğüm '+id:`Düğüm ${id} · ${format(value,6)} m`}</title></circle>;
        })}
      </g>
      <g className="v4-mark-labels" aria-hidden="true">
        {Object.entries(marks).map(([id,mark])=>{
          const p=diagram.pipes[id];
          if(!p) return null;
          const a=p[Math.floor((p.length-1)/2)], b=p[Math.ceil((p.length-1)/2)];
          const [x,y]=point([(a[0]+b[0])/2,(a[1]+b[1])/2]), size=(pressures?26:17)/camera.z;
          return <g key={id} className={mark.kind} transform={`translate(${x} ${y})`}>
            <circle cy={-size*1.2} r={size} vectorEffect="non-scaling-stroke"/>
            <text x="0" y={-size*.88} fontSize={size*.95} textAnchor="middle">{mark.label}</text>
          </g>;
        })}
      </g>
      {onSelect&&<g className="v4-eligible">
        {Object.entries(diagram.pipes).filter(([id])=>eligible?.has(id)).map(([id,p])=>
          <polyline key={id} points={path(p)} vectorEffect="non-scaling-stroke" tabIndex={0}
            role="button" aria-label={'Boru '+id} aria-pressed={Boolean(marks[id])}
            onPointerDown={e=>e.stopPropagation()} onClick={()=>onSelect(id)}
            onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(id);}}}>
            <title>Boru {id} · izolasyona uygun</title>
          </polyline>)}
      </g>}
    </svg>
    <div className="v4-map-controls" aria-label="Şema yakınlığı">
      <button type="button" aria-label="Yakınlaştır" onClick={()=>zoom(1.3)}>+</button>
      <button type="button" aria-label="Uzaklaştır" onClick={()=>zoom(1/1.3)}>−</button>
      <button type="button" onClick={()=>setCamera({x:0,y:0,z:1})}>Sıfırla</button>
    </div>
  </div>;
}
