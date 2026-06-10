import { NextResponse } from "next/server";
import { getDashboardData } from "@/lib/db";
import { getSupabaseDashboardData, hasSupabaseConfig } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export async function GET() {
  const data = hasSupabaseConfig() ? await getSupabaseDashboardData() : getDashboardData();
  return NextResponse.json(data, {
    headers: {
      "Cache-Control": "no-store"
    }
  });
}
