import { SimulationRunRequest } from "./simulation-types";


export const emptySimulationRunRequest: SimulationRunRequest = {
  title: "",
  product_name: "",
  product_category: "",
  market_region: "",
  baseline_unit_price: 0,
  target_quantity: 0,
  currency: "",
  demand_signal: "",
  supply_signal: "",
  max_rounds_per_negotiation: 0,
  supplier_min_sell_price: 0,
  manufacturer_max_buy_price: 0,
  manufacturer_min_sell_price: 0,
  retailer_max_buy_price: 0,
  manufacturer_margin_floor: 0,
};
