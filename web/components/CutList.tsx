"use client";

import type { Cut } from "@/lib/types";

const TYPE_LABEL: Record<string, string> = {
  filler: "FILLER",
  gap: "GAP",
  falsestart: "FALSE START",
  bleed: "BLEED",
};

function fmt(t: number): string {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

interface Props {
  cuts: Cut[];
  onToggle: (id: string, enabled: boolean) => void;
  onSeek: (t: number) => void;
  onBatch: (enabled: boolean, filter?: (c: Cut) => boolean) => void;
}

export default function CutList({ cuts, onToggle, onSeek, onBatch }: Props) {
  const enabledCount = cuts.filter((c) => c.enabled).length;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-white/50">
          {cuts.length} cuts, {enabledCount} on
        </span>
        <button className="rounded border border-white/15 px-2 py-1 hover:border-white/40"
          onClick={() => onBatch(true)}>Accept all</button>
        <button className="rounded border border-white/15 px-2 py-1 hover:border-white/40"
          onClick={() => onBatch(false)}>Reject all</button>
        <button className="rounded border border-white/15 px-2 py-1 hover:border-white/40"
          onClick={() => onBatch(true, (c) => c.type === "filler")}>um/uh only</button>
        <button className="rounded border border-white/15 px-2 py-1 hover:border-white/40"
          onClick={() => onBatch(true, (c) => c.type === "filler" || c.type === "gap")}>fillers + gaps</button>
      </div>

      <ul className="max-h-[28rem] space-y-1 overflow-y-auto pr-1">
        {cuts.map((c) => (
          <li key={c.id}
            className={`flex items-center gap-2 rounded border px-2 py-1 text-sm ${
              c.enabled ? "border-orange-500/40 bg-orange-500/5" : "border-white/10"
            }`}>
            <input type="checkbox" checked={c.enabled}
              onChange={(e) => onToggle(c.id, e.target.checked)} />
            <button className="font-mono text-xs text-cyan-300 hover:underline"
              onClick={() => onSeek(c.start)}>{fmt(c.start)}</button>
            <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-white/60">
              {TYPE_LABEL[c.type] || c.type}
            </span>
            <span className="truncate text-white/70">{c.text}</span>
            {c.source === "llm" && (
              <span className="ml-auto text-[10px] text-amber-400">AI suggested</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
