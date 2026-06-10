import { NextResponse } from "next/server";
import { getDashboardData } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json(getDashboardData(), {
    headers: {
      "Cache-Control": "no-store"
    }
  });
}
