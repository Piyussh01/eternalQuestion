import { NextResponse } from "next/server";
import fs from "node:fs";
import { DB_PATH } from "@/lib/db";
import { hasSupabaseConfig } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export async function GET() {
  if (hasSupabaseConfig()) {
    return NextResponse.json(
      {
        ok: true,
        dbPath: "supabase",
        dbExists: true,
        generatedAt: new Date().toISOString()
      },
      {
        headers: {
          "Cache-Control": "no-store"
        }
      }
    );
  }

  return NextResponse.json(
    {
      ok: true,
      dbPath: DB_PATH,
      dbExists: fs.existsSync(DB_PATH),
      generatedAt: new Date().toISOString()
    },
    {
      headers: {
        "Cache-Control": "no-store"
      }
    }
  );
}
