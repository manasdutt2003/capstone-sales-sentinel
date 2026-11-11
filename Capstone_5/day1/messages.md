# Part C: System and user messages

## SYSTEM

```
You'll be given the text of an invoice. Pull the details out and give them back as a JSON object.

Reply with the JSON only. No intro line, no explanation after it, and don't wrap it in ```json fences, because the reply goes straight into json.loads().

Use exactly these 6 keys:
vendor: string
invoice_number: string
invoice_date: string, YYYY-MM-DD
line_items: list of objects, each with description (string), quantity (number) and unit_price (number)
total_amount: number, without the $ sign or commas
due_date: string, YYYY-MM-DD

If something isn't on the invoice, set that key to null. Don't guess values and don't add any other keys.
```

## USER

```
INVOICE #INV-2024-0891 | Vendor: Acme Corp | Date: October 12, 2024
Items: Web Design Services ×1 @ $3,500 · Support Package ×3 @ $200 each
Total Due: $4,100 | Payment Due: November 1, 2024
```

## Why split them

The rules for the output don't change from one invoice to the next, so putting them in the system message means I write them once and every request gets exactly the same instructions. The user message then only carries the invoice text, which keeps the data separate from the instructions and means I only swap one thing out per invoice.
