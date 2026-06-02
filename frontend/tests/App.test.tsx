import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";

describe("Hello World", () => {
    it("renders a hello world message", () => {
        render(<p>Hello World</p>);
        expect(screen.getByText("Hello World")).toBeInTheDocument();
    });
});
