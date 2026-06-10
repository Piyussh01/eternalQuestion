import { NextRequest, NextResponse } from "next/server";
import { getCandidatesOnly } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const limit = Number(request.nextUrl.searchParams.get("limit") ?? 100);
  return NextResponse.json(getCandidatesOnly(Math.min(Math.max(limit, 1), 500)), {
    headers: {
      "Cache-Control": "no-store"
    }
  });
}
