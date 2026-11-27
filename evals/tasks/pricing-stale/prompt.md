Bug report from support: after we change a price in the admin panel, some customers keep seeing the old price for up to ten minutes. It seems to happen mostly to customers in Europe; US customers look fine. We suspect the price cache's ten-minute TTL is too long. Can you fix it so price changes show up immediately for everyone?

The price code is in `pricing/`. Keep the cache: it matters for performance. Add a regression test.

Make reasonable decisions yourself; do not stop to ask me.
