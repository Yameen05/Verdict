import { describe, expect, it } from "vitest";
import { browseAssets, filterAssets } from "./stockCatalog";

describe("stock board directory", () => {
  it("finds companies outside the quick suggestions while retaining popular names", () => {
    const assets = browseAssets([{ ticker: "ZZZZ", name: "Example Robotics", exchange: "NASDAQ", asset_class: "stock" }]);
    expect(filterAssets(assets, "robotics").map((asset) => asset.ticker)).toEqual(["ZZZZ"]);
    expect(assets.some((asset) => asset.ticker === "NVDA")).toBe(true);
    expect(assets.filter((asset) => asset.asset_class === "stock").length).toBeGreaterThan(8);
  });
  it("merges directory metadata without duplicating famous stocks or dropping other asset types", () => {
    const assets = browseAssets([{ ticker: "AAPL", name: "Apple Inc. Common Stock", exchange: "NASDAQ", asset_class: "stock" }]);
    expect(assets.filter((asset) => asset.ticker === "AAPL")).toEqual([
      expect.objectContaining({ name: "Apple", exchange: "NASDAQ", popular: true, asset_class: "stock" }),
    ]);
    expect(assets.find((asset) => asset.ticker === "SPY")?.asset_class).toBe("etf");
    expect(assets.find((asset) => asset.ticker === "BTC-USD")?.asset_class).toBe("crypto");
  });
  it("puts exact tickers before company-name matches and accepts class-share punctuation", () => {
    const assets = browseAssets([{ ticker: "A", name: "Agilent Technologies", exchange: "NYSE", asset_class: "stock" }]);
    expect(filterAssets(assets, "A")[0].ticker).toBe("A");
    expect(filterAssets(assets, "BRK.B")[0].ticker).toBe("BRK-B");
    expect(filterAssets(assets, "does not exist")).toEqual([]);
  });
});
