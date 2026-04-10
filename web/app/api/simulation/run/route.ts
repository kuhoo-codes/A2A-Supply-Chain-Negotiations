import { NextResponse } from "next/server";

import { getApiBaseUrl } from "../../../../lib/api";
import { RunRecord } from "../../../../lib/api-types";
import { SimulationRunRequest } from "../../../../lib/simulation-types";


export async function POST(request: Request) {
  try {
    const body = (await request.json()) as SimulationRunRequest;
    const response = await fetch(`${getApiBaseUrl()}/simulation/run`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
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

    const data = (await response.json()) as RunRecord;
    return NextResponse.json({ data, error: null });
  } catch {
    return NextResponse.json(
      {
        data: null,
        error: "Unable to reach the backend simulation endpoint.",
      },
      { status: 503 },
    );
  }
}
