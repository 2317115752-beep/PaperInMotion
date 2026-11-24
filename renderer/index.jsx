import React from 'react';
import {Composition, registerRoot} from 'remotion';
import {PaperVideo} from './paper-video.jsx';

function Root() {
  return (
    <Composition
      id="PaperInMotion"
      component={PaperVideo}
      durationInFrames={240}
      fps={24}
      width={1920}
      height={1080}
      defaultProps={{manifest: {title: 'Paper in Motion', language: 'en', scenes: []}}}
      calculateMetadata={({props}) => ({
        durationInFrames: props.manifest.scenes.reduce((sum, scene) => sum + scene.duration_frames, 0) || 240,
        fps: props.manifest.fps ?? 24,
        width: props.manifest.width ?? 1280,
        height: props.manifest.height ?? 720,
      })}
    />
  );
}

registerRoot(Root);
