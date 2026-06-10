import { NextRequest, NextResponse } from "next/server";
import { getEvaluationsOnly } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const limit = Number(request.nextUrl.searchParams.get("limit") ?? 50);
  return NextResponse.json(getEvaluationsOnly(Math.min(Math.max(limit, 1), 300)), {
    headers: {
      "Cache-Control": "no-store"
    }
  });
}
