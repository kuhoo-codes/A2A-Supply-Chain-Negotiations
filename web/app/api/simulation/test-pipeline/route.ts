import { NextResponse } from "next/server";

import { getApiBaseUrl } from "../../../../lib/api";
import { SimulationTestPipelineResult } from "../../../../lib/api-types";


export async function POST(request: Request) {
  try {
    const body = await request.json().catch(() => ({ seed: 42 }));
    const response = await fetch(`${getApiBaseUrl()}/simulation/test-pipeline`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      cache: "no-store",
    });

    if (!response.ok) {
      return NextResponse.json(
        {
          data: null,
          error: `Backend request failed with status ${response.status}.`,
        },
        { status: response.status },
      );
    }

    const data = (await response.json()) as SimulationTestPipelineResult;
    return NextResponse.json({ data, error: null });
  } catch {
    return NextResponse.json(
      {
        data: null,
        error: "Unable to reach the backend pipeline endpoint.",
      },
      { status: 503 },
    );
  }
}
