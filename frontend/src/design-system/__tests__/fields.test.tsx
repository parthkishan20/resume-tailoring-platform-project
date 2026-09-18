import "../test-polyfills";
import * as React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Input } from "../Input";
import { Textarea } from "../Textarea";

describe("Input", () => {
  it("associates a real <label> with the field", () => {
    render(<Input label="Resume name" />);
    expect(screen.getByLabelText("Resume name")).toBeInTheDocument();
  });

  it("keeps the label out of the placeholder", () => {
    render(<Input label="Resume name" placeholder="Senior backend engineer" />);
    const field = screen.getByLabelText("Resume name");
    expect(field).toHaveAttribute("placeholder", "Senior backend engineer");
    expect(field.getAttribute("placeholder")).not.toBe("Resume name");
  });

  it("describes the field with its helper text", () => {
    render(<Input label="Resume name" helper="Shown in the library list." />);
    expect(screen.getByLabelText("Resume name")).toHaveAccessibleDescription(
      "Shown in the library list.",
    );
  });

  it("announces an error, marks the field invalid, and replaces the helper", () => {
    render(<Input label="Resume name" helper="Shown in the library." error="Enter a name." />);
    const field = screen.getByLabelText("Resume name");
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field).toHaveAccessibleDescription("Enter a name.");
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a name.");
    expect(screen.queryByText("Shown in the library.")).not.toBeInTheDocument();
  });

  it("accepts typing", async () => {
    render(<Input label="Resume name" />);
    await userEvent.type(screen.getByLabelText("Resume name"), "Draft 3");
    expect(screen.getByLabelText("Resume name")).toHaveValue("Draft 3");
  });

  it("gives each instance a unique id without being told one", () => {
    render(
      <>
        <Input label="First" />
        <Input label="Second" />
      </>,
    );
    expect(screen.getByLabelText("First").id).not.toBe(screen.getByLabelText("Second").id);
  });
});

describe("Textarea", () => {
  it("associates a real <label> with the field", () => {
    render(<Textarea label="Job description" />);
    expect(screen.getByLabelText("Job description")).toBeInTheDocument();
  });

  it("announces an error and marks the field invalid", () => {
    render(<Textarea label="Job description" error="Paste a job description." />);
    expect(screen.getByLabelText("Job description")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("Paste a job description.");
  });

  it("describes the field with its helper text", () => {
    render(<Textarea label="Job description" helper="Shared by Tailor and Evaluate." />);
    expect(screen.getByLabelText("Job description")).toHaveAccessibleDescription(
      "Shared by Tailor and Evaluate.",
    );
  });
});
