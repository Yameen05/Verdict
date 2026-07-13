/** Legal & disclosure copy rendered by LegalModal. Plain objects, no JSX. */

export interface LegalSection {
  heading: string;
  body: string[];
}

export interface LegalDoc {
  id: "risk" | "terms" | "privacy";
  label: string;
  title: string;
  updated: string;
  sections: LegalSection[];
}

export const LEGAL_DOCS: LegalDoc[] = [
  {
    id: "risk",
    label: "Risk & data",
    title: "Risk & Data Disclosure",
    updated: "July 13, 2026",
    sections: [
      {
        heading: "Verdict is not investment advice",
        body: [
          "Verdict is an educational research tool and software demonstration. Nothing it produces — verdicts, confidence scores, day-trade signals, entries, stops, targets, return ranges, chat answers, or anything else — is investment, financial, trading, tax, or legal advice, or a recommendation to buy, sell, or hold any security or digital asset.",
          "The operator of this deployment is not a registered investment adviser, broker-dealer, or financial planner, and no adviser-client or fiduciary relationship is created by using the app.",
          "Reports are generated in part by large language models. AI output can be wrong, out of date, or confidently misleading. Treat every claim as unverified and do your own research or consult a licensed professional before risking money.",
        ],
      },
      {
        heading: "Markets are risky",
        body: [
          "Stocks and cryptocurrencies can lose value quickly, including all of the money you put in. Day trading in particular results in losses for most participants.",
          "Past performance, backtests, hit rates, and scoreboard statistics do not predict future results. Hypothetical or simulated results have inherent limitations and do not represent real trading.",
        ],
      },
      {
        heading: "Where the data comes from",
        body: [
          "Verdict aggregates data from third-party sources, which may include SEC EDGAR, Yahoo Finance (via the yfinance library), NewsAPI, Alpha Vantage, Finnhub, Polygon, Tiingo, Stooq, FRED, Reddit, and StockTwits, plus an LLM provider you configure.",
          "Market data may be delayed, incomplete, adjusted, or simply wrong, and is provided for personal, non-commercial, informational use only. Each source's own terms govern its data; this app does not grant you any license to redistribute, resell, or commercially exploit third-party data, and you are responsible for complying with those terms.",
          "Verdict is not affiliated with, endorsed by, or sponsored by any of these providers.",
        ],
      },
      {
        heading: "No warranty",
        body: [
          "The app is provided \"as is\" and \"as available\", without warranties of any kind. Quotes can be stale, alerts can fail to send, and analysis can be wrong. Never rely on this app as your only source for a financial decision.",
        ],
      },
    ],
  },
  {
    id: "terms",
    label: "Terms",
    title: "Terms of Use",
    updated: "July 13, 2026",
    sections: [
      {
        heading: "Acceptance",
        body: [
          "By creating an account or using this deployment of Verdict, you agree to these Terms of Use, the Privacy Policy, and the Risk & Data Disclosure. If you do not agree, do not use the app.",
          "Verdict is open-source software released under the MIT license. Each deployment is run by its own operator; these terms are between you and the operator of the instance you are using.",
        ],
      },
      {
        heading: "Eligibility and accounts",
        body: [
          "You must be at least 18 years old (or the age of majority where you live) to use the app.",
          "You are responsible for keeping your password, two-factor device, and recovery codes secure, and for all activity on your account. Provide a real email address you control — it is used for account recovery and alert emails.",
        ],
      },
      {
        heading: "Acceptable use",
        body: [
          "Do not attempt to break, overload, or probe the service; do not evade rate limits or daily run quotas; do not scrape or bulk-export third-party data through the app; do not use the app for any unlawful purpose or in violation of any data provider's terms.",
          "Research runs consume shared, rate-limited resources. The operator may throttle, suspend, or remove accounts that abuse the service, and may revoke access or discontinue the service at any time.",
        ],
      },
      {
        heading: "Your decisions are yours",
        body: [
          "Any trade or investment you make after reading the app's output is your own decision and your own risk. To the maximum extent permitted by law, the operator and contributors are not liable for trading losses or for any indirect, incidental, special, consequential, or punitive damages arising from your use of the app.",
          "To the extent liability cannot be excluded, the total aggregate liability of the operator for all claims relating to the app is limited to the greater of the amount you paid to use it (typically zero) or fifty US dollars.",
        ],
      },
      {
        heading: "Content and license",
        body: [
          "Reports, charts, and other output generated for you may be used for your personal, non-commercial purposes. Underlying third-party data remains subject to its own licenses and may not be redistributed.",
          "These terms may be updated as the software evolves; continued use after a change constitutes acceptance. Material changes will be reflected in the \"last updated\" date above.",
        ],
      },
    ],
  },
  {
    id: "privacy",
    label: "Privacy",
    title: "Privacy Policy",
    updated: "July 13, 2026",
    sections: [
      {
        heading: "What is stored",
        body: [
          "Account data: your email address, an Argon2id hash of your password (never the password itself), an encrypted TOTP seed if you enable two-factor authentication, and keyed hashes of recovery codes, invites, sessions, and password-reset tokens.",
          "Workspace data: your watchlist, positions, price alerts, chart levels, verdict watches, and the research runs you trigger (research runs for a ticker are shared across accounts on this deployment).",
          "Security log: authentication events (login, logout, resets, failures) with IP address and browser user-agent, kept to detect abuse.",
        ],
      },
      {
        heading: "Cookies",
        body: [
          "The app sets one HttpOnly session cookie, used only to keep you signed in. There are no advertising cookies, no analytics trackers, and no third-party scripts.",
        ],
      },
      {
        heading: "What leaves the server",
        body: [
          "To generate research, the app sends ticker symbols and derived research context (filing excerpts, headlines, metrics — never your password or personal details) to the configured LLM provider, and ticker symbols to market-data providers. Those providers process that data under their own privacy policies.",
          "If the operator has configured email (SMTP), your email address is used to deliver alert and password-reset messages through that mail service.",
          "Your data is never sold or shared for advertising.",
        ],
      },
      {
        heading: "Retention and deletion",
        body: [
          "Data is kept while your account exists. To delete your account and its data, contact the operator of this deployment — deletion removes your account, workspace state, and personal identifiers from the active database.",
          "This is self-hosted software: the operator of each instance is the data controller for that instance, and this policy describes the app's built-in behavior.",
        ],
      },
    ],
  },
];

export const FOOTER_DISCLAIMER =
  "Verdict is an educational research tool, not investment advice. Markets involve risk of loss. " +
  "Market data comes from third-party sources, may be delayed or inaccurate, and is for personal, non-commercial use only.";
