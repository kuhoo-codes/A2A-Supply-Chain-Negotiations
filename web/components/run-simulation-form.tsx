"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { emptySimulationRunRequest } from "../lib/simulation-defaults";
import { SimulationRunRequest } from "../lib/simulation-types";


type RunSimulationFormProps = {
  mode?: "refresh" | "redirect";
};


export function RunSimulationForm({
  mode = "refresh",
}: RunSimulationFormProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<SimulationRunRequest>(emptySimulationRunRequest);

  function updateField<K extends keyof SimulationRunRequest>(
    key: K,
    value: SimulationRunRequest[K],
  ) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    try {
      const response = await fetch("/api/simulation/run", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(form),
      });

      const payload = (await response.json()) as {
        data: { id: string } | null;
        error: string | null;
      };

      if (!response.ok || !payload.data) {
        setError(payload.error ?? "Simulation failed.");
        return;
      }

      startTransition(() => {
        if (mode === "redirect") {
          router.push(`/runs/${payload.data?.id}`);
          return;
        }

        router.refresh();
      });
    } catch {
      setError("Unable to reach the simulation endpoint.");
    }
  }

  return (
    <form className="simulation-form" onSubmit={handleSubmit}>
      <div className="form-grid">
        <label className="field">
          <span>Title</span>
          <input
            onChange={(event) => updateField("title", event.target.value)}
            value={form.title}
          />
        </label>
        <label className="field">
          <span>Product</span>
          <input
            onChange={(event) => updateField("product_name", event.target.value)}
            value={form.product_name}
          />
        </label>
        <label className="field">
          <span>Category</span>
          <input
            onChange={(event) => updateField("product_category", event.target.value)}
            value={form.product_category}
          />
        </label>
        <label className="field">
          <span>Market</span>
          <input
            onChange={(event) => updateField("market_region", event.target.value)}
            value={form.market_region}
          />
        </label>
        <label className="field">
          <span>Baseline Price</span>
          <input
            min="0"
            onChange={(event) =>
              updateField("baseline_unit_price", Number(event.target.value))
            }
            type="number"
            value={form.baseline_unit_price || ""}
          />
        </label>
        <label className="field">
          <span>Quantity</span>
          <input
            min="1"
            onChange={(event) =>
              updateField("target_quantity", Number(event.target.value))
            }
            type="number"
            value={form.target_quantity || ""}
          />
        </label>
        <label className="field">
          <span>Currency</span>
          <input
            onChange={(event) => updateField("currency", event.target.value)}
            value={form.currency}
          />
        </label>
        <label className="field">
          <span>Max Rounds</span>
          <input
            max="20"
            min="1"
            onChange={(event) =>
              updateField("max_rounds_per_negotiation", Number(event.target.value))
            }
            type="number"
            value={form.max_rounds_per_negotiation}
          />
        </label>
        <label className="field">
          <span>Supplier Min Sell</span>
          <input
            min="0"
            onChange={(event) =>
              updateField("supplier_min_sell_price", Number(event.target.value))
            }
            type="number"
            value={form.supplier_min_sell_price || ""}
          />
        </label>
        <label className="field">
          <span>Manufacturer Max Buy</span>
          <input
            min="0"
            onChange={(event) =>
              updateField("manufacturer_max_buy_price", Number(event.target.value))
            }
            type="number"
            value={form.manufacturer_max_buy_price || ""}
          />
        </label>
        <label className="field">
          <span>Manufacturer Min Sell</span>
          <input
            min="0"
            onChange={(event) =>
              updateField("manufacturer_min_sell_price", Number(event.target.value))
            }
            type="number"
            value={form.manufacturer_min_sell_price || ""}
          />
        </label>
        <label className="field">
          <span>Retailer Max Buy</span>
          <input
            min="0"
            onChange={(event) =>
              updateField("retailer_max_buy_price", Number(event.target.value))
            }
            type="number"
            value={form.retailer_max_buy_price || ""}
          />
        </label>
        <label className="field">
          <span>Manufacturer Margin Floor</span>
          <input
            min="0"
            onChange={(event) =>
              updateField("manufacturer_margin_floor", Number(event.target.value))
            }
            type="number"
            value={form.manufacturer_margin_floor || ""}
          />
        </label>
        <label className="field field-wide">
          <span>Demand Signal</span>
          <textarea
            onChange={(event) => updateField("demand_signal", event.target.value)}
            value={form.demand_signal}
          />
        </label>
        <label className="field field-wide">
          <span>Supply Signal</span>
          <textarea
            onChange={(event) => updateField("supply_signal", event.target.value)}
            value={form.supply_signal}
          />
        </label>
      </div>

      <div className="page-actions">
        <button className="button primary" disabled={isPending} type="submit">
          {isPending ? "Running Simulation..." : "Run New Simulation"}
        </button>
      </div>

      {error ? <p className="inline-error">{error}</p> : null}
    </form>
  );
}
