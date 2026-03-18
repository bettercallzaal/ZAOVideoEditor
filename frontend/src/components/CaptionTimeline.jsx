import { useRef, useState, useCallback, useEffect } from 'react';
import { formatTime } from '../utils/format';

/**
 * Horizontal timeline showing caption blocks.
 * - Click to select a caption + seek video
 * - Drag left/right edges to adjust start/end timing
 * - Playhead indicator shows current time
 */

export default function CaptionTimeline({
  captions,
  duration,
  currentTime,
  selectedId,
  onSelect,
  onSeek,
  onTimingChange,
}) {
  const containerRef = useRef(null);
  const [dragging, setDragging] = useState(null); // { captionId, edge: 'start'|'end'|'move', origTime, mouseX }
  const [zoom, setZoom] = useState(1); // pixels per second
  const [scrollLeft, setScrollLeft] = useState(0);

  const effectiveDuration = Math.max(duration, 10);

  // Auto-compute zoom to fit container or use manual zoom
  const containerWidth = containerRef.current?.clientWidth || 800;
  const pxPerSec = Math.max(containerWidth / effectiveDuration, 5) * zoom;
  const timelineWidth = effectiveDuration * pxPerSec;

  const timeToPx = (t) => t * pxPerSec;
  const pxToTime = (px) => px / pxPerSec;

  const handleTimelineClick = (e) => {
    if (dragging) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left + containerRef.current.scrollLeft;
    const time = pxToTime(x);
    onSeek(Math.max(0, Math.min(effectiveDuration, time)));
  };

  const handleEdgeDrag = useCallback((captionId, edge, e) => {
    e.stopPropagation();
    e.preventDefault();
    const cap = captions.find(c => c.id === captionId);
    if (!cap) return;
    setDragging({
      captionId,
      edge,
      origStart: cap.start,
      origEnd: cap.end,
      mouseX: e.clientX,
    });
  }, [captions]);

  useEffect(() => {
    if (!dragging) return;
    const handleMove = (e) => {
      const dx = e.clientX - dragging.mouseX;
      const dt = pxToTime(dx);
      const cap = captions.find(c => c.id === dragging.captionId);
      if (!cap) return;

      let newStart = cap.start;
      let newEnd = cap.end;

      if (dragging.edge === 'start') {
        newStart = Math.max(0, Math.min(dragging.origEnd - 0.1, dragging.origStart + dt));
      } else if (dragging.edge === 'end') {
        newEnd = Math.max(dragging.origStart + 0.1, Math.min(effectiveDuration, dragging.origEnd + dt));
      } else if (dragging.edge === 'move') {
        const dur = dragging.origEnd - dragging.origStart;
        newStart = Math.max(0, Math.min(effectiveDuration - dur, dragging.origStart + dt));
        newEnd = newStart + dur;
      }

      onTimingChange(dragging.captionId, newStart, newEnd);
    };
    const handleUp = () => setDragging(null);
    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
    return () => {
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
    };
  }, [dragging, captions, effectiveDuration, onTimingChange, pxPerSec]);

  // Auto-scroll to keep playhead visible
  useEffect(() => {
    if (!containerRef.current) return;
    const playheadX = timeToPx(currentTime);
    const el = containerRef.current;
    const viewLeft = el.scrollLeft;
    const viewRight = viewLeft + el.clientWidth;
    if (playheadX < viewLeft + 50 || playheadX > viewRight - 50) {
      el.scrollLeft = playheadX - el.clientWidth / 2;
    }
  }, [currentTime, pxPerSec]);

  return (
    <div className="space-y-1">
      {/* Zoom controls */}
      <div className="flex items-center gap-2 px-1">
        <span className="text-[10px] text-gray-500">Zoom:</span>
        <input
          type="range"
          min="0.5"
          max="8"
          step="0.25"
          value={zoom}
          onChange={(e) => setZoom(parseFloat(e.target.value))}
          className="w-20 h-1 accent-[#e0ddaa]"
        />
        <span className="text-[10px] text-gray-500 font-mono">{formatTime(currentTime)}</span>
      </div>

      {/* Timeline */}
      <div
        ref={containerRef}
        className="relative overflow-x-auto bg-[#0a0e12] border border-gray-800 rounded h-20 cursor-crosshair"
        onClick={handleTimelineClick}
        onScroll={(e) => setScrollLeft(e.target.scrollLeft)}
      >
        <div style={{ width: timelineWidth, height: '100%', position: 'relative' }}>
          {/* Time markers */}
          {Array.from({ length: Math.ceil(effectiveDuration / 5) + 1 }, (_, i) => {
            const t = i * 5;
            return (
              <div
                key={`marker-${t}`}
                className="absolute top-0 text-[9px] text-gray-600 border-l border-gray-800"
                style={{ left: timeToPx(t), height: '100%' }}
              >
                <span className="ml-1">{formatTime(t)}</span>
              </div>
            );
          })}

          {/* Caption blocks */}
          {captions.map((cap) => {
            const left = timeToPx(cap.start);
            const width = Math.max(timeToPx(cap.end - cap.start), 4);
            const isSelected = cap.id === selectedId;

            return (
              <div
                key={cap.id}
                className={`absolute rounded group ${
                  isSelected
                    ? 'bg-[#e0ddaa]/30 border border-[#e0ddaa]'
                    : 'bg-blue-900/40 border border-blue-700/50 hover:border-blue-500'
                }`}
                style={{
                  left,
                  width,
                  top: 20,
                  height: 40,
                }}
                onClick={(e) => {
                  e.stopPropagation();
                  onSelect(cap.id);
                  onSeek(cap.start);
                }}
              >
                {/* Left edge handle */}
                <div
                  className="absolute left-0 top-0 bottom-0 w-2 cursor-col-resize hover:bg-[#e0ddaa]/40 rounded-l"
                  onMouseDown={(e) => handleEdgeDrag(cap.id, 'start', e)}
                />
                {/* Right edge handle */}
                <div
                  className="absolute right-0 top-0 bottom-0 w-2 cursor-col-resize hover:bg-[#e0ddaa]/40 rounded-r"
                  onMouseDown={(e) => handleEdgeDrag(cap.id, 'end', e)}
                />
                {/* Move handle (center) */}
                <div
                  className="absolute left-2 right-2 top-0 bottom-0 cursor-grab active:cursor-grabbing overflow-hidden"
                  onMouseDown={(e) => handleEdgeDrag(cap.id, 'move', e)}
                >
                  <span className="text-[10px] text-gray-300 whitespace-nowrap px-1 leading-[40px]">
                    {cap.text.length > 30 ? cap.text.slice(0, 30) + '...' : cap.text}
                  </span>
                </div>
              </div>
            );
          })}

          {/* Playhead */}
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-[#e0ddaa] z-10 pointer-events-none"
            style={{ left: timeToPx(currentTime) }}
          >
            <div className="w-2.5 h-2.5 bg-[#e0ddaa] rounded-full -ml-1" />
          </div>
        </div>
      </div>
    </div>
  );
}
