# AI options for VPNLens

Single lookups show the evidence directly. A model that only reorders the
same facts adds latency without helping the reader make a decision.

## First use the observed connection

Save a connection baseline, toggle the VPN, and recheck in the same browser.
The comparison shows changes in the public IPv4, location, routed prefix,
origin group and evidence. A changed IP with no matching evidence gives the
operator something specific to investigate. It leaves VPN use unconfirmed.

## Where a model could help

Consider a support workflow that answers a question across several reports.
For example, an operator could ask why a browser extension and desktop client
produced different results. A model could relate their observations to the
recorded evidence and suggest a next test. The report would show the underlying
records and distinguish observations from hypotheses. Validate any benefit
against the connection comparison before adding a provider.

A trained VPN classifier is a separate project. It needs independently labeled
examples, including confirmed negatives, and measured precision and recall.
