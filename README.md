# eBay Sold & Completed Listings Intelligence API

Extract **real closed sale prices**, shipping costs, total landed prices, sale dates, and item conditions from eBay across **8 global marketplaces** (`US`, `UK`, `DE`, `ES`, `FR`, `IT`, `AU`, `CA`) in seconds—without slow browser overhead.

## Why use this eBay Sold Scraper?
- **Actual Sold Prices (`LH_Sold=1`):** Stop guessing market value from inflated active listings. Pull verified completed transactions.
- **Total Landed Cost Calculated:** Automatically parses item price + shipping cost into a clean `totalPrice` numeric field ready for Excel, Google Sheets, n8n, Make, or Python pipelines.
- **No URL Wrangling Required:** Search directly by keyword, model number, or UPC/EAN barcode and filter by marketplace and condition.
- **High-Speed HTTP/2 Engine:** Runs on TLS-fingerprinted requests instead of heavy headless browsers for fast execution and flat per-result pricing.

## Supported Marketplaces
- `US` — United States (`ebay.com`)
- `UK` — United Kingdom (`ebay.co.uk`)
- `DE` — Germany (`ebay.de`)
- `ES` — Spain (`ebay.es`)
- `FR` — France (`ebay.fr`)
- `IT` — Italy (`ebay.it`)
- `AU` — Australia (`ebay.com.au`)
- `CA` — Canada (`ebay.ca`)

## Example Input
```json
{
  "query": "iPhone 15 Pro 128GB",
  "country": "US",
  "soldOnly": true,
  "condition": "3000",
  "maxItems": 60
}
