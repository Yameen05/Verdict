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
    updated: "October 15, 2026",
    sections: [
      {
        heading: "General research, not a personal trading plan",
        body: [
          "Verdict publishes general stock-level Buy/Hold/Sell research assessments for educational use. These assessments do not determine whether a trade is suitable for you. The app does not accept investment deposits, hold investment funds, or place real trades; practice trades use pretend money.",
          "Verdict does not assess your finances, goals, taxes or risk tolerance to choose a trade or allocation for you. Educational labeling and disclaimers do not determine the legal status of a deployment or remove liability.",
          "Reports are generated in part by large language models. AI output can be wrong, out of date, or confidently misleading. Treat every claim as unverified and do your own research or consult a licensed professional before risking money.",
        ],
      },
      {
        heading: "Markets are risky",
        body: [
          "Stocks and cryptocurrencies can lose value quickly, including all of the money you put in. Day trading can amplify losses through volatility, leverage and transaction costs.",
          "An AI assessment score of 70/100 is the model's reading of evidence, not a verified 70% chance of profit or a guaranteed accuracy rate. Hold does not mean a validated 50/50 outcome.",
          "Past performance, backtests, hit rates, and scoreboard statistics do not predict future results. Hypothetical or simulated results have inherent limitations and do not represent real trading.",
        ],
      },
      {
        heading: "Where the data comes from",
        body: [
          "Verdict aggregates data from third-party sources, which may include SEC EDGAR, Yahoo Finance (via the yfinance library), NewsAPI, Alpha Vantage, Finnhub, Polygon, Tiingo, Stooq, FRED, Reddit, and StockTwits, plus an LLM provider you configure.",
          "Market data may be delayed, incomplete, adjusted, or simply wrong, and must be used within each provider's applicable license and terms. Each source's own terms govern its data; this app does not grant you any license to redistribute, resell, or commercially exploit third-party data, and you are responsible for complying with those terms.",
          "Verdict is not affiliated with, endorsed by, or sponsored by any of these providers.",
        ],
      },
      {
        heading: "No warranty",
        body: [
          "To the extent permitted by applicable law, the app is provided \"as is\" and \"as available\" without warranties. Non-waivable statutory rights remain protected. Quotes can be stale, alerts can fail to send, and analysis can be wrong. Never rely on this app as your only source for a financial decision.",
        ],
      },
    ],
  },
  {
    id: "terms",
    label: "Terms",
    title: "Terms of Service",
    updated: "October 15, 2026",
    sections: [
      {
        heading: "Acceptance",
        body: [
          "Creating a new Verdict account requires an affirmative agreement to these Terms of Service, acknowledgement of the investment risks and acknowledgement that you have been provided the Privacy Notice. The agreement step identifies the document versions being recorded. If you do not agree, do not create an account. This step is not consent to marketing or unrelated data use.",
          "Verdict is open-source software released under the MIT license. Each deployment is run by its own operator; these terms are between you and the operator of the instance you are using.",
        ],
      },
      {
        heading: "Eligibility and accounts",
        body: [
          "You must be at least 18 years old (or the age of majority where you live) to use the app.",
          "Keep your password and session secure and do not share access or impersonate another person. Provide a real email address you control — it is used for account recovery and alert emails.",
        ],
      },
      {
        heading: "Acceptable use",
        body: [
          "Use the service lawfully. Do not access other accounts without authorization, interfere with security or availability, evade limits, or scrape or redistribute data beyond the rights granted by its providers. Authorized security testing must stay within the permission given by the operator.",
          "Research runs consume shared, rate-limited resources. The operator may restrict abusive access or change or discontinue features, subject to applicable law. Provider outages, stale data and quota limits can affect availability.",
        ],
      },
      {
        heading: "Your decisions are yours",
        body: [
          "You are responsible for your own investment decisions, including checking information and deciding whether to seek qualified professional advice. Using a Buy/Hold/Sell label, score, chat answer, chart or alert does not guarantee a profit or prevent a loss. You can lose all money invested; the app does not place or manage a real trade for you. To the extent permitted by applicable law, the operator and contributors disclaim liability for investment losses and indirect or consequential damages arising from reliance on the service. Nothing here excludes liability or waives rights that cannot lawfully be excluded or waived.",
          "Disclaimers and these template terms do not guarantee immunity from claims. The deployment operator must obtain appropriate legal review for the actual service, jurisdiction, users and business model before public launch.",
        ],
      },
      {
        heading: "Content and license",
        body: [
          "Access to reports and charts does not grant rights to underlying third-party data. Sharing, redistribution and commercial use depend on the applicable provider licenses and deployment terms.",
          "Document changes are identified by their version and last-updated date. New-account acceptance applies only to the versions presented and recorded at that time; the software does not fabricate later acceptance for existing users.",
        ],
      },
    ],
  },
  {
    id: "privacy",
    label: "Privacy",
    title: "Privacy Policy",
    updated: "October 15, 2026",
    sections: [
      {
        heading: "What is stored",
        body: [
          "Account data: your email address, an Argon2id hash if you set a password (never the password itself), your Google account identifier if you use Google sign-in, and hashes of invites, sessions, and password-reset tokens.",
          "Workspace data: your watchlist, entered positions, price alerts, chart levels, verdict watches, saved strategies, and practice quotes, trades and journal notes. New-account agreement records store document versions, a fingerprint of the legal-copy source and the server-recorded acceptance time; a security audit event also associates the acknowledgement with the account and request. Stored research runs and their track record are shared across accounts on this deployment; they are not private journals.",
          "Security log: authentication events (login, logout, resets, failures) with IP address and browser user-agent, kept to detect abuse.",
        ],
      },
      {
        heading: "Cookies",
        body: [
          "The app uses an HttpOnly session cookie to keep you signed in. Google sign-in also uses a short-lived HttpOnly security cookie. When enabled, it loads Google Identity Services to authenticate you; Google's privacy policy applies to that service. The app does not add advertising cookies or analytics trackers.",
        ],
      },
      {
        heading: "What leaves the server",
        body: [
          "Research and filing search send ticker-related context, filing excerpts, headlines, metrics and search text to the configured AI/embedding providers. Chat can send your free-text question, recent conversation history and supplied report context to the configured AI provider. Personal details you type into those fields may therefore leave this server. Do not enter passwords, account credentials or other sensitive personal information into chat.",
          "Market-data requests send ticker/query information to configured data providers. AI, data, hosting and authentication providers process requests under their own policies; their retention, training and regional processing settings depend on the operator's actual accounts and configuration, which this app does not establish.",
          "If the operator has configured email (SMTP), your email address is used to deliver alert and password-reset messages through that mail service.",
          "The built-in app has no advertising, analytics-tracking or data-sale integration. This does not establish the separate practices of a deployment operator or its hosting/provider services; those require deployment-specific disclosure.",
        ],
      },
      {
        heading: "Retention and deletion",
        body: [
          "This version has no self-service account deletion or implemented deletion-request channel. Workspace and research history are not automatically deleted when a session expires. The operator must publish an actual contact/request process and retention policy before public launch; this template supplies neither a contact address nor a retention period.",
          "Deleting an account is not implemented as a user-facing workflow here. Shared research, security records, backups and copies processed by providers require separate retention/deletion decisions; the app cannot promise immediate deletion of all copies. This policy describes built-in software behavior, and must be completed for the actual deployment.",
        ],
      },
    ],
  },
];

export const FOOTER_DISCLAIMER =
  "Verdict is an educational research tool, not investment advice. Markets involve risk of loss. " +
  "AI assessment scores are not verified odds of profit. Market data may be delayed or inaccurate and remains subject to provider terms.";
