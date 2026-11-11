# Part A: Invoice extraction prompt

## First attempt

```
Extract the invoice data as JSON.

INVOICE #INV-2024-0891 | Vendor: Acme Corp | Date: October 12, 2024
Items: Web Design Services ×1 @ $3,500 · Support Package ×3 @ $200 each
Total Due: $4,100 | Payment Due: November 1, 2024
```

This sort of worked, but the key names changed between runs (`vendor_name` one time, `vendor` the next), the JSON came back inside a ```json block with a line of text before it, and the dates and amounts were in different formats each time ("October 12, 2024" vs "2024-10-12", "$4,100" vs 4100).

## Final prompt

```
Pull the details out of the invoice below and give them back as a JSON object.

Reply with the JSON only. No intro line, no explanation after it, and don't wrap it in ```json fences, because I'm passing the reply straight to json.loads().

Use exactly these 6 keys:
vendor: string
invoice_number: string
invoice_date: string, YYYY-MM-DD
line_items: list of objects, each with description (string), quantity (number) and unit_price (number)
total_amount: number, without the $ sign or commas
due_date: string, YYYY-MM-DD

If something isn't on the invoice, set that key to null. Don't guess values and don't add any other keys.

Invoice:
INVOICE #INV-2024-0891 | Vendor: Acme Corp | Date: October 12, 2024
Items: Web Design Services ×1 @ $3,500 · Support Package ×3 @ $200 each
Total Due: $4,100 | Payment Due: November 1, 2024
```

## Claude's output

<!-- PASTE THE REAL OUTPUT HERE: run the final prompt in a new Claude.ai chat and paste exactly what it returns, then delete this comment -->

Checked it against the invoice: 1 × 3500 + 3 × 200 = 4100, which matches the total, and both dates are in YYYY-MM-DD.

## What changed

My first prompt just said "extract as JSON", so in the final version I listed the exact keys, fixed the date and number formats, told it to return only raw JSON and to use null for anything missing, and after that the output was the same every run and parsed without any cleanup.
