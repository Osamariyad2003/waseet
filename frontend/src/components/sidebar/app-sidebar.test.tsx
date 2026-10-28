import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppSidebar } from "@/components/sidebar/app-sidebar";
import { SessionProvider } from "@/hooks/use-session";
import { render } from "@/test/render";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  usePathname: () => "/en/deals",
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
  }),
}));

describe("AppSidebar", () => {
  it("renders all four navigation features: Home, Explore, Wallet, Account", () => {
    render(
      <SessionProvider>
        <AppSidebar locale="en" />
      </SessionProvider>,
      { locale: "en" },
    );

    // Check desktop and mobile instances of nav labels
    const homeLinks = screen.getAllByRole("link", { name: /home/i });
    expect(homeLinks.length).toBeGreaterThanOrEqual(1);
    expect(homeLinks[0]).toHaveAttribute("href", "/en/deals");

    const exploreLinks = screen.getAllByRole("link", { name: /explore/i });
    expect(exploreLinks.length).toBeGreaterThanOrEqual(1);
    expect(exploreLinks[0]).toHaveAttribute("href", "/en/explore");

    const walletLinks = screen.getAllByRole("link", { name: /wallet/i });
    expect(walletLinks.length).toBeGreaterThanOrEqual(1);
    expect(walletLinks[0]).toHaveAttribute("href", "/en/wallet");

    const accountLinks = screen.getAllByRole("link", { name: /account/i });
    expect(accountLinks.length).toBeGreaterThanOrEqual(1);
    expect(accountLinks[0]).toHaveAttribute("href", "/en/account");
  });

  it("marks Home as active when path is /en/deals", () => {
    render(
      <SessionProvider>
        <AppSidebar locale="en" />
      </SessionProvider>,
      { locale: "en" },
    );

    const homeLinks = screen.getAllByRole("link", { name: /home/i });
    expect(homeLinks[0]).toHaveAttribute("aria-current", "page");

    const exploreLinks = screen.getAllByRole("link", { name: /explore/i });
    expect(exploreLinks[0]).not.toHaveAttribute("aria-current");
  });

  it("renders brand name and navigation items cleanly in English", () => {
    render(
      <SessionProvider>
        <AppSidebar locale="en" />
      </SessionProvider>,
      { locale: "en" },
    );

    expect(screen.getByRole("complementary", { name: /sidebar navigation/i })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /waseet/i }).length).toBeGreaterThanOrEqual(1);
  });
});
