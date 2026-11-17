import React from 'react';
import {AbsoluteFill,Audio,Sequence,staticFile,useCurrentFrame,interpolate} from 'remotion';
const C={bg:'#F7F4ED',ink:'#203048',purple:'#6353BB',orange:'#D9A365',muted:'#93909B',line:'#E3DED8',pale:'#EEEAFA'};
const font='-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif';
const choose=(zh,a,b)=>zh?a:b;
const text=(v,max=120)=>typeof v==='string'?v.length>max?v.slice(0,max-1)+'…':v:'';
const appearance=(frame,delay=0)=>interpolate(frame,[delay,delay+14],[0,1],{extrapolateLeft:'clamp',extrapolateRight:'clamp'});
const fmt=n=>Number.isFinite(n)?Number(n.toFixed(3)):'—';

function Reveal({children,delay=0,style={}}){const frame=useCurrentFrame();const p=appearance(frame,delay);return <div style={{opacity:p,transform:`translateY(${(1-p)*16}px)`,...style}}>{children}</div>}
function Matrix({value,label,color=C.ink,max=4,size=23}){
  const values=Array.isArray(value)?value.slice(0,max):[];
  const rows=values.map(v=>Array.isArray(v)?v.slice(0,max):[v]);
  return <div style={{display:'flex',flexDirection:'column',alignItems:'center',gap:11,color}}><span style={{fontWeight:650,fontSize:18}}>{label}</span><div style={{borderLeft:`2px solid ${color}`,borderRight:`2px solid ${color}`,padding:'7px 14px',display:'grid',gap:8,alignContent:'center',minHeight:48}}>{rows.map((r,i)=><div key={i} style={{display:'flex',gap:14,justifyContent:'center',fontSize:size,fontVariantNumeric:'tabular-nums'}}>{r.map((n,j)=><span key={j} style={{minWidth:23,textAlign:'center'}}>{fmt(n)}</span>)}</div>)}</div></div>
}
function Vector({values,color=C.purple}){return <span style={{color,fontSize:25,whiteSpace:'nowrap',fontVariantNumeric:'tabular-nums'}}>[{(Array.isArray(values)?values:[]).slice(0,4).map(fmt).join(', ')}]</span>}
function Flow({labels,frame,zh}){
  const nodes=(labels?.length?labels:[choose(zh,'输入','Input'),choose(zh,'方法','Method'),choose(zh,'输出','Output')]).slice(0,5);
  const active=Math.min(nodes.length-1,Math.floor(frame/28));
  return <div style={{display:'flex',alignItems:'center',width:'100%',gap:18}}>{nodes.map((n,i)=><React.Fragment key={i}>{i>0&&<span style={{color:C.orange,fontSize:30}}>→</span>}<Reveal delay={i*16} style={{flex:1,minWidth:0,border:`1px solid ${active===i?C.purple:C.line}`,background:active===i?C.purple:'#fff',borderRadius:18,padding:'24px 18px',minHeight:155,color:active===i?'white':C.ink}}><div style={{fontSize:12,opacity:.5,marginBottom:25}}>{String(i+1).padStart(2,'0')}</div><div style={{fontSize:nodes.length>3?23:28,fontWeight:550,lineHeight:1.5,overflowWrap:'anywhere'}}>{text(n,nodes.length>3?38:60)}</div></Reveal></React.Fragment>)}</div>
}
function Diagram({frame,zh}){
  return <svg viewBox="0 0 300 310" width="100%" height="100%">
    <circle cx="150" cy="155" r="130" fill="none" stroke="#E5DFD6"/><circle cx="150" cy="155" r="105" fill="none" stroke="#E9E4DD"/>
    {[0,1].map(i=><g key={i}><path d={`M150 ${95+i*92} V${116+i*92}`} stroke={C.purple} strokeWidth="2"/><circle cx="150" cy={96+i*92+frame%20} r="4" fill={C.orange}/></g>)}
    {[choose(zh,'论文证据','Paper evidence'),choose(zh,'核心方法','Core mechanism'),choose(zh,'直观理解','Clear understanding')].map((s,i)=><g key={i} opacity={appearance(frame,i*15)}><rect x="33" y={32+i*92} width="234" height="62" rx="15" fill={i===1?C.purple:'#fff'} stroke={i===1?C.purple:C.line}/><text x="150" y={70+i*92} textAnchor="middle" fontSize="18" fontFamily={font} fill={i===1?'white':C.ink}>{s}</text></g>)}
  </svg>
}
function LowRank({scene,zh}){
  const e=scene.example, f=useCurrentFrame();
  const stage=Math.min(3,Math.floor(f/(scene.duration_frames/4)));
  const scaled=e.scale!==1;
  return <div style={{display:'grid',gridTemplateColumns:'625px 447px',gap:32,height:'100%'}}>
    <div><Reveal style={{fontSize:38,fontWeight:600,marginBottom:20}}>y = <span style={{color:C.muted}}>W₀x</span> + <span style={{color:C.purple}}>{scaled?'s·':''}B(Ax)</span></Reveal>
      <Reveal delay={8} style={{display:'flex',justifyContent:'space-around',alignItems:'center',background:'#fff',border:`1px solid ${C.line}`,borderRadius:18,padding:'18px 14px'}}><Matrix value={e.base} label="W₀" color={C.muted}/><Matrix value={e.A} label="A" color={C.purple}/><Matrix value={e.B} label="B" color={C.purple}/></Reveal>
      <Reveal delay={14} style={{display:'flex',alignItems:'center',gap:20,marginTop:18,padding:'18px 24px',background:'#fff',border:`1px solid ${C.line}`,borderRadius:15}}><span style={{fontSize:23}}>x =</span><Vector values={e.input}/><span style={{marginLeft:'auto',color:C.muted,fontSize:15}}>{choose(zh,'玩具输入','Toy input')}</span></Reveal>
      {scaled&&<div style={{fontSize:16,color:C.muted,marginTop:12}}>s = {fmt(e.scale)}</div>}
    </div>
    <div style={{display:'flex',flexDirection:'column',gap:12}}>{[
      ['W₀x',e.baseline,choose(zh,'基线输出','Base output')],['Ax',e.hidden,choose(zh,'低维表示','Low-rank state')],[scaled?'s·B(Ax)':'B(Ax)',e.delta,choose(zh,'更新分支','Update')],['y',e.output,choose(zh,'最终输出','Final output')]
    ].map(([label,values,desc],i)=><Reveal key={i} delay={12+i*14} style={{height:77,display:'flex',alignItems:'center',gap:10,padding:'14px 17px',borderRadius:16,border:`1px solid ${i===3?C.purple:C.line}`,background:i===3?C.purple:stage===i?C.pale:'#fff',color:i===3?'white':C.ink}}><span style={{fontSize:22,minWidth:76,fontWeight:550}}>{label}</span><Vector values={values} color={i===3?'white':C.purple}/><span style={{marginLeft:'auto',fontSize:13,maxWidth:93,lineHeight:1.5,color:i===3?'#DCD5F5':C.muted}}>{desc}</span></Reveal>)}</div>
  </div>
}
function Attention({scene,zh}){
  const e=scene.example;
  return <div style={{height:'100%',display:'flex',flexDirection:'column',justifyContent:'center',gap:25}}><Reveal style={{fontSize:33,fontWeight:550,color:C.purple}}>Attention(Q, K, V) = softmax(QKᵀ / √d) V</Reveal><div style={{display:'flex',justifyContent:'space-around',alignItems:'center',padding:'25px 15px',background:'#fff',border:`1px solid ${C.line}`,borderRadius:20}}>{[['Q',e.Q],['K',e.K],['V',e.V],[choose(zh,'权重','Weights'),e.weights],[choose(zh,'输出','Output'),e.output]].map(([label,value],i)=><Reveal key={i} delay={i*16}><Matrix value={value} label={label} color={i>2?C.purple:C.ink} size={22}/></Reveal>)}</div><div style={{fontSize:18,color:C.muted}}>{choose(zh,'玩具示例：softmax 权重按行归一化，数值由 Python 执行。','Toy example: row-normalized softmax weights, computed in Python.')}</div></div>
}
function Content({scene,manifest,zh,frame}){
  const bullets=(scene.bullets||[]).slice(0,4);
  if(scene.example?.kind==='low_rank'&&scene.visual_type==='matrix')return <LowRank scene={scene} zh={zh}/>;
  if(scene.example?.kind==='scaled_dot_attention'&&['matrix','equation'].includes(scene.visual_type))return <Attention scene={scene} zh={zh}/>;
  if(scene.visual_type==='title')return <div style={{height:'100%',display:'grid',gridTemplateColumns:'730px 320px',gap:54,alignItems:'center'}}><div><Reveal style={{fontSize:13,letterSpacing:3,color:C.purple,marginBottom:25}}>{choose(zh,'从论文，到理解','FROM PAPER TO UNDERSTANDING')}</Reveal><Reveal delay={8} style={{fontSize:zh?60:54,fontWeight:650,lineHeight:1.2,letterSpacing:-1.3,overflowWrap:'anywhere'}}>{text(scene.title,zh?40:80)}</Reveal><Reveal delay={16} style={{width:128,height:5,background:C.orange,borderRadius:2,margin:'27px 0'}}/><Reveal delay={24} style={{fontSize:25,lineHeight:1.6,color:C.muted}}>{text(bullets[0]||manifest.paper_title,zh?65:120)}</Reveal></div><Diagram frame={frame} zh={zh}/></div>;
  if(scene.visual_type==='flow')return <div style={{height:'100%',display:'flex',flexDirection:'column',justifyContent:'center',gap:35}}><Flow labels={scene.nodes?.length?scene.nodes:bullets} frame={frame} zh={zh}/><Reveal delay={20} style={{fontSize:24,color:C.muted}}>{text(scene.formula||bullets[0],120)}</Reveal></div>;
  if(scene.visual_type==='equation')return <div style={{height:'100%',display:'grid',gridTemplateColumns:'1.3fr 1fr',gap:35,alignItems:'center'}}><Reveal style={{background:'#fff',border:`1px solid ${C.line}`,borderRadius:22,padding:35,minHeight:235,display:'flex',flexDirection:'column',justifyContent:'center'}}><span style={{fontSize:12,color:C.purple,letterSpacing:2,marginBottom:25}}>{choose(zh,'核心关系','CORE RELATIONSHIP')}</span><span style={{fontSize:(scene.formula||'').length>65?28:36,lineHeight:1.6,overflowWrap:'anywhere',fontFamily:'Georgia,"PingFang SC",serif'}}>{text(scene.formula||bullets[0],160)}</span></Reveal><Points bullets={bullets} zh={zh}/></div>;
  if(scene.visual_type==='comparison')return <div style={{height:'100%',display:'grid',gridTemplateColumns:'1fr 1fr',gap:28,alignItems:'center'}}>{[bullets.slice(0,Math.ceil(bullets.length/2)),bullets.slice(Math.ceil(bullets.length/2))].map((items,i)=><Reveal key={i} delay={i*18} style={{padding:28,minHeight:285,borderRadius:20,border:`1px solid ${C.line}`,background:i?C.pale:'#fff'}}><div style={{fontSize:12,color:C.purple,paddingBottom:18,marginBottom:20,borderBottom:`1px solid ${C.line}`,letterSpacing:2}}>{choose(zh,`视角 ${i+1}`,`PERSPECTIVE ${i+1}`)}</div><Points bullets={items} zh={zh}/></Reveal>)}</div>;
  return <div style={{height:'100%',display:'grid',gridTemplateColumns:'710px 350px',gap:44,alignItems:'center'}}><Points bullets={bullets.length?bullets:[scene.title]} zh={zh}/><Diagram frame={frame} zh={zh}/></div>
}
function Points({bullets,zh}){return <div style={{display:'flex',flexDirection:'column',gap:22}}>{bullets.map((b,i)=><Reveal key={i} delay={12+i*20} style={{display:'flex',gap:15,alignItems:'flex-start'}}><span style={{flexShrink:0,width:28,height:28,borderRadius:8,background:C.purple,color:'white',display:'grid',placeItems:'center',fontSize:12,marginTop:5}}>{i+1}</span><span style={{fontSize:26,lineHeight:1.55,fontWeight:450,overflowWrap:'anywhere'}}>{text(b,zh?50:105)}</span></Reveal>)}</div>}
function subtitleChunks(narration,zh){
  const parts=(narration||'').match(zh?/[^。！？；\n]+[。！？；]?/g:/[^.!?\n]+[.!?]?/g)||[];
  const chunks=[];const limit=zh?48:105;
  for(let part of parts){part=part.trim();while(part.length>limit){let cut=limit;if(!zh){const space=part.lastIndexOf(' ',limit);if(space>limit/2)cut=space;}chunks.push(part.slice(0,cut));part=part.slice(cut).trim();}if(part)chunks.push(part);}
  return chunks;
}
function Scene({scene,manifest,index,start,total}){
  const f=useCurrentFrame(),zh=manifest.language==='zh';
  const chunks=subtitleChunks(scene.narration,zh),weights=chunks.reduce((s,c)=>s+c.length,0);
  const at=Math.min(1,f/Math.max(1,(scene.audio_duration||scene.duration_frames/24)*24))*weights;
  let current='',sum=0;for(const chunk of chunks){sum+=chunk.length;if(at<=sum){current=chunk;break;}}
  const title=scene.visual_type==='title';
  return <AbsoluteFill style={{background:C.bg,color:C.ink,fontFamily:font,overflow:'hidden'}}>
    <div style={{position:'absolute',right:-110,top:-330,width:560,height:560,border:'1px solid #E9E2D8',borderRadius:'50%'}}/>
    <div style={{position:'absolute',left:64,right:64,top:32,display:'flex',justifyContent:'space-between',alignItems:'center'}}><span style={{fontSize:14,letterSpacing:1.7,fontWeight:650,display:'flex',alignItems:'center',gap:10}}><span style={{width:13,height:13,background:C.purple,borderRadius:4}}/>PAPER IN MOTION</span><span style={{display:'flex',gap:20,fontSize:12,color:C.muted}}>{manifest.is_demo&&<span>{choose(zh,'预制演示 · 无语音','PREPARED DEMO · NO AUDIO')}</span>}<span>{String(index+1).padStart(2,'0')} / {String(manifest.scenes.length).padStart(2,'0')}</span></span></div>
    <div style={{position:'absolute',left:64,right:64,top:95,display:'flex',alignItems:'center',gap:18}}><span style={{fontSize:12,color:C.purple,border:'1px solid #D6CCE9',padding:'6px 12px',borderRadius:30}}>{choose(zh,scene.visual_type==='result'?'重点回顾':'论文讲解',scene.visual_type==='result'?'TAKEAWAY':'PAPER EXPLAINER')}</span><span style={{flex:1,height:1,background:C.line}}/></div>
    {!title&&<Reveal style={{position:'absolute',left:64,right:64,top:151,fontSize:zh?36:34,fontWeight:600,lineHeight:1.25,maxHeight:86,overflow:'hidden'}}>{text(scene.title,zh?45:90)}</Reveal>}
    <div style={{position:'absolute',left:64,right:64,top:title?155:231,bottom:120}}><Content scene={scene} manifest={manifest} zh={zh} frame={f}/></div>
    <div style={{position:'absolute',left:64,right:64,bottom:52,minHeight:35,display:'flex',alignItems:'center',justifyContent:'center',textAlign:'center',fontSize:zh?22:20,lineHeight:1.4}}>{current}</div>
    <div style={{position:'absolute',left:64,right:64,bottom:19,display:'flex',justifyContent:'space-between',gap:25,fontSize:11,color:C.muted}}><span style={{maxWidth:790,whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>{manifest.paper_title||manifest.title}</span><span>{scene.source_pages?.length?choose(zh,`来源：第${scene.source_pages.join('、')}页`,`Source: p. ${scene.source_pages.join(', ')}`):choose(zh,'示例计算 · 非论文实验数据','Toy example · not empirical data')}</span></div>
    <div style={{position:'absolute',left:0,right:0,bottom:0,height:4,background:'#E4DDD5'}}><div style={{height:'100%',width:`${Math.min(100,(start+f+1)/total*100)}%`,background:C.purple}}/></div>
    {scene.audio_file&&<Audio src={staticFile(scene.audio_file)}/>}
  </AbsoluteFill>
}
export function PaperVideo({manifest}){const total=manifest.scenes.reduce((s,v)=>s+v.duration_frames,0);let start=0;return <AbsoluteFill>{manifest.scenes.map((scene,i)=>{const from=start;start+=scene.duration_frames;return <Sequence key={i} from={from} durationInFrames={scene.duration_frames}><Scene scene={scene} manifest={manifest} index={i} start={from} total={total}/></Sequence>})}</AbsoluteFill>}
