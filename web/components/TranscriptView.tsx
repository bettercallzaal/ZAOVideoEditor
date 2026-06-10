"use client";

import type { Cut, Segment } from "@/lib/types";

interface Props {
  segments: Segment[];
  cuts: Cut[];
  currentTime: number;
  onSeek: (t: number) => void;
}

function isCut(t: number, cuts: Cut[]): boolean {
  return cuts.some((c) => c.enabled && t >= c.start && t < c.end);
}

export default function TranscriptView({ segments, cuts, currentTime, onSeek }: Props) {
  return (
    <div className="max-h-[28rem] space-y-3 overflow-y-auto pr-2 text-sm leading-relaxed">
      {segments.map((seg) => {
        const active = currentTime >= seg.start && currentTime < seg.end;
        return (
          <p key={seg.id} className={active ? "rounded bg-white/5 p-1" : "p-1"}>
            {seg.speaker && <span className="mr-1 font-semibold text-cyan-300">{seg.speaker}:</span>}
            {seg.words && seg.words.length > 0 ? (
              seg.words.map((w, i) => {
                const cut = isCut((w.start + w.end) / 2, cuts);
                const here = currentTime >= w.start && currentTime < w.end;
                return (
                  <span key={i}
                    onClick={() => onSeek(w.start)}
                    className={`cursor-pointer ${cut ? "text-white/25 line-through" : ""} ${
                      here ? "rounded bg-orange-500/30" : ""
                    }`}>
                    {w.word}{" "}
                  </span>
                );
              })
            ) : (
              <span onClick={() => onSeek(seg.start)} className="cursor-pointer">{seg.text}</span>
            )}
          </p>
        );
      })}
    </div>
  );
}
