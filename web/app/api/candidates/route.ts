import { NextRequest, NextResponse } from "next/server";
import { getCandidatesOnly } from "@/lib/db";
import { getSupabaseCandidatesOnly, hasSupabaseConfig } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const limit = Number(request.nextUrl.searchParams.get("limit") ?? 100);
  const clampedLimit = Math.min(Math.max(limit, 1), 500);
  const data = hasSupabaseConfig()
    ? await getSupabaseCandidatesOnly(clampedLimit)
    : getCandidatesOnly(clampedLimit);
  return NextResponse.json(data, {
    headers: {
      "Cache-Control": "no-store"
    }
  });
}
