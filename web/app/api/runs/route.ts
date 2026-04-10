import { NextResponse } from "next/server";

import { getApiBaseUrl } from "../../../lib/api";
import { RunSummary } from "../../../lib/api-types";


export async function GET() {
  try {
    const response = await fetch(`${getApiBaseUrl()}/runs`, {
      cache: "no-store",
    });

    if (!response.ok) {
      const errorPayload = (await response.json().catch(() => null)) as
        | { detail?: string }
        | null;
      return NextResponse.json(
        {
          data: null,
          error:
            errorPayload?.detail ??
            `Backend request failed with status ${response.status}.`,
        },
        { status: response.status },
      );
    }

    const data = (await response.json()) as RunSummary[];
    return NextResponse.json({ data, error: null });
  } catch {
    return NextResponse.json(
      {
        data: null,
        error: "Unable to reach the backend runs endpoint.",
      },
      { status: 503 },
    );
  }
}
