import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import SignupPage from "@/app/[locale]/signup/page";
import { SessionProvider } from "@/hooks/use-session";
import { api, ApiError } from "@/lib/api";
import { render } from "@/test/render";

const mockReplace = vi.fn();
vi.mock("next/navigation", () => ({
  usePathname: () => "/en/signup",
  useRouter: () => ({
    push: vi.fn(),
    replace: mockReplace,
  }),
}));

describe("SignupPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the signup form with all required inputs and role options", () => {
    render(
      <SessionProvider>
        <SignupPage />
      </SessionProvider>,
      { locale: "en" },
    );

    expect(screen.getByRole("heading", { name: /create an account/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/full name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /buyer/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /seller/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/paypal sandbox email/i)).toBeInTheDocument();
    expect(screen.getAllByLabelText(/password/i).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("button", { name: /^create account$/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute("href", "/en/login");
  });

  it("submits the form successfully and navigates to deals", async () => {
    const signupSpy = vi.spyOn(api, "signup").mockResolvedValueOnce({
      access_token: "mock-jwt-token",
      token_type: "bearer",
      expires_in: 3600,
      user: {
        id: "mock-user-id",
        email: "alex@example.com",
        full_name: "Alex Morgan",
        role: "buyer",
      },
    });

    render(
      <SessionProvider>
        <SignupPage />
      </SessionProvider>,
      { locale: "en" },
    );

    fireEvent.change(screen.getByLabelText(/full name/i), { target: { value: "Alex Morgan" } });
    fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: "alex@example.com" } });
    fireEvent.change(screen.getAllByLabelText(/password/i)[0], { target: { value: "password123" } });
    fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: "password123" } });

    fireEvent.click(screen.getByRole("button", { name: /^create account$/i }));

    await waitFor(() => {
      expect(signupSpy).toHaveBeenCalledWith({
        email: "alex@example.com",
        password: "password123",
        full_name: "Alex Morgan",
        role: "buyer",
        paypal_account_ref: undefined,
      });
      expect(mockReplace).toHaveBeenCalledWith("/en/deals");
    });
  });

  it("displays an error alert when an account already exists (conflict)", async () => {
    vi.spyOn(api, "signup").mockRejectedValueOnce(
      new ApiError(409, "conflict", "an account with this email already exists"),
    );

    render(
      <SessionProvider>
        <SignupPage />
      </SessionProvider>,
      { locale: "en" },
    );

    fireEvent.change(screen.getByLabelText(/full name/i), { target: { value: "Existing User" } });
    fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: "existing@example.com" } });
    fireEvent.change(screen.getAllByLabelText(/password/i)[0], { target: { value: "password123" } });
    fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: "password123" } });

    fireEvent.click(screen.getByRole("button", { name: /^create account$/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/already exists/i);
    });
  });
});
