const KNOWN_COMPANY_LOGOS: Record<string, string> = {
  razorpay: "/company-assets/razorpay-logo.svg",
  zomato: "/company-assets/zomato-logo.svg",
};

function normalizeCompanyName(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

export function getKnownCompanyLogo(companyName: string) {
  return KNOWN_COMPANY_LOGOS[normalizeCompanyName(companyName)] ?? null;
}
