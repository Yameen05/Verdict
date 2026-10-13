export interface StockOption {
  ticker: string;
  name: string;
  sector: string;
}

export const POPULAR_STOCKS: StockOption[] = [
  { ticker: "AAPL", name: "Apple", sector: "Technology" },
  { ticker: "MSFT", name: "Microsoft", sector: "Technology" },
  { ticker: "NVDA", name: "NVIDIA", sector: "Semiconductors" },
  { ticker: "AMD", name: "AMD", sector: "Semiconductors" },
  { ticker: "AVGO", name: "Broadcom", sector: "Semiconductors" },
  { ticker: "TSM", name: "TSMC", sector: "Semiconductors" },
  { ticker: "INTC", name: "Intel", sector: "Semiconductors" },
  { ticker: "SMCI", name: "Super Micro", sector: "Technology" },
  { ticker: "GOOGL", name: "Alphabet", sector: "Communication" },
  { ticker: "AMZN", name: "Amazon", sector: "Consumer" },
  { ticker: "META", name: "Meta Platforms", sector: "Communication" },
  { ticker: "TSLA", name: "Tesla", sector: "Auto" },
  { ticker: "ORCL", name: "Oracle", sector: "Technology" },
  { ticker: "CRM", name: "Salesforce", sector: "Technology" },
  { ticker: "ADBE", name: "Adobe", sector: "Technology" },
  { ticker: "UBER", name: "Uber", sector: "Technology" },
  { ticker: "ABNB", name: "Airbnb", sector: "Consumer" },
  { ticker: "SPOT", name: "Spotify", sector: "Communication" },
  { ticker: "PYPL", name: "PayPal", sector: "Financials" },
  { ticker: "HOOD", name: "Robinhood", sector: "Financials" },
  { ticker: "GME", name: "GameStop", sector: "Consumer" },
  { ticker: "RDDT", name: "Reddit", sector: "Communication" },
  { ticker: "LLY", name: "Eli Lilly", sector: "Healthcare" },
  { ticker: "BRK-B", name: "Berkshire Hathaway", sector: "Financials" },
  { ticker: "F", name: "Ford", sector: "Auto" },
  { ticker: "NFLX", name: "Netflix", sector: "Communication" },
  { ticker: "DIS", name: "Disney", sector: "Communication" },
  { ticker: "PLTR", name: "Palantir", sector: "Technology" },
  { ticker: "COIN", name: "Coinbase", sector: "Financials" },
  { ticker: "JPM", name: "JPMorgan Chase", sector: "Financials" },
  { ticker: "V", name: "Visa", sector: "Financials" },
  { ticker: "BAC", name: "Bank of America", sector: "Financials" },
  { ticker: "WMT", name: "Walmart", sector: "Consumer" },
  { ticker: "COST", name: "Costco", sector: "Consumer" },
  { ticker: "NKE", name: "Nike", sector: "Consumer" },
  { ticker: "SBUX", name: "Starbucks", sector: "Consumer" },
  { ticker: "KO", name: "Coca-Cola", sector: "Consumer" },
  { ticker: "MCD", name: "McDonald's", sector: "Consumer" },
  { ticker: "JNJ", name: "Johnson & Johnson", sector: "Healthcare" },
  { ticker: "UNH", name: "UnitedHealth", sector: "Healthcare" },
  { ticker: "PFE", name: "Pfizer", sector: "Healthcare" },
  { ticker: "XOM", name: "ExxonMobil", sector: "Energy" },
  { ticker: "CVX", name: "Chevron", sector: "Energy" },
  { ticker: "BA", name: "Boeing", sector: "Industrials" },
  // Crypto trades 24/7; SEC-filing and insider evidence don't apply to coins.
  { ticker: "BTC-USD", name: "Bitcoin", sector: "Crypto" },
  { ticker: "ETH-USD", name: "Ethereum", sector: "Crypto" },
  { ticker: "SOL-USD", name: "Solana", sector: "Crypto" },
  { ticker: "XRP-USD", name: "XRP", sector: "Crypto" },
  { ticker: "DOGE-USD", name: "Dogecoin", sector: "Crypto" },
  { ticker: "ADA-USD", name: "Cardano", sector: "Crypto" },
  { ticker: "AVAX-USD", name: "Avalanche", sector: "Crypto" },
  { ticker: "LINK-USD", name: "Chainlink", sector: "Crypto" },
];

const POPULAR_ETFS: StockOption[] = [
  { ticker: "SPY", name: "SPDR S&P 500 ETF", sector: "Broad market" },
  { ticker: "VOO", name: "Vanguard S&P 500 ETF", sector: "Broad market" },
  { ticker: "QQQ", name: "Invesco QQQ", sector: "Nasdaq 100" },
  { ticker: "VTI", name: "Vanguard Total Stock Market ETF", sector: "Broad market" },
  { ticker: "DIA", name: "SPDR Dow Jones Industrial Average ETF", sector: "Broad market" },
  { ticker: "IWM", name: "iShares Russell 2000 ETF", sector: "Small companies" },
  { ticker: "GLD", name: "SPDR Gold Shares", sector: "Gold" },
  { ticker: "SCHD", name: "Schwab US Dividend Equity ETF", sector: "Dividends" },
];

export interface BrowseAsset extends StockOption {
  exchange: string;
  asset_class: "stock" | "etf" | "crypto";
  popular: boolean;
}

const featured = [...POPULAR_STOCKS, ...POPULAR_ETFS];
const featuredByTicker = new Map(featured.map((asset) => [asset.ticker, asset]));
const popularOrder = new Map(featured.map((asset, index) => [asset.ticker, index]));

export function browseAssets(directory: ListedAsset[]): BrowseAsset[] {
  const result = new Map<string, BrowseAsset>();
  for (const asset of featured) {
    result.set(asset.ticker, {
      ...asset,
      exchange: asset.sector === "Crypto" ? "24/7" : "US",
      asset_class: asset.sector === "Crypto" ? "crypto" : POPULAR_ETFS.includes(asset) ? "etf" : "stock",
      popular: true,
    });
  }
  for (const asset of directory) {
    const known = featuredByTicker.get(asset.ticker);
    result.set(asset.ticker, {
      ...asset,
      name: known?.name ?? asset.name,
      sector: known?.sector ?? (asset.asset_class === "etf" ? "ETF" : "Stock"),
      popular: Boolean(known),
    });
  }
  return [...result.values()].sort((a, b) =>
    (popularOrder.get(a.ticker) ?? Infinity) - (popularOrder.get(b.ticker) ?? Infinity)
    || a.ticker.localeCompare(b.ticker),
  );
}

export function filterAssets(assets: BrowseAsset[], query: string): BrowseAsset[] {
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return assets;
  const matches = assets.filter((asset) => {
    const haystack = `${asset.ticker} ${asset.name} ${asset.sector} ${asset.exchange}`.toLowerCase();
    return terms.every((term) => haystack.includes(term) || asset.ticker.toLowerCase().includes(term.replaceAll(".", "-")));
  });
  const exact = query.trim().toUpperCase().replaceAll(".", "-");
  return matches.sort((a, b) => Number(b.ticker === exact) - Number(a.ticker === exact));
}

import type { ListedAsset } from "../api/types";

