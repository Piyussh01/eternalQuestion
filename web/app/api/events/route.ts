import { NextRequest, NextResponse } from "next/server";
import { getHistoryOnly } from "@/lib/db";
import { getSupabaseHistoryOnly, hasSupabaseConfig } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const limit = Number(request.nextUrl.searchParams.get("limit") ?? 100);
  const clampedLimit = Math.min(Math.max(limit, 1), 500);
  const data = hasSupabaseConfig()
    ? await getSupabaseHistoryOnly(clampedLimit)
    : getHistoryOnly(clampedLimit);
  return NextResponse.json(data, {
    headers: {
      "Cache-Control": "no-store"
    }
  });
}
