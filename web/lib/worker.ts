import type { EditSheet } from "./types";

// The Python media worker (FastAPI engine on the VPS). The review UI calls it
// for transcription, rendering, and to serve video. State lives in Supabase;
// heavy media work lives here.
const WORKER = process.env.NEXT_PUBLIC_WORKER_URL || "http://localhost:8000";

export function workerUrl(path: string): string {
  return `${WORKER}${path}`;
}

export function serveVideoUrl(projectName: string, subpath: string): string {
  return workerUrl(`/api/serve-video/${encodeURIComponent(projectName)}/${subpath}`);
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(workerUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === "string" ? err.detail : "Worker request failed");
  }
  return res.json() as Promise<T>;
}

export interface Task {
  task_id: string;
  status: "pending" | "running" | "complete" | "error";
  progress: number;
  message: string;
  result?: unknown;
  error?: string;
}

export function getTask(taskId: string): Promise<Task> {
  return fetch(workerUrl(`/api/tasks/${taskId}`)).then((r) => r.json());
}

export async function pollTask(
  taskId: string,
  onProgress?: (t: Task) => void,
  intervalMs = 1200,
): Promise<Task> {
  for (;;) {
    const t = await getTask(taskId);
    onProgress?.(t);
    if (t.status === "complete") return t;
    if (t.status === "error") throw new Error(t.error || "Task failed");
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

export function startProcess(projectName: string, title: string): Promise<Task> {
  return post("/api/recordings/process", { project_name: projectName, title });
}

export function startRender(projectName: string, editSheet: EditSheet): Promise<Task> {
  return post("/api/recordings/render", { project_name: projectName, edit_sheet: editSheet });
}
