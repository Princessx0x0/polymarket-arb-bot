# Challenges & Solutions

A log of the 10 major obstacles encountered during development and how each was resolved.

---

## Challenge 1: VM in Wrong Region (London Geoblocked)

**Problem**: Initial VM deployed in London (europe-west2). All Polymarket API calls returned 403 Forbidden due to geographic restrictions.

**Solution**: Migrated VM to us-central1 (Iowa, USA).

---

## Challenge 2: Restricted GCP API Scopes

**Problem**: VM service account had limited API scopes, causing `Permission denied` errors when accessing Secret Manager and BigQuery.

**Solution**: Recreated VM with `--scopes=cloud-platform` to allow full access to all Cloud APIs.

---

## Challenge 3: Iowa Also Geoblocked

**Problem**: After migrating to Iowa, Polymarket API still returned 403. US regions are also restricted.

**Solution**: Migrated VM to Doha, Qatar (me-central1). Middle East region confirmed working.

---

## Challenge 4: USDC Contract Mismatch

**Problem**: Bot showed $0 balance despite funds being visible in Polymarket UI. CLOB API was checking the old USDC.e contract (0x2791) but funds were in the new USDC contract (0x3c49).

**Solution**: Approved both USDC contracts on Polygonscan by calling `approve()` with max uint256 for the Polymarket exchange contract address.

---

## Challenge 5: Minimum Order Size Violations

**Problem**: First live trade attempt failed for all 23 orders. Budget of $1.50 divided across 23 conditions = $0.065 per order, below the $1 minimum.

**Solution**: Deposited additional USDC to bring budget above $23 (minimum $1 per condition × number of conditions).

---

## Challenge 6: Polygon RPC Unreachable from Doha VM

**Problem**: DNS resolution failures when trying to call Polygon RPC endpoints directly from the Doha VM for contract approvals.

**Solution**: Used Polygonscan browser UI instead of programmatic RPC calls for the one-time approval transactions.

---

## Challenge 7: Wrong signature_type Parameter

**Problem**: Balance API consistently returned $0 despite correct credentials. Root cause was `signature_type=0` (EOA) being used when the account was created via MetaMask browser login.

**Solution**: Changed `signature_type` from `0` to `2` (MetaMask/browser wallet) in `client.py`.

---

## Challenge 8: Wrong Funder Address

**Problem**: Even after fixing signature_type, balance still showed $0. The wallet address used as `funder` was the raw MetaMask address, not the Polymarket proxy address.

**Solution**: Found the correct proxy wallet address in Polymarket Account Settings (0xf406...). Set this as the `funder` parameter. This was the critical breakthrough that unlocked balance visibility.

---

## Challenge 9: API Credentials for Wrong Account

**Problem**: `create_or_derive_api_creds()` was being called with a key that derived credentials for a different account than the one holding funds.

**Solution**: Re-ran credential derivation using the correct MetaMask private key associated with the funded Polymarket account.

---

## Challenge 10: Funds Visible in UI But Not in CLOB

**Problem**: After resolving all credential issues, CLOB balance still showed $0 while $19-26 was visible in the Polymarket web UI.

**Solution**: Deposited fresh USDC directly via the Polymarket UI using the Polygon network deposit option. This properly registered the funds with the CLOB system.

---

## Key Insight

The most critical discovery across all challenges was understanding Polymarket's proxy wallet system. The platform creates a proxy wallet address distinct from the user's MetaMask address. This proxy address must be used as the funder parameter in all API calls. Without this, the CLOB has no way to locate the user's funds regardless of how correct the other credentials are.
