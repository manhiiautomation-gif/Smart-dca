import { NextResponse } from "next/server";
import { getBriefingData } from "@/lib/btc-data";

export const dynamic = "force-dynamic";
export const revalidate = 300; // 5 min cache

export async function GET() {
  try {
    const data = getBriefingData();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to load briefing data", details: String(error) },
      { status: 500 }
    );
  }
}
