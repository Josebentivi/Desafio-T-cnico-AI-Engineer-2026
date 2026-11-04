# Example 5 — Out-of-scope request

> English reviewer-facing illustrative conversation. The application replies in English.

**Customer:** Do you sell guitar strings?

**Assistant:** Empório da Música works exclusively with **musical instruments**. We do not carry accessories such as strings, picks, cables, cases, pedals, or amplifiers.

If you are looking for strings, it is worth checking an accessory store or a local partner. Here I can help with acoustic guitars, ukuleles, electric guitars, basses, drums, keyboards, and orchestral instruments that are in the catalog.

Would you like me to show you some available acoustic guitars?

**Internal lookup**

```text
search_policy(
  query="accessories strings picks cables",
  top_k=2
)
```

The agent redirects politely without inventing partner stores or products the store does not sell.
