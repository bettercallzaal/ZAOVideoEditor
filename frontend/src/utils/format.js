/**
 * Format seconds to M:SS or M:SS.t display.
 * @param {number} seconds
 * @param {boolean} showTenths - include tenths of a second
 */
export function formatTime(seconds, showTenths = false) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  const base = `${m}:${s.toString().padStart(2, '0')}`;
  if (!showTenths) return base;
  const t = Math.floor((seconds % 1) * 10);
  return `${base}.${t}`;
}
