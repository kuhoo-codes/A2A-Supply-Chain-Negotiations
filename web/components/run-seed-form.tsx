"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import {
  SimulationBatchLaunchResult,
  SimulationRunConfig,
} from "../lib/api-types";


type RunSeedFormProps = {
  mode?: "refresh" | "redirect" | "inline";
  onLaunched?: (payload: SimulationBatchLaunchResult) => void;
};

type CustomSeedFormState = {
  title: string;
  market_region: string;
  baseline_unit_price: string;
  target_quantity: string;
  demand_signal: string;
  supply_signal: string;
  max_rounds_per_negotiation: string;
  supplier_min_sell_price: string;
  manufacturer_max_buy_price: string;
  manufacturer_min_sell_price: string;
  retailer_max_buy_price: string;
  manufacturer_margin_floor: string;
};

const DEFAULT_CUSTOM_SEED: CustomSeedFormState = {
  title: "Custom Tomato Negotiation",
  market_region: "California",
  baseline_unit_price: "2.75",
  target_quantity: "1000",
  demand_signal: "Retail buyers want stable ketchup pricing for the next buying cycle.",
  supply_signal: "Tomato paste supply is available, but sellers are watching input costs closely.",
  max_rounds_per_negotiation: "15",
  supplier_min_sell_price: "2.35",
  manufacturer_max_buy_price: "2.95",
  manufacturer_min_sell_price: "3.25",
  retailer_max_buy_price: "3.85",
  manufacturer_margin_floor: "0.30",
};

const NUMBER_FIELDS: Array<keyof CustomSeedFormState> = [
  "baseline_unit_price",
  "target_quantity",
  "max_rounds_per_negotiation",
  "supplier_min_sell_price",
  "manufacturer_max_buy_price",
  "manufacturer_min_sell_price",
  "retailer_max_buy_price",
  "manufacturer_margin_floor",
];


export function RunSeedForm({
  mode = "refresh",
  onLaunched,
}: RunSeedFormProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [seed, setSeed] = useState("");
  const [launchMode, setLaunchMode] = useState<"preset" | "custom">("preset");
  const [customSeed, setCustomSeed] = useState<CustomSeedFormState>(DEFAULT_CUSTOM_SEED);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSuccess(null);

    const request =
      launchMode === "custom"
        ? buildCustomSeedRequest(customSeed)
        : { endpoint: "/api/simulation/run", body: { seed: Number(seed) } };

    if (!request) {
      setError("Check the custom seed values and try again.");
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await fetch(request.endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(request.body),
      });

      const payload = (await response.json()) as {
        data: SimulationBatchLaunchResult | null;
        error: string | null;
      };

      if (!response.ok || !payload.data) {
        console.error("Simulation failed:", payload.error ?? "Unknown simulation error");
        setError(payload.error ?? "Simulation could not be completed.");
        setIsSubmitting(false);
        return;
      }

      setSuccess(`${payload.data.count} simulation${payload.data.count === 1 ? "" : "s"} launched.`);
      setIsSubmitting(false);
      navigateAfterLaunch(payload.data);
    } catch {
      console.error("Simulation request failed");
      setError("Unable to reach the simulation service.");
      setIsSubmitting(false);
    }
  }

  function navigateAfterLaunch(launchData: SimulationBatchLaunchResult) {
    const launchedRunIds = launchData.runs.map((run) => run.id).filter(Boolean);
    const runsPath =
      launchedRunIds.length > 0
        ? `/runs?ids=${launchedRunIds.join(",")}&selected=${launchedRunIds[0]}`
        : "/runs";
    startTransition(() => {
      if (mode === "inline") {
        onLaunched?.(launchData);
        return;
      }

      if (mode === "redirect") {
        router.push(runsPath);
        return;
      }

      router.refresh();
    });
  }

  function updateCustomSeed(field: keyof CustomSeedFormState, value: string) {
    setCustomSeed((current) => ({ ...current, [field]: value }));
  }

  const isBusy = isSubmitting || isPending;
  const canSubmit =
    launchMode === "custom"
      ? hasCompleteCustomSeed(customSeed)
      : seed.trim().length > 0;

  return (
    <form className="seed-form" onSubmit={handleSubmit}>
      <div className="seed-mode-actions" aria-label="Simulation setup options">
        <button
          className={`button ${launchMode === "preset" ? "primary" : "secondary"}`}
          onClick={() => setLaunchMode("preset")}
          type="button"
        >
          Use Preset Seed
        </button>
        <button
          className={`button ${launchMode === "custom" ? "primary" : "secondary"}`}
          onClick={() => setLaunchMode("custom")}
          type="button"
        >
          Configure Your Own Seed
        </button>
      </div>

      {launchMode === "preset" ? (
        <div className="seed-form-row">
          <label className="field">
            <span>Seed Number</span>
            <input
              inputMode="numeric"
              onChange={(event) => setSeed(event.target.value)}
              placeholder="e.g. 42"
              value={seed}
            />
          </label>
          <button
            className="button primary"
            disabled={isBusy || !canSubmit}
            type="submit"
          >
            {isBusy ? "Launching Simulations..." : "Run Simulation"}
          </button>
        </div>
      ) : (
        <div className="custom-seed-panel">
          <div className="custom-seed-grid">
            <label className="field wide">
              <span>Run Name</span>
              <input
                onChange={(event) => updateCustomSeed("title", event.target.value)}
                value={customSeed.title}
              />
            </label>
            <label className="field">
              <span>Location</span>
              <input
                onChange={(event) => updateCustomSeed("market_region", event.target.value)}
                value={customSeed.market_region}
              />
            </label>
            <label className="field">
              <span>Target Quantity</span>
              <input
                inputMode="numeric"
                onChange={(event) => updateCustomSeed("target_quantity", event.target.value)}
                value={customSeed.target_quantity}
              />
            </label>
            <label className="field">
              <span>Market Price</span>
              <input
                inputMode="decimal"
                onChange={(event) => updateCustomSeed("baseline_unit_price", event.target.value)}
                value={customSeed.baseline_unit_price}
              />
            </label>
            <label className="field">
              <span>Max Rounds</span>
              <input
                inputMode="numeric"
                max="15"
                min="1"
                onChange={(event) => updateCustomSeed("max_rounds_per_negotiation", event.target.value)}
                value={customSeed.max_rounds_per_negotiation}
              />
            </label>
            <label className="field">
              <span>Supplier Floor</span>
              <input
                inputMode="decimal"
                onChange={(event) => updateCustomSeed("supplier_min_sell_price", event.target.value)}
                value={customSeed.supplier_min_sell_price}
              />
            </label>
            <label className="field">
              <span>Manufacturer Buy Limit</span>
              <input
                inputMode="decimal"
                onChange={(event) => updateCustomSeed("manufacturer_max_buy_price", event.target.value)}
                value={customSeed.manufacturer_max_buy_price}
              />
            </label>
            <label className="field">
              <span>Manufacturer Sell Floor</span>
              <input
                inputMode="decimal"
                onChange={(event) => updateCustomSeed("manufacturer_min_sell_price", event.target.value)}
                value={customSeed.manufacturer_min_sell_price}
              />
            </label>
            <label className="field">
              <span>Retailer Buy Limit</span>
              <input
                inputMode="decimal"
                onChange={(event) => updateCustomSeed("retailer_max_buy_price", event.target.value)}
                value={customSeed.retailer_max_buy_price}
              />
            </label>
            <label className="field">
              <span>Margin Goal</span>
              <input
                inputMode="decimal"
                onChange={(event) => updateCustomSeed("manufacturer_margin_floor", event.target.value)}
                value={customSeed.manufacturer_margin_floor}
              />
            </label>
            <label className="field wide">
              <span>Buyer Need</span>
              <textarea
                onChange={(event) => updateCustomSeed("demand_signal", event.target.value)}
                value={customSeed.demand_signal}
              />
            </label>
            <label className="field wide">
              <span>Seller Pressure</span>
              <textarea
                onChange={(event) => updateCustomSeed("supply_signal", event.target.value)}
                value={customSeed.supply_signal}
              />
            </label>
          </div>
          <button
            className="button primary custom-launch-button"
            disabled={isBusy || !canSubmit}
            type="submit"
          >
            {isBusy ? "Launching Simulation..." : "Run Custom Simulation"}
          </button>
        </div>
      )}

      {isBusy ? (
        <div className="progress-shell" aria-live="polite">
          <div className="progress-bar" />
        </div>
      ) : null}

      {error ? (
        <p className="inline-error">{error}</p>
      ) : null}
      {success ? <p className="inline-success">{success}</p> : null}
    </form>
  );
}

