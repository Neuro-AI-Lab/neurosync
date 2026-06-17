import { render, screen } from "@testing-library/react";

import { RiskBadge } from "./RiskBadge";

describe("RiskBadge", () => {
  it("renders the Korean label for each level", () => {
    const { rerender } = render(<RiskBadge level="low" />);
    expect(screen.getByText("안전")).toBeInTheDocument();

    rerender(<RiskBadge level="critical" />);
    expect(screen.getByText("긴급")).toBeInTheDocument();
  });

  it("exposes an accessible risk-level label", () => {
    render(<RiskBadge level="high" />);
    expect(screen.getByLabelText("위험 등급: 위험")).toBeInTheDocument();
  });
});
