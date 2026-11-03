# Example 4 — Right of withdrawal

> English reviewer-facing translation. The application replies in Brazilian Portuguese (pt-BR).

**Customer:** I changed my mind about an online purchase. Can I return it?

**Assistant:** Yes, as long as you request the return within **7 calendar days of receiving the product**. The instrument must be in its original packaging, with no signs of use, and include all accessories and manuals.

In this case, return shipping is covered by the store, and the refund is issued to the original payment method within **10 business days**.

To guide you, please send the order number and the date you received the instrument. If the purchase was a customized item, a final-sale item, or a wind mouthpiece, the return does not apply.

**Internal lookup**

```text
search_policy(
  query="return policy",
  top_k=3
)
```

The answer applies section **4.1** of the manual. The agent did not invent a deadline or promise a refund outside the policy. The English query was expanded to the Portuguese policy terms (`devolução`, `arrependimento`) before the hybrid search.
