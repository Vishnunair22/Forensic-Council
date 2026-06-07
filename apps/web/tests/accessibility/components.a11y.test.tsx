/**
 * Component-level accessibility smoke tests (jest-axe).
 *
 * Complements the page-level Playwright suite (tests/e2e/accessibility.spec.ts)
 * by asserting individual presentational primitives carry no structural a11y
 * violations (roles, names, ARIA, duplicate ids). Color-contrast is intentionally
 * not run here — axe needs a real layout/canvas engine for it (covered by the e2e
 * suite and the design-system token contrast floors).
 *
 * Page-only rules (a component rendered in isolation is not a full document) are
 * disabled so they do not produce false negatives.
 */
import { render } from "@testing-library/react";
// @ts-expect-error - jest-axe ships no bundled types in this project
import { axe } from "jest-axe";

import { Badge } from "@/components/ui/Badge";
import { GlassPanel } from "@/components/ui/GlassPanel";
import { SectionHeader } from "@/components/ui/SectionHeader";

const AXE_OPTIONS = {
  rules: {
    region: { enabled: false },
    "page-has-heading-one": { enabled: false },
    "landmark-one-main": { enabled: false },
  },
} as const;

describe("component accessibility (jest-axe)", () => {
  it("Badge — every semantic variant is violation-free", async () => {
    const { container } = render(
      <div>
        <Badge variant="default">Default</Badge>
        <Badge variant="success">Authentic</Badge>
        <Badge variant="warning">Review</Badge>
        <Badge variant="destructive">Tampered</Badge>
        <Badge variant="info" withDot>
          Active
        </Badge>
      </div>,
    );
    expect(await axe(container, AXE_OPTIONS)).toHaveNoViolations();
  });

  it("GlassPanel — surface wrapper with content is violation-free", async () => {
    const { container } = render(
      <GlassPanel>
        <p>Evidence summary content.</p>
      </GlassPanel>,
    );
    expect(await axe(container, AXE_OPTIONS)).toHaveNoViolations();
  });

  it("SectionHeader — labelled heading block is violation-free", async () => {
    const { container } = render(
      <section aria-labelledby="sec-test">
        <SectionHeader
          headingId="sec-test"
          eyebrow="How it works"
          titleLead="Five specialists,"
          titleAccent="one verdict"
          subtitle="Each agent inspects the evidence independently before the council deliberates."
        />
      </section>,
    );
    expect(await axe(container, AXE_OPTIONS)).toHaveNoViolations();
  });
});
