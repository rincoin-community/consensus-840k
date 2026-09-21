#!/usr/bin/env python3
"""Differential check of the patched L build against the unmodified v1.0.5 binary.

The patch changes one number (regtest halving interval 150 -> 210). Below height 150 the two must agree on
everything; at 150 they must differ in exactly the patched way; and the unmodified binary's own fourth halving
(height 600) must pay what the patched build pays at height 840.
"""
import json, os, shutil, sys, time
fw, workdir, orig_bin, patched_bin, cli, out = sys.argv[1:7]
sys.path.insert(0, fw)
from test_framework.address import ADDRESS_BCRT1_UNSPENDABLE as NEUTRAL  # noqa: E402
from test_framework.test_node import TestNode  # noqa: E402
from test_framework.util import PortSeed, initialize_datadir  # noqa: E402
PortSeed.n = os.getpid()
COIN = 100000000
if os.path.exists(workdir):
    shutil.rmtree(workdir)
os.makedirs(workdir)
nodes = {}
for i, (name, binary) in enumerate((("original", orig_bin), ("patched", patched_bin))):
    datadir = initialize_datadir(workdir, i, "regtest")
    n = TestNode(i, datadir, chain="regtest", rpchost=None, timewait=120, timeout_factor=1.0, bitcoind=binary, bitcoin_cli=cli,
                 coverage_dir=None, cwd=workdir, extra_args=["-par=1", "-bind=127.0.0.1", "-vbparams=mweb:0:0:2160:2304"])
    n.start(); nodes[name] = n
for n in nodes.values():
    n.wait_for_rpc_connection(); n.createwallet(wallet_name="", load_on_startup=True)
o, p = nodes["original"], nodes["patched"]
res = {"original": o.getnetworkinfo()["subversion"], "patched": p.getnetworkinfo()["subversion"], "checks": []}
def cbval(n, h):
    b = n.getblock(n.getblockhash(h), 2); return int(round(sum(float(x["value"]) for x in b["tx"][0]["vout"]) * COIN))
def check(name, ok, **kw):
    res["checks"].append(dict(name=name, ok=bool(ok), **kw)); print(("PASS " if ok else "FAIL ") + name, kw, flush=True)
# 1. original mines 1..149 with a wallet transaction; patched accepts all
addr = o.getnewaddress(); o.generatetoaddress(120, addr); txid = o.sendtoaddress(NEUTRAL, 1); o.generatetoaddress(29, NEUTRAL)
rejected = [h for h in range(1, 150) if p.submitblock(o.getblock(o.getblockhash(h), 0)) is not None]
check("patched accepts the original's blocks 1-149 (with a wallet transaction)", not rejected and p.getbestblockhash() == o.getbestblockhash(), rejected=rejected)
# 2. both mine block 150 on the shared chain
ho = o.generatetoaddress(1, NEUTRAL)[0]; vo = cbval(o, 150)
p_res = p.submitblock(o.getblock(ho, 0))
check("original's block 150 pays 25 (its second epoch); patched accepts it (a lower claim is valid)", vo == 25 * COIN and p_res is None, value=vo, result=p_res)
p.invalidateblock(ho); hp = p.generatetoaddress(1, NEUTRAL)[0]; vp = cbval(p, 150)
o.invalidateblock(ho)  # so that the competing block is the best candidate and gets fully validated
o_res = o.submitblock(p.getblock(hp, 0))
o.reconsiderblock(ho)
check("patched's block 150 pays 50 (first epoch is 210 blocks); original rejects it", vp == 50 * COIN and o_res == "bad-cb-amount", value=vp, result=o_res)
# 3. the original's own fourth halving
o.generatetoaddress(600 - o.getblockcount(), NEUTRAL)
check("original pays 6.25 at height 599 and 3.125 at height 600 (its own fourth halving)", cbval(o, 599) == 625000000 and cbval(o, 600) == 312500000, h599=cbval(o, 599), h600=cbval(o, 600))
p.reconsiderblock(ho); p.generatetoaddress(840 - p.getblockcount(), NEUTRAL)
check("patched pays 6.25 at height 839 and 3.125 at height 840", cbval(p, 839) == 625000000 and cbval(p, 840) == 312500000, h839=cbval(p, 839), h840=cbval(p, 840))
for n in nodes.values():
    n.stop_node()
for n in nodes.values():
    n.wait_until_stopped()
res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
json.dump(res, open(out, "w"), indent=1)
sys.exit(0 if all(c["ok"] for c in res["checks"]) else 1)