function buildCustomSeedRequest(customSeed: CustomSeedFormState):
  | { endpoint: string; body: SimulationRunConfig }
  | null {
  const parsed = Object.fromEntries(
    NUMBER_FIELDS.map((field) => [field, Number(customSeed[field])]),
  ) as Record<keyof CustomSeedFormState, number>;

  const hasInvalidNumber = NUMBER_FIELDS.some((field) => !Number.isFinite(parsed[field]));
  if (hasInvalidNumber) {
    return null;
  }

  const maxRounds = Math.min(Math.max(Math.round(parsed.max_rounds_per_negotiation), 1), 15);

  return {
    endpoint: "/api/simulation/run/custom",
    body: {
      title: customSeed.title.trim(),
      product_name: "Tomato Ketchup",
      product_category: "condiments",
      market_region: customSeed.market_region.trim(),
      baseline_unit_price: parsed.baseline_unit_price,
      target_quantity: Math.max(Math.round(parsed.target_quantity), 1),
      currency: "USD",
      demand_signal: customSeed.demand_signal.trim(),
      supply_signal: customSeed.supply_signal.trim(),
      max_rounds_per_negotiation: maxRounds,
      supplier_min_sell_price: parsed.supplier_min_sell_price,
      manufacturer_max_buy_price: parsed.manufacturer_max_buy_price,
      manufacturer_min_sell_price: parsed.manufacturer_min_sell_price,
      retailer_max_buy_price: parsed.retailer_max_buy_price,
      manufacturer_margin_floor: parsed.manufacturer_margin_floor,
    },
  };
}

function hasCompleteCustomSeed(customSeed: CustomSeedFormState): boolean {
  const hasText =
    customSeed.title.trim().length > 0 &&
    customSeed.market_region.trim().length > 0 &&
    customSeed.demand_signal.trim().length > 0 &&
    customSeed.supply_signal.trim().length > 0;
  const hasNumbers = NUMBER_FIELDS.every((field) => {
    const value = Number(customSeed[field]);
    return Number.isFinite(value) && (field === "manufacturer_margin_floor" ? value >= 0 : value > 0);
  });

  return hasText && hasNumbers;
}
