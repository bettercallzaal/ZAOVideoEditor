import { createClient } from "@supabase/supabase-js";

// Browser client. Reads public env vars; both must be set for the app to talk
// to Supabase. See web/.env.example.
const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export const supabaseConfigured = Boolean(url && anonKey);

export const supabase = createClient(
  url || "http://localhost:54321",
  anonKey || "public-anon-key-placeholder",
);
