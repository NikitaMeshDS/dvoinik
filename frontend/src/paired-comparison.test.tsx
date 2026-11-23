// @vitest-environment jsdom
import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import PairedComparison from "./features/reports/PairedComparison";

it("distinguishes zero effect and absent paired data", () => {
  render(
    <PairedComparison
      mock={false}
      total={100}
      pairs={[
        {
          variants: ["A", "B"],
          matched_n: 60,
          means: [0.5, 0.5],
          gap_pp: 0,
          interval_95_pp: [0, 0],
        },
        {
          variants: ["A", "C"],
          matched_n: 0,
          means: null,
          gap_pp: null,
          interval_95_pp: null,
        },
      ]}
    />,
  );
  const first = screen.getByRole("row", { name: /60 из 100 профилей/ });
  expect(within(first).getByText("50,0% / 50,0%")).toBeTruthy();
  expect(within(first).getByText("95% интервал 0,0 … 0,0")).toBeTruthy();
  const missing = screen.getByRole("row", {
    name: /0 из 100 профилей.*Нет полных пар/,
  });
  expect(within(missing).queryByText(/95% интервал/)).toBeNull();
});
