import { NextResponse } from "next/server";
import fs from "node:fs";
import { DB_PATH } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
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
