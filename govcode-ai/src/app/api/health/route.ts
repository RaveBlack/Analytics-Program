import { NextResponse } from "next/server";

export function GET() {
  return NextResponse.json(
    {
      ok: true,
      service: "govcode-ai",
      ts: Date.now(),
    },
    { status: 200 },
  );
}

