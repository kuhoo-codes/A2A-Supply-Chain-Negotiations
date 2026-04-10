export type SimulationRunRequest = {
  title: string;
  product_name: string;
  product_category: string;
  market_region: string;
  baseline_unit_price: number;
  target_quantity: number;
  currency: string;
  demand_signal: string;
  supply_signal: string;
  max_rounds_per_negotiation: number;
  supplier_min_sell_price: number;
  manufacturer_max_buy_price: number;
  manufacturer_min_sell_price: number;
  retailer_max_buy_price: number;
  manufacturer_margin_floor: number;
};
