"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { supabase, supabaseConfigured } from "@/lib/supabase";
import type { Project } from "@/lib/types";

export default function Home() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!supabaseConfigured) {
      setError("Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.");
      return;
    }
    supabase
      .from("projects")
      .select("*")
      .order("created_at", { ascending: false })
      .then(({ data, error }) => {
        if (error) setError(error.message);
        else setProjects((data as Project[]) || []);
      });
  }, []);

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Recordings</h2>
      {error && <p className="text-sm text-amber-400">{error}</p>}
      {projects.length === 0 && !error && (
        <p className="text-sm text-white/50">No recordings yet.</p>
      )}
      <ul className="space-y-2">
        {projects.map((p) => (
          <li key={p.id} className="rounded-lg border border-white/10 p-3">
            <Link href={`/recordings/${p.id}`} className="flex items-center justify-between">
              <span>{p.title || "(untitled)"}</span>
              <span className="text-xs text-white/40">{p.status}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
