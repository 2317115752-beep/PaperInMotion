import React from 'react';
import {Composition, registerRoot} from 'remotion';
import {PaperVideo} from './paper-video.jsx';
function Root(){
  return <Composition id="PaperInMotion" component={PaperVideo} durationInFrames={240} fps={24} width={1280} height={720}
    defaultProps={{manifest:{title:'Paper in Motion',language:'zh',scenes:[]}}}
    calculateMetadata={({props})=>({durationInFrames:props.manifest.scenes.reduce((n,s)=>n+s.duration_frames,0),fps:24,width:1280,height:720})}/>;
}
registerRoot(Root);
