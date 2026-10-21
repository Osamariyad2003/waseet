"use client";

/**
 * PayPal checkout, JS SDK v6.
 *
 * v6 (not v5, per the SRS) authenticates the browser SDK with a short-lived
 * client token minted server-side, so the client secret never reaches the
 * browser. The flow:
 *
 *   1. fetch a browser-safe client token from our backend;
 *   2. load the v6 core script and create an SDK instance;
 *   3. start a one-time payment session, handing it a callback that creates
 *      the order on our backend (so the amount comes from the deal, never
 *      from the browser);
 *   4. on approval, tell our backend to capture — the server captures and
 *      moves the deal to FUNDED.
 *
 * The button never decides anything about money: it cannot set the amount,
 * and the order id it returns is checked against the deal's own order
 * server-side.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { ApiError, api } from "@/lib/api";

// The v6 core SDK URL is environment-specific and comes from the backend
// with the client token, so the browser never loads a production SDK against
// a sandbox order — the failure that looks like "things don't appear to be
// working" in PayPal's own window.
const SDK_SCRIPT_ID = "paypal-web-sdk-v6";

type Presentation = { presentationMode: "popup" | "modal" | "auto" };

interface OneTimePaymentSession {
  start: (
    options: Presentation,
    orderPromise: Promise<{ orderId: string }>,
  ) => Promise<void>;
}

interface PayPalSdkInstance {
  createPayPalOneTimePaymentSession: (callbacks: {
    onApprove: (data: { orderId: string }) => Promise<void> | void;
    onCancel?: () => void;
    onError?: (error: unknown) => void;
  }) => OneTimePaymentSession;
}

interface PayPalGlobal {
  createInstance: (options: {
    clientToken: string;
    components: string[];
    pageType?: string;
  }) => Promise<PayPalSdkInstance>;
}

declare global {
  interface Window {
    paypal?: PayPalGlobal;
  }
}

/** Load the v6 core script once per page, from the environment's URL. */
function loadSdkScript(sdkUrl: string): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("no window"));
  if (window.paypal) return Promise.resolve();

  const existing = document.getElementById(SDK_SCRIPT_ID) as HTMLScriptElement | null;
  if (existing) {
    return new Promise((resolve, reject) => {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error("sdk failed")), {
        once: true,
      });
    });
  }

  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.id = SDK_SCRIPT_ID;
    script.src = sdkUrl;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("sdk failed"));
    document.head.appendChild(script);
  });
}

type Phase = "idle" | "preparing" | "ready" | "paying" | "capturing" | "error";

interface PayPalCheckoutButtonProps {
  dealId: string;
  /** Called once the backend confirms the capture, so the page can refetch. */
  onFunded: () => void;
  disabled?: boolean;
  disabledReason?: string;
}

export function PayPalCheckoutButton({
  dealId,
  onFunded,
  disabled,
  disabledReason,
}: PayPalCheckoutButtonProps) {
  const t = useTranslations();
  const [phase, setPhase] = useState<Phase>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const sdkRef = useRef<PayPalSdkInstance | null>(null);

  // Prepare the SDK up front so the first click opens checkout immediately
  // rather than after two round trips.
  useEffect(() => {
    if (disabled) return;
    let cancelled = false;

    const prepare = async () => {
      setPhase("preparing");
      try {
        // The token carries the environment's SDK URL, so the matching
        // sandbox/live core script loads — fetch it before the script.
        const { client_token, sdk_url } = await api.getClientToken();
        await loadSdkScript(sdk_url);
        if (cancelled) return;
        if (!window.paypal) throw new Error("sdk missing");

        sdkRef.current = await window.paypal.createInstance({
          clientToken: client_token,
          components: ["paypal-payments"],
          pageType: "checkout",
        });
        if (!cancelled) setPhase("ready");
      } catch (error) {
        if (cancelled) return;
        setPhase("error");
        setMessage(
          error instanceof ApiError && error.code === "paypal_error"
            ? error.message
            : t("funding.sdkFailed"),
        );
      }
    };

    void prepare();
    return () => {
      cancelled = true;
    };
  }, [disabled, t]);

  const handleClick = useCallback(async () => {
    const sdk = sdkRef.current;
    if (!sdk) return;

    setMessage(null);
    setPhase("paying");

    const session = sdk.createPayPalOneTimePaymentSession({
      onApprove: async (data) => {
        setPhase("capturing");
        try {
          // The server captures. The browser only reports which order the
          // buyer approved, and the server refuses an id that is not this
          // deal's own.
          await api.captureOrder(dealId, data.orderId);
          setPhase("ready");
          onFunded();
        } catch (error) {
          setPhase("error");
          setMessage(error instanceof ApiError ? error.message : t("funding.failed"));
        }
      },
      onCancel: () => {
        setPhase("ready");
        setMessage(t("funding.cancelled"));
      },
      onError: () => {
        setPhase("error");
        setMessage(t("funding.failed"));
      },
    });

    try {
      await session.start(
        // "auto" lets the SDK pick popup or modal — the documented default.
        { presentationMode: "auto" },
        // The order is created by our backend from the deal's own amount.
        api.createOrder(dealId).then((order) => ({ orderId: order.paypal_order_id })),
      );
    } catch (error) {
      setPhase("error");
      setMessage(error instanceof ApiError ? error.message : t("funding.failed"));
    }
  }, [dealId, onFunded, t]);

  if (disabled) {
    return (
      <div className="space-y-2">
        <Button disabled>{t("funding.payWithPayPal")}</Button>
        {disabledReason ? <p className="text-sm text-ink-muted">{disabledReason}</p> : null}
      </div>
    );
  }

  const busy = phase === "preparing" || phase === "paying" || phase === "capturing";
  const busyLabel =
    phase === "capturing"
      ? t("funding.capturing")
      : phase === "preparing"
        ? t("funding.preparing")
        : t("funding.payWithPayPal");

  return (
    <div className="space-y-2">
      <Button onClick={handleClick} disabled={busy || phase === "error"} size="lg">
        {busy ? (
          <>
            <Spinner label={busyLabel} />
            {busyLabel}
          </>
        ) : (
          t("funding.payWithPayPal")
        )}
      </Button>

      {message ? (
        <p
          role={phase === "error" ? "alert" : "status"}
          className={
            phase === "error" ? "text-sm text-status-attention" : "text-sm text-ink-muted"
          }
        >
          {message}
        </p>
      ) : null}

      {phase === "error" ? (
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="text-sm font-medium text-accent underline"
        >
          {t("common.retry")}
        </button>
      ) : null}
    </div>
  );
}
