export type CutType = "filler" | "gap" | "falsestart" | "bleed";
export type CutSource = "auto" | "llm" | "human";

export interface Cut {
  id: string;
  start: number;
  end: number;
  type: CutType;
  source: CutSource;
  enabled: boolean;
  text?: string;
}

export interface EditSheet {
  duration: number;
  cuts: Cut[];
}

export interface Word {
  word: string;
  start: number;
  end: number;
}

export interface Segment {
  id: number;
  start: number;
  end: number;
  text: string;
  speaker?: string;
  words?: Word[];
}

export interface Project {
  id: string;
  owner: string;
  title: string;
  source: string | null;
  status: string;
  duration: number;
  created_at: string;
}
