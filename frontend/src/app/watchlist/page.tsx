"use client";

import { AppShell } from "@/components/AppShell";
import { SymbolSearch } from "@/components/charts/SymbolSearch";
import { QuickOrderPanel } from "@/components/orders/QuickOrderPanel";
import {
  EmptyState,
  PageHeader,
  Panel,
  TabBar,
} from "@/components/ui/terminal";
import {
  loadWatchlists,
  saveWatchlists,
  type WatchlistItem,
  type Watchlists,
} from "@/lib/watchlist";
import type { Instrument } from "@/services/chartDataService";
import { useEffect, useState } from "react";

const LIST_NAMES = ["Watchlist 1", "Watchlist 2", "Watchlist 3"];

export default function WatchlistPage() {
  const [lists, setLists] = useState<Watchlists>({});
  const [activeList, setActiveList] = useState("Watchlist 1");
  const [searchSymbol, setSearchSymbol] = useState("");
  const [searchExchange, setSearchExchange] = useState("NSE");
  const [tradeSymbol, setTradeSymbol] = useState<string | undefined>();
  const [tradeSide, setTradeSide] = useState<"BUY" | "SELL" | undefined>();

  useEffect(() => {
    setLists(loadWatchlists());
  }, []);

  function persist(next: Watchlists) {
    setLists(next);
    saveWatchlists(next);
  }

  function addInstrument(inst: Instrument) {
    const items = lists[activeList] || [];
    if (items.some((i) => i.symbol === inst.symbol && i.exchange === inst.exchange)) return;
    const item: WatchlistItem = {
      symbol: inst.symbol,
      exchange: inst.exchange,
      display_name: inst.display_name,
      security_id: inst.security_id,
      exchange_segment: inst.exchange_segment,
      segment: inst.segment,
    };
    persist({
      ...lists,
      [activeList]: [...items, item],
    });
    setSearchSymbol(inst.symbol);
    setSearchExchange(inst.exchange);
  }

  function removeItem(item: WatchlistItem) {
    const next = {
      ...lists,
      [activeList]: (lists[activeList] || []).filter(
        (i) => i.symbol !== item.symbol || i.exchange !== item.exchange,
      ),
    };
    persist(next);
  }

  const items = lists[activeList] || [];
  const tabs = LIST_NAMES.map((n) => ({ id: n, label: n }));

  return (
    <AppShell>
      <PageHeader title="Watchlist" subtitle="Search instruments and track symbols" back />
      <div className="grid gap-3 lg:grid-cols-[1fr_280px]">
        <Panel>
          <TabBar tabs={tabs} active={activeList} onChange={setActiveList} />
          <div className="flex flex-wrap gap-3 p-3 border-b border-[var(--line)]">
            <SymbolSearch
              symbol={searchSymbol}
              exchange={searchExchange}
              onSelect={addInstrument}
              placeholder="Search symbol"
            />
          </div>
          {items.length ? (
            <div className="overflow-x-auto">
              <table className="terminal-table w-full">
                <thead>
                  <tr className="border-b border-[var(--line)] bg-[var(--panel-2)]">
                    {["Symbol", "Name", "Exchange", "Actions"].map((h) => (
                      <th key={h} className="px-2 py-1.5 text-left">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={`${item.symbol}-${item.exchange}`} className="border-t border-[var(--line)]">
                      <td className="px-2 py-1.5 font-medium text-white">{item.symbol}</td>
                      <td className="px-2 py-1.5 text-[11px] text-[var(--muted)] max-w-[180px] truncate">
                        {item.display_name || "—"}
                      </td>
                      <td className="px-2 py-1.5 text-[var(--muted)]">{item.exchange}</td>
                      <td className="px-2 py-1.5">
                        <div className="flex gap-1">
                          <button
                            type="button"
                            onClick={() => {
                              setTradeSymbol(item.symbol);
                              setTradeSide("BUY");
                            }}
                            className="text-[10px] text-[var(--profit)]"
                          >
                            Buy
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setTradeSymbol(item.symbol);
                              setTradeSide("SELL");
                            }}
                            className="text-[10px] text-[var(--loss)]"
                          >
                            Sell
                          </button>
                          <button
                            type="button"
                            onClick={() => removeItem(item)}
                            className="text-[10px] text-[var(--muted)]"
                          >
                            Remove
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="Empty watchlist" detail="Search and select a symbol to add." />
          )}
        </Panel>
        <QuickOrderPanel defaultSymbol={tradeSymbol} defaultSide={tradeSide} />
      </div>
    </AppShell>
  );
}
