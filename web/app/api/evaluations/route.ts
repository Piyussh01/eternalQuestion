import { NextRequest, NextResponse } from "next/server";
import { getEvaluationsOnly } from "@/lib/db";
import { getSupabaseEvaluationsOnly, hasSupabaseConfig } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const limit = Number(request.nextUrl.searchParams.get("limit") ?? 50);
  const clampedLimit = Math.min(Math.max(limit, 1), 300);
  const data = hasSupabaseConfig()
    ? await getSupabaseEvaluationsOnly(clampedLimit)
    : getEvaluationsOnly(clampedLimit);
  return NextResponse.json(data, {
    headers: {
      "Cache-Control": "no-store"
    }
  });
}
