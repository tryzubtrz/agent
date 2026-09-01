import { NextResponse } from "next/server";
import packageJson from "../../../../package.json";

export function GET() {
  return NextResponse.json(
    {
      service: "alter-cockpit",
      status: "ok",
      version: packageJson.version
    },
    {
      headers: {
        "Cache-Control": "no-store"
      }
    }
  );
}
