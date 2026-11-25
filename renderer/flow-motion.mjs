const clamp = value => Math.min(1, Math.max(0, value));

export function flowTiming(starts, duration, frame, fps) {
  const active = Math.max(0, starts.findLastIndex(start => start <= frame));
  const progress = starts.map((start, index) => {
    const span = Math.max(1, (starts[index + 1] ?? duration) - start);
    const travel = Math.min(span * .76, fps * 2.6);
    return clamp((frame - start) / Math.max(1, travel));
  });
  return {active, progress};
}

// Percentage positions match the grid columns and equally sized rows in video.css.
export function flowPoints(layout, count) {
  if (layout === 'branch') return [];
  return Array.from({length: count}, (_, index) => {
    const center = 100 * (index + .5) / count;
    if (layout === 'route') return {x: center, y: 50};
    return {x: layout === 'stack' ? 4 : index % 2 ? 57 : 43, y: center};
  });
}
