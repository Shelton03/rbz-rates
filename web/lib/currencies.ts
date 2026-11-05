export const CURRENCY_NAMES: Record<string, string> = {
  USD: "US dollar", ZAR: "South African rand", GBP: "Pound sterling", JPY: "Japanese yen", ZMW: "Zambian kwacha",
  BWP: "Botswana pula", CHF: "Swiss franc", MWK: "Malawian kwacha", AUD: "Australian dollar", SDR: "IMF special drawing right",
  MZN: "Mozambican metical", NOK: "Norwegian krone", SEK: "Swedish krona", CAD: "Canadian dollar", EUR: "Euro",
  CNY: "Chinese yuan", INR: "Indian rupee", NZD: "New Zealand dollar", DKK: "Danish krone", XAU: "Gold (troy ounce)",
  AFN: "Afghan afghani", THB: "Thai baht", ETB: "Ethiopian birr", SZL: "Eswatini lilangeni", MUR: "Mauritian rupee",
  MYR: "Malaysian ringgit", LSL: "Lesotho loti", AED: "UAE dirham", NAD: "Namibian dollar", ANG: "Netherlands Antillean guilder",
  BRL: "Brazilian real", TZS: "Tanzanian shilling", RUB: "Russian ruble", KES: "Kenyan shilling", DEM: "German mark (legacy)",
  ESP: "Spanish peseta (legacy)", ITL: "Italian lira (legacy)", FRF: "French franc (legacy)", HKD: "Hong Kong dollar",
  ARS: "Argentine peso", XAF: "Central African CFA franc", CYP: "Cypriot pound (legacy)", EGP: "Egyptian pound",
  SGD: "Singapore dollar", KRW: "South Korean won", NGN: "Nigerian naira", UGX: "Ugandan shilling", GHS: "Ghanaian cedi",
};

export const FEATURED = ["USD", "ZAR", "GBP", "EUR", "BWP", "CNY", "ZMW", "MZN", "JPY", "XAU"];

export function formatRate(n: number): string {
  const digits = n >= 1000 ? 2 : n >= 1 ? 4 : 6;
  return n.toLocaleString("en-US", { minimumFractionDigits: Math.min(digits, 4), maximumFractionDigits: digits });
}

export function formatDay(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}
