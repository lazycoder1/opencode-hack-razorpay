"use client";

import Link from "next/link";
import { FormEvent, useMemo, useState } from "react";

const COST_PER_MICROSITE_INR = 10_000;
const CONTACT_NAME = "Vignesh G Sabhahit";
const CONTACT_PHONE_DISPLAY = "+91 99015 28025";
const CONTACT_PHONE_E164 = "+919901528025";
const UPI_ID = "vigneshsabhahit911@okhdfcbank";
const UPI_PAYEE_NAME = "Vignesh Sabhahit";
const BANK_LABEL = "Standard Chartered 3927";

function formatInr(value: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

function buildUpiIntent(amount: number, note: string) {
  const params = new URLSearchParams({
    pa: UPI_ID,
    pn: UPI_PAYEE_NAME,
    cu: "INR",
  });

  if (amount > 0) {
    params.set("am", amount.toString());
  }

  if (note) {
    params.set("tn", note);
  }

  return `upi://pay?${params.toString()}`;
}

export default function SignupPage() {
  const [sellerOrg, setSellerOrg] = useState("");
  const [micrositeCount, setMicrositeCount] = useState<number | "">(10);
  const [submitted, setSubmitted] = useState(false);
  const [copied, setCopied] = useState<"upi" | "summary" | null>(null);

  const count = typeof micrositeCount === "number" ? micrositeCount : 0;
  const totalInr = count * COST_PER_MICROSITE_INR;

  const paymentNote = useMemo(() => {
    const trimmedOrg = sellerOrg.trim();
    if (!trimmedOrg && count <= 0) {
      return "Convinced microsite order";
    }
    if (!trimmedOrg) {
      return `Convinced microsites x${count}`;
    }
    if (count <= 0) {
      return `${trimmedOrg} - Convinced microsites`;
    }
    return `${trimmedOrg} - ${count} microsites`;
  }, [sellerOrg, count]);

  const orderSummary = useMemo(() => {
    const trimmedOrg = sellerOrg.trim() || "[Seller Org]";
    const lines = [
      "Convinced Microsite Generator - signup",
      `Seller Org: ${trimmedOrg}`,
      `Microsites: ${count}`,
      `Rate: ${formatInr(COST_PER_MICROSITE_INR)} per microsite`,
      `Total: ${formatInr(totalInr)}`,
      `UPI: ${UPI_ID}`,
    ];
    return lines.join("\n");
  }, [sellerOrg, count, totalInr]);

  const whatsappHref = useMemo(() => {
    const text = encodeURIComponent(
      `Hi ${CONTACT_NAME}, I would like to sign up for the Convinced Microsite Generator.\n\n${orderSummary}`,
    );
    return `https://wa.me/${CONTACT_PHONE_E164.replace("+", "")}?text=${text}`;
  }, [orderSummary]);

  const upiIntent = useMemo(() => buildUpiIntent(totalInr, paymentNote), [totalInr, paymentNote]);

  async function copyToClipboard(value: string, label: "upi" | "summary") {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(label);
      window.setTimeout(() => setCopied((current) => (current === label ? null : current)), 1600);
    } catch {
      // Clipboard API can fail on insecure contexts; ignore silently.
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
  }

  const canSubmit = sellerOrg.trim().length > 0 && count > 0;

  return (
    <main className="pageShell">
      <nav className="topbar">
        <div className="brand">
          <div className="brandIcon">CM</div>
          <div className="brandBlock">
            <strong className="brandTitle">Convinced Microsite Generator</strong>
            <span className="brandCaption">Signup and checkout</span>
          </div>
        </div>

        <div className="navCluster">
          <Link className="navLink" href="/">
            Create
          </Link>
          <Link className="navLink" href="/microsites">
            Microsites
          </Link>
          <Link className="navLink" href="/prompts">
            Prompt Library
          </Link>
          <Link className="navLink" href="/observability">
            Observability
          </Link>
        </div>
      </nav>

      <section className="pageIntro">
        <div>
          <p className="kicker">Convinced signup</p>
          <h1 className="pageTitle">Reserve your microsite batch in two quick steps.</h1>
          <p className="sectionText">
            Tell us your organization and how many microsites you need. Each microsite is priced at a flat
            {" "}
            {formatInr(COST_PER_MICROSITE_INR)}. Once you pay, reach out to {CONTACT_NAME} for delivery
            directions.
          </p>
        </div>

        <div className="metricGrid metricGridThree compactMetrics">
          <article className="metricCard">
            <span>Rate</span>
            <strong>{formatInr(COST_PER_MICROSITE_INR)}</strong>
          </article>
          <article className="metricCard">
            <span>Microsites</span>
            <strong>{count || "—"}</strong>
          </article>
          <article className="metricCard">
            <span>Total due</span>
            <strong>{count > 0 ? formatInr(totalInr) : "—"}</strong>
          </article>
        </div>
      </section>

      <section className="signupGrid">
        <form className="panel formPanel" onSubmit={handleSubmit}>
          <div className="panelHeader">
            <div>
              <p className="kicker">01 · Details</p>
              <h2 className="sectionTitle">Your order</h2>
            </div>
            <p className="sectionText">We use this to label your batch and reconcile the payment.</p>
          </div>

          <label className="fieldGroup" htmlFor="seller-org">
            <div className="fieldLabel">
              <strong>Seller Org</strong>
              <span className="fieldHint">Your company or workspace name</span>
            </div>
            <input
              id="seller-org"
              type="text"
              autoComplete="organization"
              value={sellerOrg}
              onChange={(event) => setSellerOrg(event.target.value)}
              placeholder="e.g. Convinced Labs"
            />
          </label>

          <label className="fieldGroup" htmlFor="microsite-count">
            <div className="fieldLabel">
              <strong>Number of Microsites</strong>
              <span className="fieldHint">Minimum 1</span>
            </div>
            <input
              id="microsite-count"
              type="number"
              inputMode="numeric"
              min={1}
              step={1}
              value={micrositeCount}
              onChange={(event) => {
                const raw = event.target.value;
                if (raw === "") {
                  setMicrositeCount("");
                  return;
                }
                const parsed = Number.parseInt(raw, 10);
                setMicrositeCount(Number.isFinite(parsed) && parsed >= 0 ? parsed : "");
              }}
              placeholder="10"
            />
          </label>

          <div className="orderSummary">
            <div className="orderRow">
              <span>Cost per microsite</span>
              <strong>{formatInr(COST_PER_MICROSITE_INR)}</strong>
            </div>
            <div className="orderRow">
              <span>Microsites</span>
              <strong>× {count || 0}</strong>
            </div>
            <div className="orderDivider" />
            <div className="orderRow orderTotal">
              <span>Total due</span>
              <strong>{formatInr(totalInr)}</strong>
            </div>
          </div>

          <div className="actionRow">
            <button className="buttonPrimary" type="submit" disabled={!canSubmit}>
              Confirm order
            </button>
            <button
              className="buttonSecondary"
              type="button"
              onClick={() => copyToClipboard(orderSummary, "summary")}
              disabled={!canSubmit}
            >
              {copied === "summary" ? "Copied summary" : "Copy summary"}
            </button>
          </div>

          {submitted ? (
            <div className="noticePanel">
              <p className="miniLabel">Next</p>
              <p>
                Great — your order for {count} microsite{count === 1 ? "" : "s"} at {formatInr(totalInr)} is
                ready. Pay via the UPI panel, then message {CONTACT_NAME} with your payment screenshot so we
                can kick off delivery.
              </p>
              <div className="actionRow">
                <a className="buttonPrimary" href={whatsappHref} rel="noreferrer" target="_blank">
                  WhatsApp {CONTACT_NAME.split(" ")[0]}
                </a>
                <a className="buttonSecondary" href={`tel:${CONTACT_PHONE_E164}`}>
                  Call {CONTACT_PHONE_DISPLAY}
                </a>
              </div>
            </div>
          ) : null}
        </form>

        <aside className="panel paymentPanel">
          <div className="panelHeader compactHeader">
            <div>
              <p className="kicker">02 · Payment</p>
              <h2 className="sectionTitle">Pay via UPI</h2>
            </div>
          </div>

          <div className="qrFrame">
            {/* Drop the QR screenshot at public/upi-qr.png to replace the fallback. */}
            <img
              alt={`UPI QR code for ${UPI_PAYEE_NAME}`}
              className="qrImage"
              src="/upi-qr.png"
              onError={(event) => {
                const target = event.currentTarget;
                target.style.display = "none";
                const fallback = target.nextElementSibling as HTMLElement | null;
                if (fallback) {
                  fallback.style.display = "grid";
                }
              }}
            />
            <div className="qrFallback">
              <strong>QR image pending</strong>
              <span>Save your Google Pay QR as <code>public/upi-qr.png</code> to show it here.</span>
              <span>You can still pay using the UPI ID below.</span>
            </div>
          </div>

          <div className="upiBadge">
            <div>
              <p className="miniLabel">UPI ID</p>
              <strong className="upiId">{UPI_ID}</strong>
            </div>
            <button
              className="buttonTertiary"
              type="button"
              onClick={() => copyToClipboard(UPI_ID, "upi")}
            >
              {copied === "upi" ? "Copied" : "Copy"}
            </button>
          </div>

          <dl className="payeeList">
            <div className="payeeRow">
              <dt>Payee</dt>
              <dd>{UPI_PAYEE_NAME}</dd>
            </div>
            <div className="payeeRow">
              <dt>Bank</dt>
              <dd>{BANK_LABEL}</dd>
            </div>
            <div className="payeeRow">
              <dt>Reference note</dt>
              <dd>{paymentNote}</dd>
            </div>
            {count > 0 ? (
              <div className="payeeRow payeeHighlight">
                <dt>Amount</dt>
                <dd>{formatInr(totalInr)}</dd>
              </div>
            ) : null}
          </dl>

          <div className="actionRow">
            <a className="buttonPrimary" href={upiIntent}>
              Open in UPI app
            </a>
            <a className="buttonSecondary" href={whatsappHref} rel="noreferrer" target="_blank">
              Share with {CONTACT_NAME.split(" ")[0]}
            </a>
          </div>

          <div className="contactCard">
            <p className="miniLabel">Need directions?</p>
            <strong>Reach out to {CONTACT_NAME}</strong>
            <p className="contactPhoneRow">
              <a className="textLink" href={`tel:${CONTACT_PHONE_E164}`}>
                {CONTACT_PHONE_DISPLAY}
              </a>
              <span className="contactSep">·</span>
              <a className="textLink" href={whatsappHref} rel="noreferrer" target="_blank">
                WhatsApp
              </a>
            </p>
          </div>
        </aside>
      </section>
    </main>
  );
}
