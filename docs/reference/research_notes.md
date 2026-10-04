# Satark research notes (2026-10-03)
## AMFI
- NAVAll.txt: https://www.amfiindia.com/spages/NAVAll.txt -> 302 -> https://portal.amfiindia.com/spages/NAVAll.txt ; 200 OK, ~1.5MB, 18104 lines; header: Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date ; NAV date 01-Oct-2026 (8 cols now incl Plan, Option)
- ARN locator: https://www.amfiindia.com/locate-distributor ; suspended ARN: https://www.amfiindia.com/locate-distributor/suspended-arn
## NPCI
- UPI Help: pilot announced 8 Oct 2025 at GFF 2025 (news: businessworld, adda247); FiMI-powered; Eng/Hindi/Telugu/Bengali; via bank websites, chatbots, DigiSaathi, later in UPI apps
- Beneficiary name (CBS) display mandatory from 30 Jun 2025 (P2P, P2PM) (news: business-standard, angelone)
- AMFI locator JSON (undocumented, used by site JS): https://www.amfiindia.com/api/distributor-agent?strOpt=ALL&search=<name|ARN digits>&page=1&pageSize=N (also &city= / &pinCode=) -> fields ARN, ARNHolderName, Address, ARNValidFrom, ARNValidTill, Pin, City, KYDCompliant, EUIN, SIF_Validity_From/to, TelephoneNumber_O/R, Email. Tested OK (search=HDFC). No captcha.
- AMFI /api/arn-social-media-links?arn=<ARN> -> social links per ARN (empty for tested ARNs) -> AMFI collects MFD social handles
- Other pages: /locate-distributor/invalid-arn, /locate-distributor/list-of-arn-misselling (quarterly PDFs e.g. https://www.amfiindia.com/uploads/Mis_Selling_Data_Apr_Jun_2026_5090235588.pdf), /locate-distributor/suspended-arn
- NAV history: https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx?frmdt=01-Sep-2026&todt=02-Sep-2026 -> 200, semicolon text: Scheme Code;NAV Name;Plan;Option;ISIN...;Net Asset Value;Date
- AMFI Terms https://www.amfiindia.com/terms-of-use : personal & non-commercial use only; "shall not store electronically any significant portion"; no reverse engineering/linking/framing w/o written approval; link only to home page.
- NPCI site returns 403 to curl (bot block). Dispute: upi.disputes@npci.org.in (secondary: razorpay/paytm blogs); 45-day chargeback window from 25 Jul 2024 (secondary)
## RBI
- NBFC list page https://www.rbi.org.in/Scripts/BS_NBFCList.aspx : "June 30, 2026 List of NBFCs and ARCs registered with the RBI" XLSX https://rbidocs.rbi.org.in/rdocs/content/DOCs/List_of_NBFCs_and_ARCs_registered_with_the_RBI.XLSX + PDF; ALSO "List of NBFCs and ARCs whose CoR has been cancelled by the RBI" XLSX https://rbidocs.rbi.org.in/rdocs/content/DOCs/List_of_NBFCs_and_ARCs_whose_CoR_has_been_cancelled_by_the_RBI.XLSX ; discrepancy email nbfclistdor@rbi.org.in. rbidocs has JS bot challenge (F5 TSPD "bobcmn") -> curl gets HTML, need browser/manual download.
- ETP list HTML https://rbi.org.in/scripts/bs_viewcontent.aspx?Id=4080 under Master Direction - RBI (Electronic Trading Platforms) Directions, 2025; entries: CCIL/Clearcorp FX-CLEAR (incl FX-RETAIL), NDS-Call, NDS-OM, CROMS, TREPS, ASTROID; ICAP i-Stream; 360T TEX/SEP, 360TGTX; Refinitiv FXall ... ; (PDF version https://rbidocs.rbi.org.in/rdocs/Content/PDFs/LISTETPSD9BC0F6159C9491A802B72122A91550D.PDF per search)
- DLA directory: linked from RBI home as "DLA's deployed by Regulated Entities" -> https://data.rbi.org.in/BOE/OpenDocument/opendoc/custom.jsp?sIDType=CUID&iDocID=ARfEgy.WNSVIvFfvSIVmBCw (SAP BusinessObjects viewer, JS). Operational from 01.07.2025 (PIB PRID 2241255 per search; pib 403 to fetch). RE-reported via CIMS; "as is".
- RBI site URLs 200: cms.rbi.org.in, rbikehtahai.rbi.org.in, /FinancialEducation/Home.aspx, data.rbi.org.in, udgam.rbi.org.in, IFSCMICRDetails.aspx
- PSO list HTML https://rbi.org.in/Scripts/PublicationsView.aspx?id=12043 : FMIs, CCPs, NPCI systems, PPIs (e.g. ZikZuk 14.05.2026), Payment Aggregators (PA-O, PA-P, PA-CB) e.g. 1Pay, Adyen, Airpay, Amazon Pay...
- Authorised dealers https://rbi.org.in/commonman/English/Scripts/AuthorizedDealers.aspx ; franchisees https://rbi.org.in/scripts/franchisees_List.aspx ; FFMC PDF https://rbi.org.in/commonman/Upload/English/Content/PDFs/75926.pdf
- RBI Kehta Hai: rbikehtahai.rbi.org.in -> TSPD CAPTCHA bot wall
- DBIE: https://data.rbi.org.in/DBIE/#/dbie/home ; no public API (secondary); RBIDATA app
- MoSPI: MCP server https://mcp.mospi.gov.in/ (MIT, github nso-india/esankhyiki-mcp), API base https://api.mospi.gov.in (unreachable from here, 000), no API key per README; launched beta 6 Feb 2026 (dev.to secondary); CPI page https://esankhyiki.mospi.gov.in/macroindicators?product=cpi
- data.gov.in: www.data.gov.in 200; data.gov.in 503; api.data.gov.in conn fail from here. Company Master Data catalog: Published 15/09/2015, Updated 22/07/2026 (www page), NDSAP, MCA contributor; GODL licence.
- NCRB Crime in India 2023 released 30 Sep 2025: cybercrime 86,420 (2023) vs 65,893 (2022) +31.2%; fraud 59,526 (68.9%) (secondary: vajiram, visionias)
- MCA, IEPF: 403 to curl. iepf.org.in is NOT official (private).
## SEBI extras
- DNVS: https://www.sebi.gov.in/sebiweb/dnvs-authentication-v2.html (homepage link "Authenticate Document Issued by SEBI"); launched Apr 2025 (BS 3 Apr 2025); Sep 2026 revamp: subject matter mandatory; OTP to recipient mobile; dnvs@sebi.gov.in; confirms issuance not content
- 30-day rule: SEBI circular 08 May 2026 "Norms for sharing and usage of price data for educational purposes" https://www.sebi.gov.in/legal/circulars/may-2026/norms-for-sharing-and-usage-of-price-data-for-educational-purposes_101293.html ; No. HO/47/17/12(11)2025-MRD-POD3/I/11107/2026 ; effective 1 Jul 2026; replaces 1-day (24 May 2024) & 3-month (29 Jan 2025); NISM 1-day exemption
- MI portal: https://mi.sebi.gov.in/ (also miportal.sebi.gov.in per SCORES FAQ) no acknowledgement/complaint number
- investor.sebi.gov.in/Investor-support.html: lists -> NSE mobile apps https://www.nseindia.com/trade/members-compliance/list-of-mobile-applications ; BSE https://www.bseindia.com/investors/mobiletradingmember.aspx ; NCDEX https://ncdex.com/ctcl/listing-of-trading-members-mobile-application ; MCX https://www.mcxindia.com/technology/ctcl/authorized-mobile-applications ; MSE https://inspection-os.msei.in/MobileApplication/MobileApplication_View.aspx ; IA weblinks https://www.bseindia.com/iara/weblink.aspx ; RA weblinks https://www.bseindia.com/IARA/weblink_ra.aspx ; OBPP https://www.sebi.gov.in/online-bond-platform-providers.html ; AMFI MF apps https://www.amfiindia.com/list-of-mobile-application ; broker social handles BSE https://www.bseindia.com/investors/SocialMediaTM.aspx NSE https://www.nseindia.com/trade/members-compliance/list-of-social-media-handle NCDEX https://www.ncdex.com/disclosures/members-social-media-handles MSE https://inspection-os.msei.in/MobileApplication/SocialMedia_View.aspx ; MF Central https://www.mfcentral.com/ inactive folios https://app.mfcentral.com/links/inactive-folios
- SEBI helpline 1800-266-7575 / 1800-22-7575 (7 langs, 9-6); asksebi@sebi.gov.in
- Saa₹thi 2.0 (June 2024 BS) 12 languages incl Eng (secondary)
## NSE/BSE extras
- NSE mobile apps JSON: https://www.nseindia.com/api/list-of-mobile-applications (needs NSE cookie from page visit) -> 619 rows: srNo, memberCode, memberName, productName, devName, playStore, androidAppLink (play url w/ package id), appStore, iosAppLink
- NSE broker social handles JSON: https://www.nseindia.com/api/list-of-social-media-handel (sic) -> 582 rows: memberCode, memberName, facebook, instagram, linkedIn, twitter, youtube, nameOfSocialMedia, linkOfSocialMedia
- NSE ToU https://www.nseindia.com/static/nse-terms-of-use : "User is prohibited to conduct any systematic or automated data collection activities (including scraping, data mining, data extraction and data harvesting)"; no copy/store/redistribute w/o prior written permission
- BSE pages (iara weblink, SocialMediaTM, mobiletradingmember) are Angular SPA (data via BSE API; IARA pages show IA/RA website, mobile app, social media)
- NSE debarred: page https://www.nseindia.com/static/regulations/member-sebi-debarred-entities ; file https://nsearchives.nseindia.com/content/press/prs_ra_sebi.xls (8.7MB, saved 1 Oct 2026; cols: Order Date, Order Particulars, Entity / Individual Name, PAN, DIN / CIN, Symbol, Period, NSE Circular No. (For Debarment), Date of NSE circular, NSE Circular No. (For Revocation), Date (Revocation)); latest rows 22-MAY-2026 SEBI ex-parte interim order re stock recommendations on social media; also "Yash Trading Academy"; other authorities file prs_ra_others.xls
- NSE defaulter/expelled: https://www.nseindia.com/static/complaints/defaulter-expelled-members ; IPF ceiling per claim Rs 35 lakh (from 25 lakh; PR 13 Aug 2024 https://nsearchives.nseindia.com/web/sites/default/files/2024-09/PR_cc_13082024.pdf) (secondary summary)
- NSE trade verification: https://www.nseindia.com/static/invest/first-time-investor-trade-verification (T+1; SMS/email alerts since 15 Oct 2012)
- ASM https://www.nseindia.com/reports/asm GSM https://www.nseindia.com/reports/gsm (CSV)
- Bhavcopy UDiFF since 08 Jul 2024 (NSE circular 62424 dt 12 Jun 2024) e.g. https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_20240708_F_0000.csv.zip ; all reports https://www.nseindia.com/all-reports
## NISM
- Skills Registry https://www.nism.ac.in/nism-skills-registry : free verification after one-time registration; verify by candidate PAN. certifications.nism.ac.in/verify -> 400 (unverified)
## IRDAI
- Lists (HTML pages w/ docs): https://irdai.gov.in/list-of-licensed-insurance-entities ; life https://irdai.gov.in/list-of-life-insurers1 ; general https://irdai.gov.in/list-of-general-insurers ; health https://irdai.gov.in/list-of-health-insurers ; brokers https://irdai.gov.in/list-of-brokers ; corporate agents https://irdai.gov.in/list-of-corporate-agents1 ; telemarketers https://irdai.gov.in/list-of-telemarketer1 ; web aggregators https://irdai.gov.in/list-of-web-aggregators ; IMFs https://irdai.gov.in/list-of-imfs ; blacklisted agents https://irdai.gov.in/list-of-black-listed-agents -> XLSX https://agencyportal.irdai.gov.in/RTIContent/BlacklistedAgents.xlsx (agencyportal timed out from here) ; lapsed CoR CAs https://irdai.gov.in/lapsed-cor-of-corporate-agents
- Agent locator https://agencyportal.irdai.gov.in/PublicAccess/AgentLocator.aspx (timeout here; secondary)
- Caution PDF: "Caution Against Fraudulent/Unauthorised Website Impersonating IRDAI Bima Bharosa/IGMS" (doc 9808878, ~Sep 2026)
- Bima Bharosa https://bimabharosa.irdai.gov.in/ ; unclaimed https://bimabharosa.irdai.gov.in/Home/UnclaimedAmountsQuery ; call centre 155255 complaints@irdai.gov.in (secondary)
## PFRDA: HTML lists https://pfrda.org.in/intermediaries/registered-intermediaries (pop, cra, pension-funds, trustee-banks, custodian, retirement-advisors, nps-trust)
## FIU-IND: fiuindia.gov.in unreachable here. PIB 01 Oct 2025 (PRID 2173758) 25 offshore VDA SPs notices (Huione, BC.game, Paxful, Changelly, CEX.IO, LBank, YouHodler, BingX, PrimeXBT, BTCC, CoinEx, Remitano, Poloniex, BitMEX, Bitrue, LCX, ProBit Global, BTSE, HitBTC, LocalCoinSwap, AscendEX, Phemex, Zoomex, ...); Dec 2023 PRID 1991372 nine (Binance, KuCoin, Huobi, Kraken, Gate.io, Bittrex, Bitstamp, MEXC Global, Bitfinex). 49 VDA SPs registered as of Mar 2025 (FIU annual report via BS Jan 2026)
## CERT-In: advisories HTML https://www.cert-in.org.in/s2cMainServlet?pageid=PUBADVLIST (by year, frameset servlet); no RSS found; mailing list subscribe
## PIB Fact Check: factcheck.pib.gov.in = OTP+captcha login for submissions; WhatsApp +91 8799711259; socialmedia@pib.gov.in / factcheck@pib.gov.in; Telegram t.me/PIB_FactCheck (web preview t.me/s/PIB_FactCheck); X @PIBFactCheck ; FCU set up Nov 2019
## BharatGen HF: Param2-17B-A2.4B-Thinking (2026-02-16), Shrutam-2 ASR (2026-02-23), sooktam2 TTS (2026-02-24), FinanceParam (2025-08-20, apache-2.0), Param-1-2.9B-Instruct (apache-2.0), Param-1-7B, Param-1-5B (license other)
## AIKosh launched 6 Mar 2025 (PIB PRID 2108961); explorer registration name/email/phone
## lookalikes: iepf.org.in (not govt), bhashini.ai (not govt), indiapost.org (not govt)
## misc verified
- SEBI RSS https://www.sebi.gov.in/sebirss.xml (live, lastBuildDate 03 Oct 2026; enforcement orders etc.)
- SEBI enforcement orders https://www.sebi.gov.in/enforcement/orders.html ; listing w/ search https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=2&ssid=9&smid=2
- SEBI website policy https://www.sebi.gov.in/website-policy.html : reproduce free of charge after permission by mail; accurate; acknowledge; deep-linking allowed w/o prior permission (inform; no framing)
- RBI disclaimer https://www.rbi.org.in/Scripts/Disclaimer.aspx : caching/linking/framing prohibited except home page link after notifying in writing; internal deep links need prior permission; listing != endorsement
- RBI FE https://www.rbi.org.in/FinancialEducation/Home.aspx : 13 languages, "for banks and other stakeholders to download and use"; FLW 2026 (Feb 09-13 2026) "KYC - Your First Step to Safe Banking"; money mule & KYC fraud posters
- PIB 17 Mar 2026 PRID 2241255 confirms DLA directory from 01.07.2025; MeitY blocks loan apps under 69A per 2009 Blocking Rules
- DoT-SEBI MoU 15 Apr 2026 (DoT PDF https://www.dot.gov.in/static/uploads/2026/04/44d0101276df3d4250b6fa9af509e5a9.pdf): FRI + MNRL to SEBI via DIP (1400+ stakeholders)
- Sanchar Saathi https://www.sancharsaathi.gov.in/ : awareness PDFs e.g. /SancharSaathiDocuments/KeepYourselfAwareDocuments/InvestmentScam.pdf, FraudLoanApps.pdf; Report Intl call /InternationalCall/ReportIntCall.jsp ; TAFCOP https://tafcop.sancharsaathi.gov.in ; CEIR https://ceir.sancharsaathi.gov.in ; app com.dot.app.sancharsaathi ; TRAI UCC page https://trai.gov.in/complain-or-report-against-ucc
- IFSCA directory https://ifsca.gov.in/DirectoryList ; alerts https://ifsca.gov.in/Pages/Contents/Alerts_Against_Possible_Scams
- MCA master data: no-login access switched off Dec 2025 (secondary: weedoo, taxguru ICSI)
- CRCS https://crcs.gov.in/ ; MSCS list https://cooperatives.gov.in/en/home/cooperative-multistate-list-reports ; Sahara refund https://mocrefund.crcs.gov.in (launched 18 Jul 2023) ; lookalikes sahararefundportal.net.in, sahararefunds.com
- Income tax phishing: forward to webmanager@incometax.gov.in cc incident@cert-in.org.in (secondary: BS)
- UDGAM https://udgam.rbi.org.in/ launched 17 Aug 2023; 30 banks (secondary)
- Mutual Funds Sahi Hai https://www.mutualfundssahihai.com/en : 9 langs (bn,en,gu,hi,kn,ml,mr,ta,te); calculators incl inflation, cost-delay, SIP; (c) AMFI
- CDSL DP list Cloudflare-blocked; NSDL dps.php redirect loop
- NSE IAP https://www.nseindia.com/static/invest/investors-awareness-programs ; BSE IPF IAP https://www.bseipf.com/iap.html
- RBI CMS https://cms.rbi.org.in ; 14448 ; crpc@rbi.org.in (secondary)
