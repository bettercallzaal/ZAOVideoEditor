"use client";

import { useEffect, useRef, useState } from "react";
import { supabase, supabaseConfigured } from "@/lib/supabase";
import { serveVideoUrl, startRender, pollTask } from "@/lib/worker";
import type { Cut, EditSheet, Project, Segment } from "@/lib/types";
import TranscriptView from "./TranscriptView";
import CutList from "./CutList";

function slug(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "untitled";
}

export default function ReviewEditor({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<Project | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [cuts, setCuts] = useState<Cut[]>([]);
  const [currentTime, setCurrentTime] = useState(0);
  const [status, setStatus] = useState("");
  const [rendered, setRendered] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  const workerName = project ? slug(project.title) : "";

  useEffect(() => {
    if (!supabaseConfigured) {
      setStatus("Supabase not configured - set env vars to load this recording.");
      return;
    }
    (async () => {
      const { data: proj } = await supabase.from("projects").select("*").eq("id", projectId).single();
      setProject((proj as Project) || null);

      const { data: tr } = await supabase
        .from("transcripts").select("data").eq("project_id", projectId).eq("kind", "corrected").single();
      const d = tr?.data as { segments?: Segment[] } | undefined;
      setSegments(d?.segments || []);

      const { data: cutRows } = await supabase.from("cuts").select("*").eq("project_id", projectId);
      setCuts(
        ((cutRows as Array<Record<string, unknown>>) || []).map((r) => ({
          id: String(r.id),
          start: Number(r.start_s),
          end: Number(r.end_s),
          type: r.type as Cut["type"],
          source: r.source as Cut["source"],
          enabled: Boolean(r.enabled),
          text: (r.label as string) || "",
        })),
      );
    })();
  }, [projectId]);

  function seek(t: number) {
    if (videoRef.current) videoRef.current.currentTime = t;
  }

  async function toggle(id: string, enabled: boolean) {
    setCuts((prev) => prev.map((c) => (c.id === id ? { ...c, enabled } : c)));
    if (supabaseConfigured) await supabase.from("cuts").update({ enabled }).eq("id", id);
  }

  async function batch(enabled: boolean, filter?: (c: Cut) => boolean) {
    const affected = cuts.filter((c) => (filter ? filter(c) : true));
    setCuts((prev) =>
      prev.map((c) => (!filter || filter(c) ? { ...c, enabled } : c)),
    );
    if (supabaseConfigured) {
      await Promise.all(
        affected.map((c) => supabase.from("cuts").update({ enabled }).eq("id", c.id)),
      );
    }
  }

  async function render() {
    if (!project) return;
    setStatus("Rendering trimmed master...");
    setRendered(false);
    const sheet: EditSheet = { duration: project.duration, cuts };
    try {
      const task = await startRender(workerName, sheet);
      await pollTask(task.task_id, (t) => setStatus(t.message || "Rendering..."));
      setStatus("Render complete");
      setRendered(true);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Render failed");
    }
  }

  if (!project) {
    return <p className="text-sm text-white/50">{status || "Loading..."}</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">{project.title}</h2>
        <button onClick={render}
          className="rounded bg-orange-500 px-4 py-1.5 text-sm font-semibold text-black hover:opacity-90">
          Render trimmed master
        </button>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <video ref={videoRef} controls className="w-full rounded border border-white/10"
            src={serveVideoUrl(workerName, rendered ? "processing/trimmed.mp4" : "input/main.mp4")}
            onTimeUpdate={(e) => setCurrentTime((e.target as HTMLVideoElement).currentTime)} />
          {status && <p className="text-xs text-white/50">{status}</p>}
          <CutList cuts={cuts} onToggle={toggle} onSeek={seek} onBatch={batch} />
        </div>
        <TranscriptView segments={segments} cuts={cuts} currentTime={currentTime} onSeek={seek} />
      </div>
    </div>
  );
}
