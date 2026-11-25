import {bundle} from '@remotion/bundler';
import {renderMedia, renderStill, selectComposition} from '@remotion/renderer';
import {access, readFile, mkdir, mkdtemp, copyFile, rm, stat, realpath} from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath} from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const emit = (event, values = {}) => process.stdout.write(JSON.stringify({event, ...values}) + '\n');
const macChrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const chromeOptions = browserExecutable => browserExecutable
  ? {browserExecutable, chromeMode: 'chrome-for-testing'}
  : {};

async function fallbackChrome(error, preferredChrome) {
  if (preferredChrome || process.platform !== 'darwin' ||
      !/target closed|browser (?:closed|disconnected|process exited)/i.test(error.message)) return null;
  try {
    await access(macChrome);
    return macChrome;
  } catch {
    return null;
  }
}


async function copySceneAsset(sourcePath, publicDir, name, limit) {
  if (typeof sourcePath !== 'string' || !path.isAbsolute(sourcePath)) {
    throw new Error('Scene asset path must be absolute');
  }
  const source = await realpath(sourcePath);
  const info = await stat(source);
  const ext = path.extname(name);
  if (!info.isFile() || info.size === 0 || info.size > limit || path.extname(source).toLowerCase() !== ext) {
    throw new Error(`Invalid scene asset (${ext})`);
  }
  await copyFile(source, path.join(publicDir, name));
}

export async function renderPaperInMotion(manifestPath, outputPath, {previewPath, previewFrame, previewOnly = false} = {}) {
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
  const fps = manifest.fps ?? 24;
  const width = manifest.width ?? 1280;
  const height = manifest.height ?? 720;
  if (![24, 25, 30].includes(fps) || ![[1280, 720], [1920, 1080]].some(([w, h]) => w === width && h === height)) {
    throw new Error('Unsupported render dimensions or frame rate');
  }
  if (!Array.isArray(manifest.scenes) || !manifest.scenes.length || manifest.scenes.length > 20) {
    throw new Error('Invalid scene count');
  }
  let total = 0;
  for (const scene of manifest.scenes) {
    if (!Number.isInteger(scene.duration_frames) || scene.duration_frames < 1 || scene.duration_frames > fps * 300) {
      throw new Error('Invalid scene duration');
    }
    total += scene.duration_frames;
  }
  if (total > fps * 1800) throw new Error('Video too long');

  const temp = await mkdtemp(path.join(os.tmpdir(), 'pim-render-'));
  let phase = 'bundle';
  try {
    const publicDir = path.join(temp, 'public');
    await mkdir(publicDir);
    for (const [index, scene] of manifest.scenes.entries()) {
      if (scene.audio_path) {
        const name = `audio-${index}.wav`;
        await copySceneAsset(scene.audio_path, publicDir, name, 64 * 1024 * 1024);
        scene.audio_file = name;
        delete scene.audio_path;
      }
      if (scene.figure_path) {
        const name = `figure-${index}.png`;
        await copySceneAsset(scene.figure_path, publicDir, name, 20 * 1024 * 1024);
        scene.figure_file = name;
        delete scene.figure_path;
      }
    }

    emit('render_start', {frames: total, scenes: manifest.scenes.length, width, height});
    const serveUrl = await bundle({
      entryPoint: path.join(here, 'index.jsx'),
      publicDir,
      outDir: path.join(temp, 'bundle'),
    });
    const inputProps = {manifest};
    const render = async browserExecutable => {
      const browser = chromeOptions(browserExecutable);
      phase = 'browser_start';
      const composition = await selectComposition({serveUrl, id: 'PaperInMotion', inputProps, ...browser});

      if (previewPath) {
        phase = 'preview';
        const defaultFrame = Math.floor(manifest.scenes[0].duration_frames * 0.32);
        const frame = Math.max(0, Math.min(total - 1, previewFrame ?? defaultFrame));
        await mkdir(path.dirname(path.resolve(previewPath)), {recursive: true});
        await renderStill({serveUrl, composition, inputProps, frame, output: previewPath, imageFormat: 'png', ...browser});
        emit('preview_complete', {frame});
      }
      if (previewOnly) return;

      phase = 'encoding';
      await mkdir(path.dirname(path.resolve(outputPath)), {recursive: true});
      let previous = -5;
      await renderMedia({
        serveUrl,
        ...browser,
        composition,
        inputProps,
        codec: 'h264',
        audioCodec: 'aac',
        audioBitrate: '192k',
        outputLocation: outputPath,
        concurrency: 2,
        pixelFormat: 'yuv420p',
        crf: 17,
        jpegQuality: 94,
        colorSpace: 'bt709',
        onProgress: ({progress}) => {
          const percent = Math.floor(progress * 100);
          if (percent >= previous + 5 || percent === 100) {
            previous = percent;
            emit('render_progress', {percent});
          }
        },
      });
    };
    const preferredChrome = process.env.PIM_CHROME_BINARY?.trim();
    try {
      await render(preferredChrome);
    } catch (error) {
      // macOS can deny a browser child access to ICU data when the bundled shell is on the Desktop.
      const fallback = await fallbackChrome(error, preferredChrome);
      if (!fallback) throw error;
      emit('render_retry', {phase, message: error.message, browser: 'Google Chrome'});
      await render(fallback);
    }
    if (previewOnly) return;
    emit('render_complete', {frames: total, duration: total / fps, has_audio: manifest.scenes.some(scene => scene.audio_file)});
  } catch (cause) {
    const error = new Error(cause.message, {cause});
    error.phase = phase;
    throw error;
  } finally {
    await rm(temp, {recursive: true, force: true});
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (![4, 5].includes(process.argv.length)) {
    emit('render_error', {message: 'Usage: node renderer/render.mjs manifest.json output.mp4 [preview.png]'});
    process.exitCode = 1;
  } else {
    renderPaperInMotion(process.argv[2], process.argv[3], {previewPath: process.argv[4]}).catch(error => {
      emit('render_error', {phase: error.phase, message: error.message});
      process.exitCode = 1;
    });
  }
}
