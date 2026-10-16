# Verdict terms and research-disclosure comparison

Reviewed official sources on October 15, 2026 (America/New_York). These are
paraphrased product-design lessons, not copied contracts or a legal opinion.
Verdict publishes general stock-level Buy/Hold/Sell research and an AI assessment
score; it does not execute trades or accept investment funds. Its actual operator,
jurisdiction, audience, monetization and provider rights remain launch inputs.

| Official comparable service | Relevant sections and lesson | Verdict adaptation | Deliberately not adopted |
| --- | --- | --- | --- |
| [Seeking Alpha Terms of Use](https://about.seekingalpha.com/terms) | Sections 1, 3–6 address agreement, impersonal security research versus individual suitability, investment loss, historical-performance limitations, account conduct and data/content rights. | Describe Buy/Hold/Sell as general stock research; explain that the app does not assess individual finances; explain losses and source limitations beside the product and at signup. Require an explicit checkbox and retain version evidence. | Their legal entity, registration statements, contributor/conflict policies, subscription provisions and blanket transfer of responsibility are not facts about Verdict. No invented registration status or immunity claim. |
| [TradingView Terms of Service and Company Policy](https://www.tradingview.com/policies/) | Sections 6–9 and 12 discuss data errors, trading risk, limitations of hypothetical performance, registration assent and account security. | Put a readable risk notice before account creation; distinguish pretend-money/historical arithmetic from actual results; link full documents and preserve non-waivable rights in qualified warranty/liability wording. | Their billing, exchange subscriber classifications, jurisdiction/dispute provisions and absolute loss exclusions are not justified for this deployment. No arbitrary liability cap or copied arbitration clause. |

These services are comparable for general market research/ratings and charting or
simulation. Their terms are examples of topics to explain, not evidence that
Verdict has the same licenses, regulatory status or enforceable contract.

## Original Verdict wording and implementation

- `frontend/src/lib/legal.ts` contains the original Terms of Service, Risk & Data
  Disclosure and Privacy Policy. The signup checkbox acknowledges receipt of the
  privacy notice; it does not manufacture marketing or unrelated processing consent.
- `SignupAgreement` presents a separate account-agreement screen, initially
  unchecked, with visible investment-loss risk and the full readable documents.
  Creation requires the checkbox and current document versions. Back creates no
  account and clears acceptance. Modal documents support keyboard focus and Escape.
- `backend/app/legal_manifest.json` and the matching frontend manifest identify
  each document version and SHA-256 of the legal-copy source. New email/invite,
  owner and first-time Google accounts require explicit current acceptance.
  The database records versions, fingerprint, server time and purpose atomically
  with account creation; the audit event associates account/request evidence.
- Existing sign-ins and authenticated Google linking do not gain fabricated
  records or imply acceptance of later terms. The additive table migration does
  not backfill legacy users. There is no forced retroactive agreement feature.
- AI scores describe the model's assessment, not verified profit odds or a
  calibrated accuracy rate. Hold is not a validated 50/50. Original prediction
  values, dates and horizons remain intact; statistical diagnostics do not
  certify profitability or legal compliance.
- Chat input/history may contain personal information and may be sent to the
  configured provider. Common personal trade/allocation/holding/future-earnings
  requests get a helpful research redirect. Remaining requests carry model
  instructions and a limited output backstop; these cannot guarantee recognition
  of every phrasing. Historical arithmetic is labelled hypothetical, uses the
  supplied base amount, and does not project account profits or give instructions.

## Remaining deployment decisions

Publish the actual operator identity/contact, governing location and intended
users; determine free/subscription/advertising/affiliate arrangements before
adding payment or conflict provisions. Have appropriate legal review assess the
actual service, advertising, recommendations, jurisdiction and business model.
Educational wording alone does not establish an exemption or eliminate liability.

Complete the provider/hosting inventory and processing settings, retention and
backup policy, and an actual rights/deletion request process before public launch.
This version does not implement self-service deletion or a request channel; the
privacy copy says so rather than promising one. Verify commercial/public-display
rights for every data source and any required provider attribution. Credentials
and open-source code licenses do not establish market-data redistribution rights.

Primary deployment references (checked October 15, 2026):

- [SEC Staff Legal Bulletin No. 11](https://www.sec.gov/interps/legal/slbim11.htm):
  fact-specific advice/compensation/business analysis, including its specific
  municipal-finance context; not a classification of this app.
- [FTC mobile-app marketing guidance](https://www.ftc.gov/business-guidance/resources/marketing-your-mobile-app-get-it-right-start):
  accurately describe privacy/security behavior and substantiate claims.
- [NewsAPI pricing and permitted environments](https://newsapi.org/pricing):
  its Developer plan is for development, not staging/production deployments.
- [yfinance project documentation](https://ranaroussi.github.io/yfinance/):
  its personal-use warning and underlying Yahoo terms require a rights review.
