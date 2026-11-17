import {bundle} from '@remotion/bundler';
import {renderMedia,selectComposition} from '@remotion/renderer';
import {readFile,mkdir,mkdtemp,copyFile,rm,stat,realpath} from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url));
const emit=(event,values={})=>process.stdout.write(JSON.stringify({event,...values})+'\n');
export async function renderPaperInMotion(manifestPath,outputPath){
  const manifest=JSON.parse(await readFile(manifestPath,'utf8'));
  if(!Array.isArray(manifest.scenes)||!manifest.scenes.length||manifest.scenes.length>20)throw new Error('Invalid scene count');
  let total=0;
  for(const s of manifest.scenes){
    if(!Number.isInteger(s.duration_frames)||s.duration_frames<1||s.duration_frames>24*300)throw new Error('Invalid scene duration');
    total+=s.duration_frames;
  }
  if(total>24*1800)throw new Error('Video too long');
  const temp=await mkdtemp(path.join(os.tmpdir(),'pim-render-'));
  try{
    const publicDir=path.join(temp,'public');await mkdir(publicDir);
    for(const [i,s] of manifest.scenes.entries()){
      if(!s.audio_path)continue;
      if(!path.isAbsolute(s.audio_path))throw new Error('Audio path must be absolute');
      const source=await realpath(s.audio_path);const info=await stat(source);
      if(!info.isFile()||info.size>64*1024*1024||path.extname(source)!=='.wav')throw new Error('Invalid audio');
      const name=`audio-${i}.wav`;await copyFile(source,path.join(publicDir,name));
      s.audio_file=name;delete s.audio_path;
    }
    emit('render_start',{frames:total,scenes:manifest.scenes.length});
    const serveUrl=await bundle({entryPoint:path.join(here,'index.jsx'),publicDir,outDir:path.join(temp,'bundle')});
    const inputProps={manifest};
    const composition=await selectComposition({serveUrl,id:'PaperInMotion',inputProps});
    await mkdir(path.dirname(path.resolve(outputPath)),{recursive:true});
    let previous=-5;
    await renderMedia({serveUrl,composition,inputProps,codec:'h264',audioCodec:'aac',outputLocation:outputPath,concurrency:2,pixelFormat:'yuv420p',crf:20,
      onProgress:({progress})=>{const percent=Math.floor(progress*100);if(percent>=previous+5||percent===100){previous=percent;emit('render_progress',{percent});}}});
    emit('render_complete',{frames:total,duration:total/24,has_audio:manifest.scenes.some(s=>s.audio_file)});
  }finally{await rm(temp,{recursive:true,force:true});}
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  if(process.argv.length!==4){emit('render_error',{message:'Usage: node renderer/render.mjs manifest.json output.mp4'});process.exitCode=1;}
  else renderPaperInMotion(process.argv[2],process.argv[3]).catch(error=>{emit('render_error',{message:error.message});process.exitCode=1;});
}
